from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from dayahead_core import (
    DEFAULT_HISTORY_DIR,
    DEFAULT_MODEL_ROOT,
    TARGET_COLUMN,
    DayAheadDataBuilder,
    calculate_metrics,
    list_excel_files_for_date_window,
    load_holiday_calendar,
    parse_sheet_date,
    summarize_prediction_errors,
)


DEFAULT_PREDICTION_ARCHIVE_ROOT = Path(__file__).resolve().parent / "output" / "prediction_archive"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if pd.isna(value):
        return None
    return value


def archive_index_path(archive_root: str | Path = DEFAULT_PREDICTION_ARCHIVE_ROOT) -> Path:
    return Path(archive_root) / "index.json"


def read_archive_index(archive_root: str | Path = DEFAULT_PREDICTION_ARCHIVE_ROOT) -> dict:
    path = archive_index_path(archive_root)
    if not path.exists():
        return {"records": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"records": []}
    return data if isinstance(data, dict) and isinstance(data.get("records"), list) else {"records": []}


def write_archive_index(archive_root: str | Path, index: dict) -> None:
    path = archive_index_path(archive_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(index), ensure_ascii=False, indent=2), encoding="utf-8")


def rounded_prediction_prices(rows: list[dict[str, Any]]) -> list[float | None]:
    result: list[float | None] = []
    ordered_rows = sorted(rows or [], key=lambda row: int(row.get("period") or 0))
    for row in ordered_rows:
        value = row.get("predicted_price")
        try:
            result.append(round(float(value), 2))
        except (TypeError, ValueError):
            result.append(None)
    return result


def prediction_fingerprint(record: dict[str, Any]) -> str:
    payload = {
        "forecast_date": record.get("forecast_date"),
        "reference_strategy_key": record.get("reference_strategy_key"),
        "reference_days_requested": record.get("reference_days_requested"),
        "model_run_id": record.get("model_run_id"),
        "selected_segment_price_models": record.get("selected_segment_price_models") or {},
        "rounded_predicted_price": rounded_prediction_prices(record.get("rows") or []),
    }
    raw = json.dumps(json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def archive_file_path(archive_root: str | Path, forecast_date: str, archive_id: str) -> Path:
    return Path(archive_root) / str(forecast_date) / f"{archive_id}.json"


def build_prediction_archive_record(
    variant: dict[str, Any],
    metadata: dict[str, Any],
    forecast_file: str | Path,
    output_file: str | Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    forecast_date = str(variant.get("forecast_date") or "")
    created_text = created_at or datetime.now().isoformat(timespec="seconds")
    segment_config = metadata.get("segment_config") or metadata.get("segments") or []
    record = {
        "forecast_date": forecast_date,
        "created_at": created_text,
        "model_run_id": metadata.get("run_id"),
        "model_type": metadata.get("model_type"),
        "selected_model_key": metadata.get("selected_model_key"),
        "selected_segment_price_models": metadata.get("selected_segment_price_models") or {},
        "segment_count": len(segment_config) if isinstance(segment_config, list) else None,
        "segment_config": segment_config,
        "reference_strategy_key": variant.get("reference_strategy_key"),
        "reference_strategy_label": variant.get("reference_strategy_label"),
        "reference_days_requested": variant.get("reference_days_requested"),
        "reference_dates": variant.get("reference_dates") or [],
        "similarity_weights": metadata.get("similarity_weights") or {},
        "price_interval_model": metadata.get("price_interval_model") or {},
        "forecast_file": str(forecast_file),
        "output_file": str(output_file),
        "rows": variant.get("rows") or [],
    }
    fingerprint = prediction_fingerprint(record)
    archive_id = f"{forecast_date}_{record['reference_strategy_key']}_{fingerprint[:12]}"
    record["fingerprint"] = fingerprint
    record["archive_id"] = archive_id
    return record


def record_summary(record: dict[str, Any], relative_path: str) -> dict[str, Any]:
    return {
        "archive_id": record.get("archive_id"),
        "forecast_date": record.get("forecast_date"),
        "created_at": record.get("created_at"),
        "model_run_id": record.get("model_run_id"),
        "reference_strategy_key": record.get("reference_strategy_key"),
        "reference_strategy_label": record.get("reference_strategy_label"),
        "reference_days_requested": record.get("reference_days_requested"),
        "segment_count": record.get("segment_count"),
        "fingerprint": record.get("fingerprint"),
        "path": relative_path,
    }


def save_prediction_archive_record(record: dict[str, Any], archive_root: str | Path = DEFAULT_PREDICTION_ARCHIVE_ROOT) -> dict[str, Any]:
    archive_root = Path(archive_root)
    index = read_archive_index(archive_root)
    for existing in index["records"]:
        if existing.get("forecast_date") == record.get("forecast_date") and existing.get("fingerprint") == record.get("fingerprint"):
            return {"saved": False, "duplicate": existing}
    path = archive_file_path(archive_root, str(record["forecast_date"]), str(record["archive_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(record), ensure_ascii=False, indent=2), encoding="utf-8")
    relative_path = str(path.relative_to(archive_root))
    summary = record_summary(record, relative_path)
    index["records"].append(summary)
    index["records"].sort(key=lambda item: (str(item.get("forecast_date") or ""), str(item.get("created_at") or "")), reverse=True)
    write_archive_index(archive_root, index)
    return {"saved": True, "record": summary}


def archive_prediction_bundle(
    prediction: dict[str, Any],
    metadata: dict[str, Any],
    archive_root: str | Path = DEFAULT_PREDICTION_ARCHIVE_ROOT,
    forecast_file: str | Path = "",
    output_file: str | Path = "",
) -> dict[str, Any]:
    comparisons = prediction.get("comparison_predictions") if isinstance(prediction.get("comparison_predictions"), dict) else {}
    if not comparisons:
        comparisons = {prediction.get("reference_strategy_key") or "selected": prediction}
    saved: list[dict[str, Any]] = []
    skipped_duplicates: list[dict[str, Any]] = []
    created_at = datetime.now().isoformat(timespec="seconds")
    for variant in comparisons.values():
        record = build_prediction_archive_record(variant, metadata, forecast_file, output_file, created_at=created_at)
        result = save_prediction_archive_record(record, archive_root)
        if result["saved"]:
            saved.append(result["record"])
        else:
            skipped_duplicates.append(result["duplicate"])
    return {"saved": saved, "skipped_duplicates": skipped_duplicates}


def list_prediction_archives(archive_root: str | Path = DEFAULT_PREDICTION_ARCHIVE_ROOT, forecast_date: str | None = None) -> list[dict[str, Any]]:
    records = read_archive_index(archive_root)["records"]
    if forecast_date:
        records = [record for record in records if record.get("forecast_date") == forecast_date]
    return sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def load_archive_record(archive_root: str | Path, archive_id: str) -> dict[str, Any]:
    index = read_archive_index(archive_root)
    match = next((record for record in index["records"] if record.get("archive_id") == archive_id), None)
    if not match:
        raise FileNotFoundError(f"未找到预测归档记录：{archive_id}")
    path = Path(archive_root) / str(match["path"])
    return json.loads(path.read_text(encoding="utf-8"))


def load_actual_prices_for_date(
    forecast_date: str,
    history_dir: str | Path = DEFAULT_HISTORY_DIR,
    model_root: str | Path = DEFAULT_MODEL_ROOT,
    holiday_file: str | Path | None = None,
) -> pd.DataFrame:
    history_path = Path(history_dir)
    if not history_path.exists():
        return pd.DataFrame()
    target_date = pd.Timestamp(forecast_date).normalize()
    try:
        calendar = load_holiday_calendar(holiday_file) if holiday_file else set()
        builder = DayAheadDataBuilder(calendar)
        excel_files = list_excel_files_for_date_window(history_path, target_date, target_date)
    except Exception:
        return pd.DataFrame()
    for file_path in excel_files:
        try:
            workbook = pd.ExcelFile(file_path)
        except Exception:
            continue
        try:
            matching_sheets = [sheet_name for sheet_name in workbook.sheet_names if parse_sheet_date(str(sheet_name)) == target_date]
            for sheet_name in matching_sheets:
                try:
                    raw_df = pd.read_excel(workbook, sheet_name=sheet_name)
                    day_df = builder.prepare_single_sheet(raw_df, file_path, str(sheet_name), target_date, require_target=True)
                except Exception:
                    continue
                if day_df.empty:
                    continue
                return (
                    day_df[["period", TARGET_COLUMN]]
                    .rename(columns={TARGET_COLUMN: "actual_price"})
                    .sort_values("period")
                    .reset_index(drop=True)
                )
        finally:
            workbook.close()
    return pd.DataFrame()


def compare_archive_with_actual(record: dict[str, Any], actual_df: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    prediction_df = pd.DataFrame(record.get("rows") or [])
    if prediction_df.empty:
        return [], None
    prediction_df["period"] = pd.to_numeric(prediction_df["period"], errors="coerce").astype("Int64")
    if actual_df.empty:
        rows = prediction_df.sort_values("period").to_dict(orient="records")
        return json_safe(rows), None
    merged = prediction_df.merge(actual_df, on="period", how="left").sort_values("period")
    metric_df = pd.DataFrame(
        {
            "date": merged.get("date", record.get("forecast_date")),
            "period": merged["period"],
            "actual": pd.to_numeric(merged["actual_price"], errors="coerce"),
            "predicted": pd.to_numeric(merged["predicted_price"], errors="coerce"),
        }
    ).dropna(subset=["actual", "predicted"])
    if metric_df.empty:
        return json_safe(merged.to_dict(orient="records")), None
    metrics = summarize_prediction_errors(metric_df)
    return json_safe(merged.to_dict(orient="records")), metrics


def load_prediction_archive_detail(
    archive_root: str | Path,
    archive_id: str,
    history_dir: str | Path = DEFAULT_HISTORY_DIR,
    model_root: str | Path = DEFAULT_MODEL_ROOT,
    holiday_file: str | Path | None = None,
) -> dict[str, Any]:
    record = load_archive_record(archive_root, archive_id)
    actual_df = load_actual_prices_for_date(record["forecast_date"], history_dir, model_root, holiday_file)
    rows, metrics = compare_archive_with_actual(record, actual_df)
    actual_available = not actual_df.empty and metrics is not None
    return {
        "record": record,
        "rows": rows,
        "metrics": metrics,
        "actual_available": bool(actual_available),
        "message": None if actual_available else "暂无实际价格数据",
    }
