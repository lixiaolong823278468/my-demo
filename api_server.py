from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import shutil
import stat
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

from data_quality import latest_quality_report, list_quality_reports, load_quality_report
from dayahead_core import (
    DEFAULT_FORECAST_FILE,
    DEFAULT_HISTORY_DIR,
    DEFAULT_MODEL_ROOT,
    DEFAULT_OUTPUT_FILE,
    DEFAULT_SEGMENT_CONFIG,
    PRICE_CAP,
    PRICE_FLOOR,
    TrainConfig,
    activate_model_version,
    build_history_source_signature,
    delete_model_versions,
    list_model_versions,
    load_cached_history_collection,
    load_current_metadata,
    load_training_log,
    load_training_preferences,
    normalize_segment_config,
    normalize_similarity_weights,
    predict_prices_compare,
    rank_model_candidates,
    rollback_to_previous,
    save_training_preferences,
    train_and_register,
)
from price_interval import normalize_price_intervals
from prediction_archive import (
    DEFAULT_PREDICTION_ARCHIVE_ROOT,
    archive_prediction_bundle,
    list_prediction_archives,
    load_prediction_archive_detail,
)


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_APP_DIR = BASE_DIR / "frontend_app"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

MODEL_ROOT = Path(DEFAULT_MODEL_ROOT)
FORECAST_FILE = Path(DEFAULT_FORECAST_FILE)
HISTORY_DIR = Path(DEFAULT_HISTORY_DIR)
OUTPUT_FILE = Path(DEFAULT_OUTPUT_FILE)
OUTPUT_ROOT = BASE_DIR / "output"
PREDICTION_ARCHIVE_ROOT = DEFAULT_PREDICTION_ARCHIVE_ROOT
WINDOW_OPTIMIZATION_STATE_FILE = MODEL_ROOT / "window_optimization.json"
WINDOW_OPTIMIZATION_OUTPUT_ROOT = OUTPUT_ROOT / "window_optimization"
AUTO_WINDOW_CANDIDATES = [30, 45, 60, 75, 90, 120, 150, 180, 240, 365]
AUTO_WINDOW_FINE_RADIUS = 15
AUTO_WINDOW_MAX_HISTORY_DAYS = 100
AUTO_WINDOW_VALID_DAYS = 14
AUTO_WINDOW_NUM_BOOST_ROUND = 400
AUTO_WINDOW_RERANK_TOP_N = 3
AUTO_WINDOW_CHECK_INTERVAL_SECONDS = 60
LAST_AUTO_WINDOW_CHECK_AT: datetime | None = None


def parse_similarity_weights_payload(payload: dict[str, Any]) -> dict[str, float] | None:
    raw_weights = payload.get("similarity_weights")
    if raw_weights is None:
        return None
    if not isinstance(raw_weights, dict):
        raise ValueError("similarity_weights 必须是对象")
    return dict(normalize_similarity_weights(raw_weights))


def resolve_similarity_weights(payload: dict[str, Any], model_root: Path = MODEL_ROOT) -> dict[str, float]:
    parsed_weights = parse_similarity_weights_payload(payload)
    if parsed_weights is not None:
        return parsed_weights
    return dict(load_training_preferences(model_root)["similarity_weights"])


def parse_segment_config_payload(payload: dict[str, Any]) -> list[dict[str, object]] | None:
    mode = str(payload.get("segment_mode") or "default")
    if mode != "custom":
        return None
    raw_segments = payload.get("segment_config")
    if not isinstance(raw_segments, list):
        raise ValueError("自定义时段配置不能为空")
    normalized = normalize_segment_config(raw_segments)
    return [
        {
            "name": name,
            "start_time": f"{((start - 1) * 15) // 60:02d}:{((start - 1) * 15) % 60:02d}",
            "end_time": f"{(end * 15) // 60:02d}:{(end * 15) % 60:02d}",
        }
        for name, (start, end) in normalized.items()
    ]


def parse_high_price_weighting_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("high_price_weighting") if isinstance(payload.get("high_price_weighting"), dict) else {}
    enabled = bool(raw.get("enabled", payload.get("high_price_weight_enabled", False)))
    try:
        quantile = float(raw.get("quantile", payload.get("high_price_quantile", 0.8)))
    except (TypeError, ValueError):
        quantile = 0.8
    try:
        multiplier = float(raw.get("multiplier", payload.get("high_price_weight_multiplier", 2.0)))
    except (TypeError, ValueError):
        multiplier = 2.0
    return {
        "enabled": enabled,
        "quantile": min(0.99, max(0.5, quantile)),
        "multiplier": max(1.0, multiplier),
    }


def parse_price_intervals_payload(payload: dict[str, Any]) -> list[dict[str, object]]:
    intervals = payload.get("price_intervals")
    if intervals is None:
        intervals = load_training_preferences(MODEL_ROOT).get("price_intervals")
    return normalize_price_intervals(intervals if isinstance(intervals, list) else None)


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


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(data), ensure_ascii=False, indent=2), encoding="utf-8")


def parse_optional_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def update_segment_price_model_selection(model_root: Path, selected: dict[str, Any]) -> dict[str, Any]:
    current_dir = model_root / "current"
    metadata_path = current_dir / "metadata.json"
    metadata = read_json_file(metadata_path)
    if not metadata:
        raise FileNotFoundError("当前模型元数据不存在，请先训练模型")
    variants = metadata.get("model_variants") if isinstance(metadata.get("model_variants"), dict) else {}
    segments = metadata.get("segments") if isinstance(metadata.get("segments"), list) else metadata.get("segment_config")
    segment_names = {str(item.get("name")) for item in segments or [] if isinstance(item, dict) and item.get("name")}
    if not isinstance(selected, dict):
        raise ValueError("selected_segment_price_models 必须是对象")
    normalized: dict[str, str] = {}
    for raw_segment, raw_model_key in selected.items():
        segment_name = str(raw_segment).strip()
        model_key = str(raw_model_key).strip()
        if not segment_name or not model_key:
            continue
        if segment_names and segment_name not in segment_names:
            raise ValueError(f"未知时段：{segment_name}")
        if model_key not in variants:
            raise ValueError(f"未知模型：{model_key}")
        normalized[segment_name] = model_key
    metadata["selected_segment_price_models"] = normalized
    metadata["segment_price_model_selection_updated_at"] = now_text()
    write_json_file(metadata_path, metadata)
    run_id = str(metadata.get("run_id") or "").strip()
    history_path = model_root / "history" / run_id / "metadata.json" if run_id else None
    if history_path and history_path.exists():
        write_json_file(history_path, metadata)
    return metadata


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
            if job.job_type == "optimize":
                mark_window_optimization_attempt_status("cancelled", "任务已手动停止")
            STATE.finish_job(job.job_id, cancelled=True)
        except Exception as exc:  # noqa: BLE001
            if job.job_type == "optimize":
                mark_window_optimization_attempt_status("failed", str(exc))
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
        "quality_report_path": str(result.quality_report_path) if result.quality_report_path else None,
    }


def summarize_metric_rows(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total_rows = 0.0
    mae_sum = 0.0
    rmse_sum = 0.0
    rmse_square_sum = 0.0
    for row in (metrics or {}).values():
        valid_rows = float(row.get("valid_rows") or 0)
        mae = row.get("final_mae")
        rmse = row.get("final_rmse")
        if valid_rows <= 0 or mae is None or rmse is None:
            continue
        mae_value = float(mae)
        rmse_value = float(rmse)
        total_rows += valid_rows
        mae_sum += mae_value * valid_rows
        rmse_sum += rmse_value * valid_rows
        rmse_square_sum += rmse_value**2 * valid_rows
    return {
        "valid_rows": int(total_rows),
        "mae": round(mae_sum / total_rows, 4) if total_rows else None,
        "rmse": round(rmse_sum / total_rows, 4) if total_rows else None,
        "rmse_true_weighted": round(math.sqrt(rmse_square_sum / total_rows), 4) if total_rows else None,
    }


def window_score(summary: dict[str, Any]) -> float:
    mae = summary.get("mae")
    rmse = summary.get("rmse")
    if mae is None or rmse is None:
        return float("inf")
    return float(mae) + 0.2 * float(rmse)


def rolling_metric_score(metric: dict[str, Any] | None) -> float | None:
    if not isinstance(metric, dict):
        return None
    mae = metric.get("mae")
    rmse = metric.get("rmse")
    if mae is None or rmse is None:
        return None
    return float(mae) + 0.2 * float(rmse)


def business_window_score(static_metrics: dict[str, Any], rolling_metrics: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    parts: list[tuple[str, float, float]] = []
    static_score = window_score(static_metrics)
    if math.isfinite(static_score):
        parts.append(("static_validation", 0.2, static_score))

    rolling_14 = rolling_metrics.get("14") or {}
    rolling_30 = rolling_metrics.get("30") or {}
    rolling_14_score = rolling_metric_score(rolling_14.get("overall"))
    rolling_30_score = rolling_metric_score(rolling_30.get("overall"))
    if rolling_14_score is not None:
        parts.append(("rolling_14_days", 0.3, rolling_14_score))
    if rolling_30_score is not None:
        parts.append(("rolling_30_days", 0.2, rolling_30_score))

    high_scores = [
        rolling_metric_score((rolling_14.get("spike_errors") or {}).get("high")),
        rolling_metric_score((rolling_30.get("spike_errors") or {}).get("high")),
    ]
    high_scores = [value for value in high_scores if value is not None]
    if high_scores:
        parts.append(("high_price_spike", 0.2, sum(high_scores) / len(high_scores)))

    evening_scores = [
        rolling_metric_score((rolling_14.get("segments") or {}).get("evening_peak")),
        rolling_metric_score((rolling_30.get("segments") or {}).get("evening_peak")),
    ]
    evening_scores = [value for value in evening_scores if value is not None]
    if evening_scores:
        parts.append(("evening_peak", 0.1, sum(evening_scores) / len(evening_scores)))

    if not parts:
        return float("inf"), {"parts": [], "basis": "none"}
    total_weight = sum(weight for _, weight, _ in parts)
    score = sum(weight * value for _, weight, value in parts) / total_weight
    return score, {
        "basis": "rolling_backtest" if rolling_metrics else "static_validation",
        "parts": [
            {"name": name, "weight": weight, "score": round(value, 4)}
            for name, weight, value in parts
        ],
    }


def summarize_window_result(result: Any, model_root: Path, window_days: int, phase: str) -> dict[str, Any]:
    metadata = read_json_file(Path(result.current_model_dir) / "metadata.json")
    variant_metrics = metadata.get("variant_metrics") or {}
    selected_key = metadata.get("selected_model_key")
    direct_metrics = summarize_metric_rows(
        variant_metrics.get(selected_key)
        or variant_metrics.get("no_lag_96")
        or variant_metrics.get("direct_price")
        or metadata.get("metrics")
        or {}
    )
    static_score = window_score(direct_metrics)
    rolling_metrics = metadata.get("rolling_backtest_metrics") or {}
    score, score_detail = business_window_score(direct_metrics, rolling_metrics)
    return {
        "phase": phase,
        "window_days": int(window_days),
        "score": round(score, 4) if math.isfinite(score) else None,
        "static_score": round(static_score, 4) if math.isfinite(static_score) else None,
        "score_detail": score_detail,
        "run_id": result.run_id,
        "model_root": str(model_root),
        "train_start": result.train_dates[0] if result.train_dates else None,
        "train_end": result.train_dates[-1] if result.train_dates else None,
        "valid_start": result.valid_dates[0] if result.valid_dates else None,
        "valid_end": result.valid_dates[-1] if result.valid_dates else None,
        "train_date_count": len(result.train_dates),
        "valid_date_count": len(result.valid_dates),
        "sample_rows": metadata.get("sample_rows"),
        "selected_model_key": selected_key,
        "selected_model_backend": metadata.get("selected_model_backend"),
        "metrics": direct_metrics,
        "rolling_backtest_metrics": rolling_metrics,
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
        "quality_report_path": str(result.quality_report_path) if result.quality_report_path else None,
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
        "quality_report_path": str(result.quality_report_path) if result.quality_report_path else None,
        "prediction": prediction,
    }


def build_train_worker(payload: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    def worker(job_id: str) -> dict[str, Any]:
        STATE.append_log(job_id, "收到手动重训请求", 1)
        STATE.raise_if_cancelled(job_id)
        model_root = Path(payload.get("model_root") or MODEL_ROOT)
        training_mode = str(payload.get("training_mode") or "rolling_window")
        training_window_days = int(payload.get("training_window_days") or 60) if training_mode == "rolling_window" else None
        segment_config = parse_segment_config_payload(payload)
        high_price_weighting = parse_high_price_weighting_payload(payload)
        price_intervals = parse_price_intervals_payload(payload)
        STATE.append_log(job_id, describe_training_options(segment_config, high_price_weighting), 3)
        save_training_preferences(
            model_root,
            {
                "segment_mode": "custom" if segment_config else "default",
                "segment_config": segment_config or DEFAULT_SEGMENT_CONFIG,
                "high_price_weighting": high_price_weighting,
                "price_intervals": price_intervals,
            },
        )
        previous_metadata = load_current_metadata(model_root) or {}
        previous_run_id = previous_metadata.get("run_id")
        result = train_and_register(
            TrainConfig(
                history_dir=Path(payload.get("history_dir") or HISTORY_DIR),
                model_root=model_root,
                valid_days=int(payload.get("valid_days") or 14),
                training_window_days=training_window_days,
                num_boost_round=int(payload.get("num_boost_round") or 400),
                start_date=(payload.get("start_date") or None) if training_mode != "rolling_window" and payload.get("enable_start", True) else None,
                end_date=(payload.get("end_date") or None) if training_mode != "rolling_window" and payload.get("enable_end", True) else None,
                similarity_reference_days=int(payload.get("similarity_reference_days") or 100),
                segment_config=segment_config,
                high_price_weight_enabled=high_price_weighting["enabled"],
                high_price_quantile=high_price_weighting["quantile"],
                high_price_weight_multiplier=high_price_weighting["multiplier"],
                price_intervals=price_intervals,
            ),
            progress_callback=build_progress_callback(job_id),
        )
        validate_training_result_or_restore(model_root, result, segment_config, high_price_weighting, previous_run_id)
        return summarize_train_result(result)

    return worker


def build_predict_worker(payload: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    def worker(job_id: str) -> dict[str, Any]:
        STATE.append_log(job_id, "收到预测请求", 1)
        STATE.raise_if_cancelled(job_id)
        model_root = Path(payload.get("model_root") or MODEL_ROOT)
        similarity_weights = resolve_similarity_weights(payload, model_root)
        save_training_preferences(model_root, {"similarity_weights": similarity_weights})
        result = predict_prices_compare(
            history_dir=Path(payload.get("history_dir") or HISTORY_DIR),
            forecast_file=Path(payload.get("forecast_file") or FORECAST_FILE),
            model_root=model_root,
            output_file=Path(payload.get("output_file") or OUTPUT_FILE),
            reference_days=int(payload.get("reference_days") or 1),
            selected_strategy=str(payload.get("selected_strategy") or "recent_n_days"),
            similarity_weights=similarity_weights,
            progress_callback=build_progress_callback(job_id),
        )
        summary = summarize_predict_result(result)
        metadata = load_current_metadata(model_root) or {}
        archive_result = archive_prediction_bundle(
            summary["prediction"],
            metadata,
            PREDICTION_ARCHIVE_ROOT,
            Path(payload.get("forecast_file") or FORECAST_FILE),
            Path(payload.get("output_file") or OUTPUT_FILE),
        )
        summary["prediction_archive"] = archive_result
        summary["prediction"]["archive_result"] = archive_result
        return summary

    return worker


def current_history_signature() -> dict[str, Any]:
    return build_history_source_signature(HISTORY_DIR, None, True)


def window_optimization_state() -> dict[str, Any]:
    return read_json_file(WINDOW_OPTIMIZATION_STATE_FILE)


def save_window_optimization_state(state: dict[str, Any]) -> None:
    write_json_file(WINDOW_OPTIMIZATION_STATE_FILE, state)


def path_size(path: Path) -> int:
    try:
        if not path.exists() and not path.is_symlink():
            return 0
        if path.is_file() or path.is_symlink():
            return path.stat().st_size
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    except OSError:
        return 0


def count_path_files(path: Path) -> int:
    try:
        if not path.exists() and not path.is_symlink():
            return 0
        if path.is_file() or path.is_symlink():
            return 1
        return sum(1 for item in path.rglob("*") if item.is_file())
    except OSError:
        return 0


def safe_cleanup_target(path: Path) -> Path:
    target = path.resolve()
    base = BASE_DIR.resolve()
    if base not in [target, *target.parents]:
        raise RuntimeError(f"拒绝清理项目目录外路径：{target}")
    protected = {base, MODEL_ROOT.resolve(), HISTORY_DIR.resolve(), FRONTEND_APP_DIR.resolve()}
    if target in protected:
        raise RuntimeError(f"拒绝清理受保护目录：{target}")
    return target


def retry_writable_remove(function: Callable[[str], None], path: str, _exc_info: object) -> None:
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    function(path)


def remove_cleanup_target(
    path: Path,
    label: str,
    removed: list[dict[str, Any]],
    skipped: list[dict[str, Any]] | None = None,
) -> None:
    target = safe_cleanup_target(path)
    if not target.exists() and not target.is_symlink():
        return
    size = path_size(target)
    files = count_path_files(target)
    try:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target, onerror=retry_writable_remove)
        else:
            target.chmod(stat.S_IWRITE | stat.S_IREAD)
            target.unlink(missing_ok=True)
    except (OSError, shutil.Error) as exc:
        if skipped is None:
            raise
        skipped.append(
            {
                "label": label,
                "path": str(target),
                "bytes": size,
                "files": files,
                "error": str(exc),
            }
        )
        return
    removed.append(
        {
            "label": label,
            "path": str(target),
            "bytes": size,
            "files": files,
        }
    )


def prune_quality_reports(
    report_dir: Path,
    keep_latest: int,
    removed: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> None:
    if not report_dir.exists():
        return
    reports = sorted(report_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    keep = {item.resolve() for item in reports[:keep_latest]}
    for report in reports[keep_latest:]:
        remove_cleanup_target(report, "旧数据异常报告", removed, skipped)
    for extra in report_dir.iterdir():
        if extra.resolve() in keep:
            continue
        if extra.suffix.lower() != ".json":
            remove_cleanup_target(extra, "数据异常报告目录杂项", removed, skipped)
    if report_dir.exists() and not any(report_dir.iterdir()):
        try:
            report_dir.rmdir()
        except OSError as exc:
            skipped.append(
                {
                    "label": "空数据异常报告目录",
                    "path": str(report_dir.resolve()),
                    "bytes": 0,
                    "files": 0,
                    "error": str(exc),
                }
            )


def cleanup_output_junk() -> dict[str, Any]:
    status = STATE.status()
    if status.get("running"):
        raise RuntimeError("当前有训练、寻优或预测任务正在运行，请任务结束后再清理")

    removed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    keep_quality_reports = 10
    output_file = OUTPUT_FILE.resolve()
    quality_report_dir = (OUTPUT_ROOT / "data_quality_reports").resolve()

    if OUTPUT_ROOT.exists():
        for item in list(OUTPUT_ROOT.iterdir()):
            resolved = item.resolve()
            if resolved == output_file:
                continue
            if resolved == quality_report_dir:
                prune_quality_reports(item, keep_quality_reports, removed, skipped)
                continue
            if item.name == "window_optimization":
                remove_cleanup_target(item, "自动寻优中间结果", removed, skipped)
                continue
            remove_cleanup_target(item, "output 目录杂项", removed, skipped)

    for folder_name in [".test_tmp", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__"]:
        remove_cleanup_target(BASE_DIR / folder_name, folder_name, removed, skipped)

    for log_path in [BASE_DIR / "api_server.stdout.log", BASE_DIR / "api_server.stderr.log"]:
        if log_path.exists() and log_path.stat().st_size == 0:
            remove_cleanup_target(log_path, "空日志文件", removed, skipped)

    total_bytes = sum(item["bytes"] for item in removed)
    total_files = sum(item["files"] for item in removed)
    return {
        "message": "清理完成",
        "removed": removed,
        "removed_count": len(removed),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "kept": [
            str(output_file),
            f"{quality_report_dir}（保留最新 {keep_quality_reports} 个）",
            str(MODEL_ROOT.resolve()),
        ],
    }


def mark_window_optimization_attempt(
    signature: dict[str, Any],
    reason: str,
    force: bool = False,
    payload: dict[str, Any] | None = None,
) -> None:
    state = window_optimization_state()
    max_history_days = resolve_window_optimization_max_history_days(payload)
    state.update(
        {
            "enabled": True,
            "last_attempt_at": now_text(),
            "last_attempt_reason": reason,
            "last_attempt_status": "running",
            "last_attempt_force": bool(force),
            "last_attempted_history_cache_key": signature.get("cache_key"),
            "max_search_history_days": max_history_days,
        }
    )
    save_window_optimization_state(state)


def resolve_window_optimization_max_history_days(payload: dict[str, Any] | None = None) -> int:
    payload = payload or {}
    state = window_optimization_state()
    raw_value = payload.get("max_history_days", state.get("max_search_history_days", AUTO_WINDOW_MAX_HISTORY_DAYS))
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = AUTO_WINDOW_MAX_HISTORY_DAYS
    return max(1, value)


def mark_window_optimization_attempt_status(status: str, message: str | None = None) -> None:
    state = window_optimization_state()
    state["last_attempt_status"] = status
    state["last_attempt_finished_at"] = now_text()
    if message:
        state["last_attempt_message"] = message
    save_window_optimization_state(state)


def build_window_optimization_worker_payload(
    reason: str,
    payload: dict[str, Any] | None = None,
    *,
    force: bool | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    preferences = load_training_preferences(MODEL_ROOT)

    has_segment_payload = "segment_mode" in payload or "segment_config" in payload
    has_high_price_payload = (
        "high_price_weighting" in payload
        or "high_price_weight_enabled" in payload
        or "high_price_quantile" in payload
        or "high_price_weight_multiplier" in payload
    )
    segment_source = payload if has_segment_payload else preferences
    high_price_source = payload if has_high_price_payload else preferences
    price_interval_source = payload if isinstance(payload.get("price_intervals"), list) else preferences

    worker_payload: dict[str, Any] = {
        "reason": reason,
        "max_history_days": resolve_window_optimization_max_history_days(payload),
        "valid_days": int(payload.get("valid_days") or AUTO_WINDOW_VALID_DAYS),
        "num_boost_round": int(payload.get("num_boost_round") or AUTO_WINDOW_NUM_BOOST_ROUND),
        "fine_radius": int(payload.get("fine_radius") or AUTO_WINDOW_FINE_RADIUS),
        "segment_mode": segment_source.get("segment_mode", "default"),
        "segment_config": segment_source.get("segment_config"),
        "high_price_weighting": parse_high_price_weighting_payload(high_price_source),
        "price_intervals": normalize_price_intervals(price_interval_source.get("price_intervals")),
    }
    if force is not None:
        worker_payload["force"] = force
    if payload.get("candidate_windows"):
        worker_payload["candidate_windows"] = payload.get("candidate_windows")
    return worker_payload


def normalize_segments_for_compare(segment_config: list[dict[str, object]] | None) -> list[dict[str, object]]:
    return parse_segment_config_payload(
        {
            "segment_mode": "custom",
            "segment_config": segment_config or DEFAULT_SEGMENT_CONFIG,
        }
    ) or []


def describe_training_options(segment_config: list[dict[str, object]] | None, high_price_weighting: dict[str, Any]) -> str:
    segments = normalize_segments_for_compare(segment_config)
    segment_text = " / ".join(
        f"{item.get('name')}:{item.get('start_time')}-{item.get('end_time')}"
        for item in segments
    )
    high_text = (
        f"开启，高价分位={high_price_weighting.get('quantile')}，权重倍数={high_price_weighting.get('multiplier')}"
        if high_price_weighting.get("enabled")
        else "关闭"
    )
    return f"实际训练配置：{len(segments)} 个时段（{segment_text}）；高价样本加权：{high_text}"


def validate_training_result_options(
    result: Any,
    segment_config: list[dict[str, object]] | None,
    high_price_weighting: dict[str, Any],
) -> None:
    metadata = read_json_file(Path(result.history_model_dir) / "metadata.json")
    expected_segments = normalize_segments_for_compare(segment_config)
    actual_segments = normalize_segments_for_compare(metadata.get("segment_config") or metadata.get("segments"))
    expected_mode = "custom" if segment_config else "default"
    actual_mode = str(metadata.get("segment_mode") or "default")
    if actual_mode != expected_mode or actual_segments != expected_segments:
        raise RuntimeError(
            "训练配置校验失败：模型元数据中的时段配置与本次提交配置不一致，已阻止启用该模型。"
        )

    actual_high = metadata.get("high_price_weighting") if isinstance(metadata.get("high_price_weighting"), dict) else {}
    expected_enabled = bool(high_price_weighting.get("enabled"))
    actual_enabled = bool(actual_high.get("enabled"))
    expected_quantile = float(high_price_weighting.get("quantile", 0.8))
    actual_quantile = float(actual_high.get("quantile", 0.8))
    expected_multiplier = float(high_price_weighting.get("multiplier", 2.0))
    actual_multiplier = float(actual_high.get("multiplier", 2.0))
    if (
        actual_enabled != expected_enabled
        or abs(actual_quantile - expected_quantile) > 1e-9
        or abs(actual_multiplier - expected_multiplier) > 1e-9
        or (expected_enabled and actual_high.get("threshold") is None)
    ):
        raise RuntimeError(
            "训练配置校验失败：模型元数据中的高价样本加权配置与本次提交配置不一致，已阻止启用该模型。"
        )


def validate_training_result_or_restore(
    model_root: Path,
    result: Any,
    segment_config: list[dict[str, object]] | None,
    high_price_weighting: dict[str, Any],
    previous_run_id: str | None,
) -> None:
    try:
        validate_training_result_options(result, segment_config, high_price_weighting)
    except Exception:
        if previous_run_id:
            try:
                activate_model_version(model_root, previous_run_id, persist_default=True)
            except Exception:
                pass
        raise


def build_window_optimization_worker(payload: dict[str, Any] | None = None) -> Callable[[str], dict[str, Any]]:
    payload = payload or {}

    def worker(job_id: str) -> dict[str, Any]:
        valid_days = int(payload.get("valid_days") or AUTO_WINDOW_VALID_DAYS)
        num_boost_round = int(payload.get("num_boost_round") or AUTO_WINDOW_NUM_BOOST_ROUND)
        fine_radius = int(payload.get("fine_radius") or AUTO_WINDOW_FINE_RADIUS)
        max_history_days = resolve_window_optimization_max_history_days(payload)
        segment_config = parse_segment_config_payload(payload)
        high_price_weighting = parse_high_price_weighting_payload(payload)
        STATE.append_log(job_id, describe_training_options(segment_config, high_price_weighting), 2)
        save_training_preferences(
            MODEL_ROOT,
            {
                "segment_mode": "custom" if segment_config else "default",
                "segment_config": segment_config or DEFAULT_SEGMENT_CONFIG,
                "high_price_weighting": high_price_weighting,
                "price_intervals": payload.get("price_intervals"),
            },
        )
        STATE.append_log(job_id, "开始自动训练使用天数寻优", 1)
        STATE.raise_if_cancelled(job_id)

        history_signature = current_history_signature()
        history_df, _, _, _, _ = load_cached_history_collection(HISTORY_DIR, None, True, MODEL_ROOT, leading_days=0)
        unique_dates = sorted(pd.to_datetime(history_df["date"], errors="coerce").dropna().dt.strftime("%Y-%m-%d").unique().tolist())
        if len(unique_dates) <= valid_days + 1:
            raise ValueError("历史数据天数不足，无法执行训练使用天数寻优。")
        available_train_days = len(unique_dates) - valid_days
        max_train_days = min(available_train_days, max_history_days)
        requested_candidates = payload.get("candidate_windows")
        if requested_candidates:
            candidate_windows = sorted({max(1, min(max_train_days, int(item))) for item in requested_candidates})
        else:
            candidate_windows = sorted({item for item in AUTO_WINDOW_CANDIDATES if item <= max_train_days} | {max_train_days})
            if max_train_days < 30:
                candidate_windows = sorted({1, max_train_days})
        run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        search_root = WINDOW_OPTIMIZATION_OUTPUT_ROOT / run_stamp
        search_root.mkdir(parents=True, exist_ok=True)

        results: list[dict[str, Any]] = []

        def run_window(window_days: int, phase: str, index: int, total: int, enable_rolling_backtest: bool = False) -> dict[str, Any]:
            STATE.raise_if_cancelled(job_id)
            progress = 5 + int((index - 1) / max(total, 1) * 70)
            STATE.append_log(job_id, f"{phase}窗口回测 {index}/{total}：最近 {window_days} 天", progress)
            window_model_root = search_root / f"{phase}_{window_days}"
            result = train_and_register(
                TrainConfig(
                    history_dir=HISTORY_DIR,
                    model_root=window_model_root,
                    valid_days=valid_days,
                    training_window_days=window_days,
                    num_boost_round=num_boost_round,
                    enable_rolling_backtest=enable_rolling_backtest,
                    segment_config=segment_config,
                    high_price_weight_enabled=high_price_weighting["enabled"],
                    high_price_quantile=high_price_weighting["quantile"],
                    high_price_weight_multiplier=high_price_weighting["multiplier"],
                    price_intervals=payload.get("price_intervals"),
                ),
                progress_callback=lambda _message, _percent: STATE.raise_if_cancelled(job_id),
            )
            summary = summarize_window_result(result, window_model_root, window_days, phase)
            results.append(summary)
            return summary

        total_estimated = len(candidate_windows) + fine_radius * 2 + 1
        coarse_summaries = [run_window(window, "coarse", idx, total_estimated) for idx, window in enumerate(candidate_windows, start=1)]
        finite_coarse = [item for item in coarse_summaries if item.get("score") is not None]
        if not finite_coarse:
            raise ValueError("所有候选训练使用天数均未得到有效指标。")
        best_coarse = min(finite_coarse, key=lambda item: (float(item["score"]), float((item.get("metrics") or {}).get("mae") or float("inf"))))
        best_coarse_window = int(best_coarse["window_days"])
        fine_start = max(1 if max_train_days < 30 else 30, best_coarse_window - fine_radius)
        fine_end = min(max_train_days, best_coarse_window + fine_radius)
        searched_windows = {int(row["window_days"]) for row in results}
        fine_candidates = [item for item in range(fine_start, fine_end + 1) if item not in searched_windows]
        for offset, window in enumerate(fine_candidates, start=1):
            run_window(window, "fine", len(candidate_windows) + offset, len(candidate_windows) + len(fine_candidates))

        finite_results = [item for item in results if item.get("score") is not None]
        if not finite_results:
            raise ValueError("所有候选训练使用天数均未得到有效指标。")
        static_top = sorted(
            finite_results,
            key=lambda item: (float(item["score"]), float((item.get("metrics") or {}).get("mae") or float("inf"))),
        )[:AUTO_WINDOW_RERANK_TOP_N]
        rerank_results: list[dict[str, Any]] = []
        for offset, candidate in enumerate(static_top, start=1):
            window = int(candidate["window_days"])
            STATE.append_log(job_id, f"严格滚动回测复核 {offset}/{len(static_top)}：最近 {window} 天", 76 + offset)
            rerank_results.append(
                run_window(
                    window,
                    "rerank",
                    offset,
                    max(len(static_top), 1),
                    enable_rolling_backtest=True,
                )
            )
        best_pool = [item for item in rerank_results if item.get("score") is not None] or finite_results
        best = min(best_pool, key=lambda item: (float(item["score"]), float((item.get("metrics") or {}).get("mae") or float("inf"))))
        best_window_days = int(best["window_days"])
        STATE.append_log(job_id, f"最优训练使用天数为最近 {best_window_days} 天，正在训练正式模型", 86)
        previous_metadata = load_current_metadata(MODEL_ROOT) or {}
        previous_run_id = previous_metadata.get("run_id")
        final_result = train_and_register(
            TrainConfig(
                history_dir=HISTORY_DIR,
                model_root=MODEL_ROOT,
                valid_days=valid_days,
                training_window_days=best_window_days,
                num_boost_round=num_boost_round,
                segment_config=segment_config,
                high_price_weight_enabled=high_price_weighting["enabled"],
                high_price_quantile=high_price_weighting["quantile"],
                high_price_weight_multiplier=high_price_weighting["multiplier"],
                price_intervals=payload.get("price_intervals"),
            ),
            progress_callback=lambda _message, _percent: STATE.raise_if_cancelled(job_id),
        )
        validate_training_result_or_restore(MODEL_ROOT, final_result, segment_config, high_price_weighting, previous_run_id)
        activate_model_version(MODEL_ROOT, final_result.run_id, persist_default=True)
        final_summary = summarize_train_result(final_result)
        state = {
            "enabled": True,
            "last_run_at": now_text(),
            "last_attempt_at": now_text(),
            "last_attempt_status": "success",
            "last_attempt_finished_at": now_text(),
            "last_attempted_history_cache_key": history_signature.get("cache_key"),
            "history_cache_key": history_signature.get("cache_key"),
            "history_date_start": unique_dates[0],
            "history_date_end": unique_dates[-1],
            "history_date_count": len(unique_dates),
            "available_train_days": available_train_days,
            "max_search_history_days": max_history_days,
            "valid_days": valid_days,
            "num_boost_round": num_boost_round,
            "candidate_window_start": candidate_windows[0] if candidate_windows else None,
            "candidate_window_end": candidate_windows[-1] if candidate_windows else None,
            "candidate_window_count": len(candidate_windows),
            "coarse_candidates": candidate_windows,
            "fine_radius": fine_radius,
            "fine_candidates": fine_candidates,
            "rerank_top_n": AUTO_WINDOW_RERANK_TOP_N,
            "selection_method": "rolling_backtest_rerank",
            "segment_mode": "custom" if segment_config else "default",
            "segment_config": segment_config or DEFAULT_SEGMENT_CONFIG,
            "high_price_weighting": high_price_weighting,
            "best_window_days": best_window_days,
            "best_score": best.get("score"),
            "best_static_score": best.get("static_score"),
            "best_score_detail": best.get("score_detail"),
            "best_rolling_backtest_metrics": best.get("rolling_backtest_metrics"),
            "best_metrics": {
                "no_lag_96": best.get("metrics"),
            },
            "search_root": str(search_root),
            "results": sorted(results, key=lambda item: (float(item.get("score") or float("inf")), int(item.get("window_days") or 0))),
            "final_model": final_summary,
        }
        save_window_optimization_state(state)
        STATE.append_log(job_id, f"训练使用天数寻优完成，已启用最近 {best_window_days} 天模型", 100)
        return {"window_optimization": state, "train_result": final_summary}

    return worker


def maybe_start_window_optimization(reason: str = "startup", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    state = window_optimization_state()
    try:
        signature = current_history_signature()
    except Exception as exc:  # noqa: BLE001
        return {"started": False, "reason": f"history_signature_failed: {exc}", "state": state}
    if STATE.has_running_job():
        return {"started": False, "reason": "job_running", "state": state}
    if state.get("history_cache_key") == signature.get("cache_key"):
        return {"started": False, "reason": "history_unchanged", "state": state}
    if (
        state.get("last_attempted_history_cache_key") == signature.get("cache_key")
        and state.get("last_attempt_status") == "failed"
    ):
        return {"started": False, "reason": "last_attempt_failed", "state": state}
    worker_payload = build_window_optimization_worker_payload(reason, payload)
    mark_window_optimization_attempt(signature, reason, payload=worker_payload)
    job = start_background_job("optimize", build_window_optimization_worker(worker_payload))
    return {"started": True, "job": job, "state": state}


def check_window_optimization(reason: str = "status_check", force: bool = False, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    global LAST_AUTO_WINDOW_CHECK_AT
    if not force:
        checked_at = LAST_AUTO_WINDOW_CHECK_AT
        now = datetime.now()
        if checked_at and (now - checked_at).total_seconds() < AUTO_WINDOW_CHECK_INTERVAL_SECONDS:
            return {"started": False, "reason": "throttled", "state": window_optimization_state()}
        LAST_AUTO_WINDOW_CHECK_AT = now
        return maybe_start_window_optimization(reason, payload)
    if STATE.has_running_job():
        return {"started": False, "reason": "job_running", "state": window_optimization_state()}
    LAST_AUTO_WINDOW_CHECK_AT = datetime.now()
    worker_payload = build_window_optimization_worker_payload(reason, payload, force=True)
    try:
        mark_window_optimization_attempt(current_history_signature(), reason, force=True, payload=worker_payload)
    except Exception:
        pass
    job = start_background_job("optimize", build_window_optimization_worker(worker_payload))
    return {"started": True, "job": job, "state": window_optimization_state()}


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
            if path == "/api/window-optimization/status":
                return self.send_json({"state": window_optimization_state(), "current_job": STATE.snapshot()})
            if path == "/api/model/current":
                return self.send_json({"metadata": load_current_metadata(MODEL_ROOT) or {}})
            if path == "/api/model/candidate-rankings":
                query = urllib.parse.parse_qs(parsed.query)
                metric = str((query.get("metric") or ["default_score"])[0] or "default_score")
                price_min = parse_optional_float((query.get("price_min") or [None])[0])
                price_max = parse_optional_float((query.get("price_max") or [None])[0])
                return self.send_json(rank_model_candidates(MODEL_ROOT, metric=metric, price_min=price_min, price_max=price_max))
            if path == "/api/model/versions":
                return self.send_json(self.get_versions())
            if path == "/api/training/logs":
                return self.send_json(self.get_training_logs())
            if path in {"/api/training/preferences", "/api/prediction/preferences"}:
                return self.send_json({"preferences": load_training_preferences(MODEL_ROOT)})
            if path == "/api/data-quality/reports":
                return self.send_json({"reports": list_quality_reports()})
            if path == "/api/data-quality/reports/latest":
                return self.send_json({"report": latest_quality_report()})
            if path.startswith("/api/data-quality/reports/"):
                report_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
                return self.send_json({"report": load_quality_report(report_id)})
            if path == "/api/forecast/template":
                return self.send_json(load_forecast_template_preview())
            if path == "/api/prediction/latest":
                return self.send_json({"prediction": load_latest_prediction_output()})
            if path == "/api/prediction-archive":
                query = urllib.parse.parse_qs(parsed.query)
                forecast_date = str((query.get("date") or [""])[0] or "").strip() or None
                return self.send_json({"records": list_prediction_archives(PREDICTION_ARCHIVE_ROOT, forecast_date)})
            if path.startswith("/api/prediction-archive/"):
                archive_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
                return self.send_json(
                    load_prediction_archive_detail(
                        PREDICTION_ARCHIVE_ROOT,
                        archive_id,
                        history_dir=HISTORY_DIR,
                        model_root=MODEL_ROOT,
                    )
                )
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
            if path == "/api/window-optimization/run":
                return self.send_json(check_window_optimization("manual", force=bool(payload.get("force", True)), payload=payload), HTTPStatus.ACCEPTED)
            if path == "/api/cleanup/output":
                return self.send_json(cleanup_output_junk())
            if path in {"/api/training/preferences", "/api/prediction/preferences"}:
                preference_payload: dict[str, Any] = {"similarity_weights": resolve_similarity_weights(payload, MODEL_ROOT)}
                if path == "/api/training/preferences":
                    segment_config = parse_segment_config_payload(payload)
                    preference_payload.update(
                        {
                            "segment_mode": "custom" if segment_config else "default",
                            "segment_config": segment_config or DEFAULT_SEGMENT_CONFIG,
                            "high_price_weighting": parse_high_price_weighting_payload(payload),
                            "price_intervals": parse_price_intervals_payload(payload),
                        }
                    )
                preferences = save_training_preferences(MODEL_ROOT, preference_payload)
                return self.send_json({"preferences": preferences})
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
            if path == "/api/model/segment-selection":
                metadata = update_segment_price_model_selection(MODEL_ROOT, payload.get("selected_segment_price_models") or {})
                return self.send_json({"message": "分时段预测模型已保存", "metadata": metadata})
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
        except ValueError as exc:
            return self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
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
            "default_training_mode": "rolling_window",
            "default_training_window_days": 60,
            "default_window_optimization_max_history_days": resolve_window_optimization_max_history_days(),
            "max_reference_days": 100,
            "default_similarity_weights": dict(load_training_preferences(MODEL_ROOT)["similarity_weights"]),
            "prediction_preferences": load_training_preferences(MODEL_ROOT),
            "training_preferences": load_training_preferences(MODEL_ROOT),
            "default_segment_config": DEFAULT_SEGMENT_CONFIG,
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
        status["window_optimization"] = window_optimization_state()
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
