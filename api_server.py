from __future__ import annotations

import argparse
import json
import math
import mimetypes
import threading
import traceback
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from dayahead_core import (
    DEFAULT_FORECAST_FILE,
    DEFAULT_HISTORY_DIR,
    DEFAULT_MODEL_ROOT,
    DEFAULT_OUTPUT_FILE,
    PRICE_CAP,
    PRICE_FLOOR,
    TrainConfig,
    activate_model_version,
    delete_model_versions,
    list_model_versions,
    load_current_metadata,
    load_training_log,
    predict_prices_compare,
    rollback_to_previous,
    train_and_register,
)


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_APP_DIR = BASE_DIR / "frontend_app"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

MODEL_ROOT = Path(DEFAULT_MODEL_ROOT)
FORECAST_FILE = Path(DEFAULT_FORECAST_FILE)
HISTORY_DIR = Path(DEFAULT_HISTORY_DIR)
OUTPUT_FILE = Path(DEFAULT_OUTPUT_FILE)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_version_label(row: dict[str, Any]) -> str:
    flags: list[str] = []
    if row.get("is_default"):
        flags.append("默认模型")
    if row.get("is_previous"):
        flags.append("上一版")
    if row.get("is_pinned_default"):
        flags.append("已锁定默认")
    suffix = f" | {' / '.join(flags)}" if flags else ""
    return (
        f"{row.get('version_key', '-')}"
        f" | {row.get('created_at', '-')}"
        f" | {row.get('train_start_date', '-')} ~ {row.get('train_end_date', '-')}"
        f"{suffix}"
    )


def sanitize_scalar(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [sanitize_scalar(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize_scalar(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return [sanitize_scalar(item) for item in value.tolist()]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        if getattr(value, "hour", 0) == 0 and getattr(value, "minute", 0) == 0 and getattr(value, "second", 0) == 0:
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if math.isnan(float(value)):
            return None
        return float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    safe_df = df.copy().where(pd.notna(df), None)
    return [{str(key): sanitize_scalar(value) for key, value in row.items()} for row in safe_df.to_dict(orient="records")]


def to_jsonable(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(key): to_jsonable(value) for key, value in data.items()}
    if isinstance(data, list):
        return [to_jsonable(item) for item in data]
    if isinstance(data, tuple):
        return [to_jsonable(item) for item in data]
    if isinstance(data, pd.DataFrame):
        return dataframe_to_records(data)
    return sanitize_scalar(data)


def read_first_sheet(file_path: Path) -> tuple[str, pd.DataFrame]:
    workbook = pd.read_excel(file_path, sheet_name=None)
    for sheet_name, sheet_df in workbook.items():
        if not sheet_df.empty or len(sheet_df.columns) > 0:
            result = sheet_df.copy().reset_index(drop=True)
            result.columns = [str(column).strip() for column in result.columns]
            return str(sheet_name), result
    raise ValueError(f"未从 {file_path} 读取到可用 Sheet")


def load_forecast_template_preview(file_path: Path = FORECAST_FILE) -> dict[str, Any]:
    sheet_name, df = read_first_sheet(file_path)
    preview_df = df.iloc[:96].copy().reset_index(drop=True)
    return {
        "file_path": str(file_path),
        "sheet_name": sheet_name,
        "columns": [str(column) for column in preview_df.columns],
        "rows": dataframe_to_records(preview_df),
        "row_count": int(len(preview_df)),
    }


def save_forecast_template_rows(rows: list[dict[str, Any]], file_path: Path = FORECAST_FILE) -> None:
    workbook = load_workbook(file_path)
    worksheet = workbook[workbook.sheetnames[0]]
    headers = [worksheet.cell(row=1, column=col).value for col in range(1, worksheet.max_column + 1)]
    header_map = {str(header).strip(): index for index, header in enumerate(headers, start=1) if header not in (None, "")}

    for row_index, row_data in enumerate(rows, start=2):
        for header, value in row_data.items():
            if header not in header_map:
                continue
            worksheet.cell(row=row_index, column=header_map[header]).value = None if value == "" else value
    workbook.save(file_path)


def load_latest_prediction_output(file_path: Path = OUTPUT_FILE) -> dict[str, Any] | None:
    if not file_path.exists():
        return None
    sheet_name, df = read_first_sheet(file_path)
    result_df = df.copy().reset_index(drop=True)
    forecast_date = None
    if "date" in result_df.columns and not result_df.empty:
        forecast_date = sanitize_scalar(pd.to_datetime(result_df.loc[0, "date"], errors="coerce"))
    return {
        "file_path": str(file_path),
        "sheet_name": sheet_name,
        "forecast_date": forecast_date,
        "columns": [str(column) for column in result_df.columns],
        "rows": dataframe_to_records(result_df),
        "row_count": int(len(result_df)),
    }


@dataclass
class JobState:
    job_id: str
    job_type: str
    status: str = "等待中"
    progress: int = 0
    running: bool = True
    cancel_requested: bool = False
    cancelled: bool = False
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    result: dict[str, Any] | None = None
    started_at: str = field(default_factory=now_text)
    finished_at: str | None = None


class JobCancelledError(RuntimeError):
    pass


class AppState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobState] = {}
        self._current_job_id: str | None = None
        self._last_prediction: dict[str, Any] | None = None

    def has_running_job(self) -> bool:
        if not self._current_job_id:
            return False
        job = self._jobs.get(self._current_job_id)
        return bool(job and job.running)

    def create_job(self, job_type: str) -> JobState:
        with self._lock:
            if self.has_running_job():
                raise RuntimeError("当前已有任务在执行，请等待完成后再试。")
            job_id = datetime.now().strftime(f"{job_type}_%Y%m%d_%H%M%S")
            job = JobState(job_id=job_id, job_type=job_type, status=f"{job_type}任务已创建")
            self._jobs[job_id] = job
            self._current_job_id = job_id
            return job

    def append_log(self, job_id: str, message: str, progress: int | None = None) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = message
            if progress is not None:
                job.progress = max(0, min(100, int(progress)))
            job.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
            job.logs = job.logs[-400:]

    def request_cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            job = self._jobs[job_id]
            if not job.running:
                return to_jsonable(job.__dict__)
            job.cancel_requested = True
            job.status = "正在停止任务..."
            job.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 已收到停止请求，正在安全中断")
            job.logs = job.logs[-400:]
            return to_jsonable(job.__dict__)

    def raise_if_cancelled(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.cancel_requested:
                raise JobCancelledError("任务已手动停止")

    def finish_job(
        self,
        job_id: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        cancelled: bool = False,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.running = False
            job.finished_at = now_text()
            if cancelled or job.cancel_requested:
                job.cancelled = True
                job.status = "任务已停止"
                job.progress = min(job.progress or 0, 99)
                job.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 任务已停止")
            elif error:
                job.error = error
                job.status = "执行失败"
                job.progress = min(job.progress or 0, 99)
                job.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 执行失败：{error}")
            else:
                job.result = result
                job.status = "执行完成"
                job.progress = 100
                job.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 执行完成")
                if result and result.get("prediction"):
                    self._last_prediction = result["prediction"]
            if self._current_job_id == job_id:
                self._current_job_id = None

    def snapshot(self, job_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            target_id = job_id or self._current_job_id
            if not target_id or target_id not in self._jobs:
                return None
            return to_jsonable(self._jobs[target_id].__dict__)

    def status(self) -> dict[str, Any]:
        with self._lock:
            current_job = self._jobs.get(self._current_job_id) if self._current_job_id else None
            recent_jobs = sorted(self._jobs.values(), key=lambda item: item.started_at, reverse=True)[:10]
            return {
                "running": bool(current_job and current_job.running),
                "current_job": to_jsonable(current_job.__dict__) if current_job else None,
                "recent_jobs": [to_jsonable(item.__dict__) for item in recent_jobs],
                "last_prediction": self._last_prediction or load_latest_prediction_output(),
            }


STATE = AppState()


def build_progress_callback(job_id: str) -> Callable[[str, int | None], None]:
    def callback(message: str, percent: int | None) -> None:
        STATE.raise_if_cancelled(job_id)
        STATE.append_log(job_id, message, percent)
        STATE.raise_if_cancelled(job_id)

    return callback


def start_background_job(job_type: str, worker: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    job = STATE.create_job(job_type)

    def runner() -> None:
        try:
            result = worker(job.job_id)
            STATE.finish_job(job.job_id, result=result)
        except JobCancelledError:
            STATE.finish_job(job.job_id, cancelled=True)
        except Exception as exc:  # noqa: BLE001
            STATE.finish_job(job.job_id, error=f"{exc}\n{traceback.format_exc(limit=3)}")

    threading.Thread(target=runner, daemon=True).start()
    return {"job_id": job.job_id, "job_type": job.job_type, "status": job.status}


def summarize_train_result(result: Any) -> dict[str, Any]:
    return {
        "run_id": result.run_id,
        "current_model_dir": str(result.current_model_dir),
        "history_model_dir": str(result.history_model_dir),
        "metrics": to_jsonable(result.metrics),
        "train_dates": result.train_dates,
        "valid_dates": result.valid_dates,
        "skipped_sheets": result.skipped_sheets,
        "metadata_path": str(result.metadata_path),
    }


def serialize_prediction_variant(result: Any) -> dict[str, Any]:
    return {
        "forecast_date": result.forecast_date,
        "output_file": str(result.output_file),
        "template_updated": result.template_updated,
        "reference_strategy_key": result.reference_strategy_key,
        "reference_strategy_label": result.reference_strategy_label,
        "reference_days_requested": result.reference_days_requested,
        "reference_dates": result.reference_dates,
        "columns": list(result.result_df.columns),
        "rows": dataframe_to_records(result.result_df),
    }


def summarize_predict_result(result: Any) -> dict[str, Any]:
    prediction = serialize_prediction_variant(result.strategy_results[result.selected_strategy_key])
    prediction["comparison_predictions"] = {
        key: serialize_prediction_variant(value)
        for key, value in result.strategy_results.items()
    }
    prediction["selected_strategy_key"] = result.selected_strategy_key
    prediction["selected_strategy_label"] = result.selected_strategy_label
    return {
        "forecast_date": result.forecast_date,
        "output_file": str(result.output_file),
        "template_updated": result.template_updated,
        "selected_strategy_key": result.selected_strategy_key,
        "selected_strategy_label": result.selected_strategy_label,
        "prediction": prediction,
    }


def build_train_worker(payload: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    def worker(job_id: str) -> dict[str, Any]:
        STATE.append_log(job_id, "收到手动重训请求", 1)
        STATE.raise_if_cancelled(job_id)
        result = train_and_register(
            TrainConfig(
                history_dir=Path(payload.get("history_dir") or HISTORY_DIR),
                model_root=Path(payload.get("model_root") or MODEL_ROOT),
                valid_days=int(payload.get("valid_days") or 14),
                num_boost_round=int(payload.get("num_boost_round") or 400),
                start_date=(payload.get("start_date") or None) if payload.get("enable_start", True) else None,
                end_date=(payload.get("end_date") or None) if payload.get("enable_end", True) else None,
            ),
            progress_callback=build_progress_callback(job_id),
        )
        return summarize_train_result(result)

    return worker


def build_predict_worker(payload: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    def worker(job_id: str) -> dict[str, Any]:
        STATE.append_log(job_id, "收到预测请求", 1)
        STATE.raise_if_cancelled(job_id)
        result = predict_prices_compare(
            history_dir=Path(payload.get("history_dir") or HISTORY_DIR),
            forecast_file=Path(payload.get("forecast_file") or FORECAST_FILE),
            model_root=Path(payload.get("model_root") or MODEL_ROOT),
            output_file=Path(payload.get("output_file") or OUTPUT_FILE),
            reference_days=int(payload.get("reference_days") or 1),
            selected_strategy=str(payload.get("selected_strategy") or "recent_n_days"),
            progress_callback=build_progress_callback(job_id),
        )
        return summarize_predict_result(result)

    return worker


def protected_versions() -> set[str]:
    versions_df = list_model_versions(MODEL_ROOT)
    protected: set[str] = set()
    if versions_df.empty:
        return protected
    protected.update(versions_df.loc[versions_df["is_default"], "version_key"].astype(str).tolist())
    protected.update(versions_df.loc[versions_df["is_previous"], "version_key"].astype(str).tolist())
    return protected


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "DayAheadPriceApi/1.0"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/config":
                return self.send_json(self.get_config())
            if path == "/api/status":
                return self.send_json(self.get_status())
            if path == "/api/model/current":
                return self.send_json({"metadata": load_current_metadata(MODEL_ROOT) or {}})
            if path == "/api/model/versions":
                return self.send_json(self.get_versions())
            if path == "/api/training/logs":
                return self.send_json(self.get_training_logs())
            if path == "/api/forecast/template":
                return self.send_json(load_forecast_template_preview())
            if path == "/api/prediction/latest":
                return self.send_json({"prediction": load_latest_prediction_output()})
            if path.startswith("/api/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                snapshot = STATE.snapshot(job_id)
                if snapshot is None:
                    return self.send_error_json(HTTPStatus.NOT_FOUND, "未找到任务")
                return self.send_json(snapshot)
            if path == "/download/output":
                return self.send_file(OUTPUT_FILE, OUTPUT_FILE.name)
            return self.serve_static(path)
        except Exception as exc:  # noqa: BLE001
            return self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            payload = self.read_json_body()
            if path == "/api/jobs/cancel":
                job_id = str(payload.get("job_id") or "").strip()
                if not job_id:
                    return self.send_error_json(HTTPStatus.BAD_REQUEST, "缺少 job_id")
                try:
                    return self.send_json(STATE.request_cancel(job_id))
                except KeyError:
                    return self.send_error_json(HTTPStatus.NOT_FOUND, "未找到任务")
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                job_id = urllib.parse.unquote(path.split("/")[-2])
                try:
                    return self.send_json(STATE.request_cancel(job_id))
                except KeyError:
                    return self.send_error_json(HTTPStatus.NOT_FOUND, "未找到任务")
            if path == "/api/train":
                return self.send_json(start_background_job("train", build_train_worker(payload)), HTTPStatus.ACCEPTED)
            if path == "/api/predict":
                return self.send_json(start_background_job("predict", build_predict_worker(payload)), HTTPStatus.ACCEPTED)
            if path == "/api/forecast/template/save":
                save_forecast_template_rows(payload.get("rows") or [])
                return self.send_json({"message": "预测文件已保存"})
            if path == "/api/model/activate":
                version_key = str(payload.get("version_key") or "").strip()
                if not version_key:
                    return self.send_error_json(HTTPStatus.BAD_REQUEST, "缺少 version_key")
                activate_model_version(MODEL_ROOT, version_key)
                return self.send_json({"message": f"已切换默认模型：{version_key}"})
            if path == "/api/model/rollback":
                current_dir = rollback_to_previous(MODEL_ROOT)
                return self.send_json({"message": "已回退到上一版模型", "current_model_dir": str(current_dir)})
            if path == "/api/model/delete":
                version_keys = [str(item).strip() for item in payload.get("version_keys") or [] if str(item).strip()]
                if not version_keys:
                    return self.send_error_json(HTTPStatus.BAD_REQUEST, "请选择要删除的模型版本")
                invalid = [key for key in version_keys if key in protected_versions()]
                if invalid:
                    return self.send_error_json(HTTPStatus.BAD_REQUEST, f"以下版本当前受保护，不能直接删除：{', '.join(invalid)}")
                deleted = delete_model_versions(MODEL_ROOT, version_keys)
                return self.send_json({"message": "删除完成", "deleted": deleted})
            return self.send_error_json(HTTPStatus.NOT_FOUND, "未找到接口")
        except RuntimeError as exc:
            return self.send_error_json(HTTPStatus.CONFLICT, str(exc))
        except Exception as exc:  # noqa: BLE001
            return self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def get_config(self) -> dict[str, Any]:
        return {
            "app_name": "日前电价预测平台",
            "history_dir": str(HISTORY_DIR),
            "model_root": str(MODEL_ROOT),
            "forecast_file": str(FORECAST_FILE),
            "output_file": str(OUTPUT_FILE),
            "frontend_dir": str(FRONTEND_APP_DIR),
            "price_floor": PRICE_FLOOR,
            "price_cap": PRICE_CAP,
            "default_reference_days": 1,
            "reference_strategy_options": [
                {"key": "recent_n_days", "label": "最近 N 天"},
                {"key": "recent_same_type_days", "label": "最近 N 个同类型日"},
            ],
            "default_reference_strategy": "recent_n_days",
            "server_time": now_text(),
        }

    def get_status(self) -> dict[str, Any]:
        status = STATE.status()
        status["current_model"] = load_current_metadata(MODEL_ROOT) or {}
        return status

    def get_versions(self) -> dict[str, Any]:
        versions_df = list_model_versions(MODEL_ROOT)
        if versions_df.empty:
            return {"versions": []}
        records = dataframe_to_records(versions_df)
        for row in records:
            row["label"] = make_version_label(row)
        return {"versions": records}

    def get_training_logs(self) -> dict[str, Any]:
        log_df = load_training_log(MODEL_ROOT)
        if log_df.empty:
            return {"logs": []}
        log_df = log_df.sort_values("created_at", ascending=False).reset_index(drop=True)
        return {"logs": dataframe_to_records(log_df)}

    def read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")

    def send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(to_jsonable(data), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def send_file(self, file_path: Path, download_name: str | None = None) -> None:
        if not file_path.exists():
            return self.send_error_json(HTTPStatus.NOT_FOUND, f"文件不存在：{file_path}")
        content = file_path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(file_path))
        self.send_response(HTTPStatus.OK)
        self.send_common_headers()
        self.send_header("Content-Type", content_type or "application/octet-stream")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_static(self, path: str) -> None:
        decoded = urllib.parse.unquote(path)
        if decoded in {"", "/"}:
            target = FRONTEND_APP_DIR / "index.html"
        else:
            target = (FRONTEND_APP_DIR / decoded.lstrip("/")).resolve()
            if FRONTEND_APP_DIR.resolve() not in [target, *target.parents]:
                return self.send_error_json(HTTPStatus.FORBIDDEN, "非法路径")
        if not target.exists() or target.is_dir():
            target = FRONTEND_APP_DIR / "index.html"
        content = target.read_bytes()
        content_type, _ = mimetypes.guess_type(str(target))
        self.send_response(HTTPStatus.OK)
        self.send_common_headers()
        self.send_header("Content-Type", f"{content_type or 'text/html'}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def build_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), ApiHandler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="日前电价预测平台 API 服务")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口")
    parser.add_argument("--open-browser", action="store_true", help="启动后自动打开浏览器")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not FRONTEND_APP_DIR.exists():
        raise FileNotFoundError(f"未找到前端目录：{FRONTEND_APP_DIR}")

    server = build_server(args.host, args.port)
    url = f"http://{args.host}:{args.port}"
    print(f"前端地址：{url}")
    print(f"历史数据目录：{HISTORY_DIR}")
    print(f"预测文件：{FORECAST_FILE}")
    print(f"模型目录：{MODEL_ROOT}")
    if args.open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
