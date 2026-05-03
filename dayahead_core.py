from __future__ import annotations

import json
import hashlib
import pickle
import re
import shutil
import warnings
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from data_quality import (
    DataQualityIssue,
    DataQualityValidationError,
    has_blocking_issues,
    save_quality_report,
    validate_forecast_template,
    validate_history_sheet,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_HISTORY_DIR = BASE_DIR / "数据"
DEFAULT_MODEL_ROOT = BASE_DIR / "models"
DEFAULT_OUTPUT_FILE = BASE_DIR / "output" / "dayahead_price_prediction.xlsx"
DEFAULT_FORECAST_FILE = BASE_DIR / "预测文件" / "预测文件.xlsx"
PRICE_FLOOR = 0.0
PRICE_CAP = 1500.0
HISTORY_CACHE_VERSION = 2

TARGET_COLUMN = "日前出清价格(元/MWh)"
SIMILAR_PRICE_COLUMN = "similar_price"
SIMILAR_GAP_COLUMN = "similar_gap"
NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN = "net_load_only_similar_price"
NET_LOAD_ONLY_SIMILAR_GAP_COLUMN = "net_load_only_similar_gap"
RESIDUAL_TARGET_COLUMN = "residual_target"
TOTAL_LOAD_COLUMN = "total_load"
RENEWABLE_POWER_COLUMN = "renewable_power"
DAY_TYPE_COLUMN = "day_type"
THERMAL_SPACE_WEIGHT_KEY = "thermal_space"
THERMAL_SPACE_LOAD_RATIO_COLUMN = "thermal_space_load_ratio"
DEFAULT_SIMILARITY_REFERENCE_DAYS = 100
MULTICONDITION_SIMILARITY_WEIGHTS = OrderedDict(
    [
        (THERMAL_SPACE_WEIGHT_KEY, 0.45),
        (RENEWABLE_POWER_COLUMN, 0.15),
        ("thermal_on_capacity", 0.20),
        (DAY_TYPE_COLUMN, 0.10),
        (THERMAL_SPACE_LOAD_RATIO_COLUMN, 0.10),
    ]
)
SIMILARITY_WEIGHT_COLUMN_MAP = {
    THERMAL_SPACE_WEIGHT_KEY: "net_load",
    RENEWABLE_POWER_COLUMN: RENEWABLE_POWER_COLUMN,
    "thermal_on_capacity": "thermal_on_capacity",
    DAY_TYPE_COLUMN: DAY_TYPE_COLUMN,
    THERMAL_SPACE_LOAD_RATIO_COLUMN: THERMAL_SPACE_LOAD_RATIO_COLUMN,
}
SIMILARITY_WEIGHT_ALIASES = {
    "net_load": THERMAL_SPACE_WEIGHT_KEY,
    "thermal_space": THERMAL_SPACE_WEIGHT_KEY,
}
FEATURE_COLUMNS = [
    "net_load",
    "thermal_on_capacity",
    "hour",
    "period",
    "weekday",
    "month",
    "is_weekend",
    "is_holiday",
    "lag_96",
    SIMILAR_PRICE_COLUMN,
    SIMILAR_GAP_COLUMN,
]
LAG_96_COLUMN = "lag_96"
REFERENCE_STRATEGIES = OrderedDict(
    [
        ("recent_n_days", "最近 N 天"),
        ("recent_same_type_days", "最近 N 个同类型日"),
    ]
)
SEGMENTS = OrderedDict(
    [
        ("night", (1, 24)),
        ("morning_peak", (25, 40)),
        ("midday", (41, 60)),
        ("evening_peak", (61, 80)),
        ("late_night", (81, 96)),
    ]
)
DEFAULT_XGB_PARAMS = {
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "eta": 0.05,
    "max_depth": 5,
    "min_child_weight": 3,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "seed": 42,
}


@dataclass
class TrainConfig:
    history_dir: Path = DEFAULT_HISTORY_DIR
    model_root: Path = DEFAULT_MODEL_ROOT
    holiday_file: Path | None = None
    valid_days: int = 14
    num_boost_round: int = 400
    start_date: str | None = None
    end_date: str | None = None
    similarity_reference_days: int = DEFAULT_SIMILARITY_REFERENCE_DAYS
    use_lag_96: bool = True
    similarity_weights: dict[str, float] | None = None


@dataclass
class TrainResult:
    run_id: str
    current_model_dir: Path
    history_model_dir: Path
    metrics: dict[str, dict[str, float | int | None]]
    train_dates: list[str]
    valid_dates: list[str]
    skipped_sheets: list[str]
    metadata_path: Path
    quality_report_path: Path | None = None


@dataclass
class PredictResult:
    forecast_date: str
    output_file: Path
    template_updated: bool
    reference_strategy_key: str
    reference_strategy_label: str
    reference_days_requested: int
    reference_dates: list[str]
    result_df: pd.DataFrame
    quality_report_path: Path | None = None


@dataclass
class PredictCompareResult:
    forecast_date: str
    output_file: Path
    template_updated: bool
    selected_strategy_key: str
    selected_strategy_label: str
    strategy_results: dict[str, PredictResult]
    quality_report_path: Path | None = None


ProgressCallback = Callable[[str, int | None], None]


def ensure_xgboost_available() -> None:
    try:
        import xgboost  # noqa: F401
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("缺少 xgboost，请先执行: pip install xgboost") from exc


def emit_progress(callback: ProgressCallback | None, message: str, percent: int | None = None) -> None:
    if callback is not None:
        callback(message, percent)


def normalize_reference_days(reference_days: int | None) -> int:
    value = int(reference_days or 1)
    if value <= 0:
        raise ValueError("reference_days 必须大于等于 1")
    return value


def normalize_reference_strategy(reference_strategy: str | None) -> str:
    strategy_key = str(reference_strategy or "recent_n_days").strip() or "recent_n_days"
    if strategy_key not in REFERENCE_STRATEGIES:
        raise ValueError(f"不支持的参考日策略: {strategy_key}")
    return strategy_key


def training_feature_columns(config: TrainConfig | None = None) -> list[str]:
    use_lag_96 = True if config is None else bool(config.use_lag_96)
    if use_lag_96:
        return list(FEATURE_COLUMNS)
    return [column for column in FEATURE_COLUMNS if column != LAG_96_COLUMN]


def model_requires_lag_96(metadata: dict) -> bool:
    return LAG_96_COLUMN in (metadata.get("feature_columns") or FEATURE_COLUMNS)


def normalize_similarity_weights(
    similarity_weights: dict[str, object] | None = None,
    fill_missing_with_defaults: bool = True,
) -> OrderedDict[str, float]:
    if similarity_weights is None:
        return OrderedDict((key, float(value)) for key, value in MULTICONDITION_SIMILARITY_WEIGHTS.items())
    weights = OrderedDict(
        (key, float(value) if fill_missing_with_defaults else 0.0)
        for key, value in MULTICONDITION_SIMILARITY_WEIGHTS.items()
    )
    for raw_key, value in similarity_weights.items():
        key = SIMILARITY_WEIGHT_ALIASES.get(str(raw_key), str(raw_key))
        if key not in weights:
            raise ValueError(f"不支持的相似法权重字段: {raw_key}")
        numeric_value = float(value)
        if not np.isfinite(numeric_value) or numeric_value < 0:
            raise ValueError(f"相似法权重 {key} 必须是大于等于 0 的数字")
        weights[key] = numeric_value
    if sum(weights.values()) <= 0:
        raise ValueError("相似法权重总和必须大于 0")
    return weights


def normalize_text(text: object) -> str:
    return re.sub(r"\s+", "", str(text)).strip().lower()


def list_excel_files(source: str | Path) -> list[Path]:
    path = Path(source)
    if path.is_file():
        return [path]
    files = sorted(
        [
            file
            for file in [*path.rglob("*.xlsx"), *path.rglob("*.xls")]
            if not file.name.startswith("~$")
        ]
    )
    if not files:
        raise FileNotFoundError(f"未在 {path} 下找到 Excel 文件")
    return files


def parse_optional_date(value: str | Path | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    return pd.Timestamp(timestamp).normalize()


def excel_file_month(file_path: str | Path) -> pd.Timestamp | None:
    path = Path(file_path)
    candidates = [path.stem, path.name, *[part for part in path.parts[-3:]]]
    for text in candidates:
        match = re.search(r"(20\d{2})\s*年?\D{0,8}(1[0-2]|0?[1-9])\s*月?", str(text))
        if match:
            return pd.Timestamp(year=int(match.group(1)), month=int(match.group(2)), day=1)
    year_value = None
    month_value = None
    for part in reversed(path.parts):
        year_match = re.search(r"(20\d{2})\s*年", part)
        month_match = re.search(r"(1[0-2]|0?[1-9])\s*月", part)
        if year_match and year_value is None:
            year_value = int(year_match.group(1))
        if month_match and month_value is None:
            month_value = int(month_match.group(1))
        if year_value is not None and month_value is not None:
            return pd.Timestamp(year=year_value, month=month_value, day=1)
    return None


def list_excel_files_for_date_window(
    source: str | Path,
    start_date: str | pd.Timestamp | None,
    end_date: str | pd.Timestamp | None,
    leading_days: int = 0,
) -> list[Path]:
    path = Path(source)
    files = list_excel_files(path)
    if path.is_file():
        return files
    window_start = parse_optional_date(start_date)
    window_end = parse_optional_date(end_date)
    if window_start is None and window_end is None:
        return files
    if window_start is not None and leading_days > 0:
        window_start = window_start - pd.Timedelta(days=leading_days)
    selected: list[Path] = []
    unknown: list[Path] = []
    for file_path in files:
        month_start = excel_file_month(file_path)
        if month_start is None:
            unknown.append(file_path)
            continue
        month_end = month_start + pd.offsets.MonthEnd(0)
        if window_start is not None and month_end < window_start:
            continue
        if window_end is not None and month_start > window_end:
            continue
        selected.append(file_path)
    scoped_files = [*selected, *unknown]
    if not scoped_files:
        raise FileNotFoundError(f"未找到覆盖日期范围的历史 Excel 文件: {source}")
    return sorted(scoped_files)


def build_history_source_signature(
    source: str | Path,
    holiday_file: str | Path | None,
    require_target: bool,
    excel_files: list[Path] | None = None,
    scope: dict | None = None,
) -> dict:
    source_path = Path(source).resolve()
    files = []
    for file_path in (excel_files if excel_files is not None else list_excel_files(source_path)):
        stat = file_path.stat()
        files.append(
            {
                "path": str(file_path.resolve()),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    holiday_signature = None
    if holiday_file:
        holiday_path = Path(holiday_file).resolve()
        holiday_stat = holiday_path.stat()
        holiday_signature = {
            "path": str(holiday_path),
            "size": holiday_stat.st_size,
            "mtime_ns": holiday_stat.st_mtime_ns,
        }
    payload = {
        "version": HISTORY_CACHE_VERSION,
        "source": str(source_path),
        "require_target": bool(require_target),
        "files": files,
        "holiday_file": holiday_signature,
        "scope": scope or {},
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload["cache_key"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return payload


def derived_cache_key(source_key: str, namespace: str) -> str:
    raw = json.dumps(
        {
            "version": HISTORY_CACHE_VERSION,
            "source_key": source_key,
            "namespace": namespace,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def dataframe_cache_path(cache_dir: str | Path, cache_name: str, cache_key: str) -> Path:
    return Path(cache_dir) / f"{cache_name}_{cache_key}.pkl"


def load_dataframe_cache(cache_dir: str | Path, cache_name: str, cache_key: str) -> tuple[pd.DataFrame, list[str]] | None:
    cache_path = dataframe_cache_path(cache_dir, cache_name, cache_key)
    if not cache_path.exists():
        return None
    try:
        with cache_path.open("rb") as handle:
            payload = pickle.load(handle)
    except (OSError, pickle.PickleError, EOFError, AttributeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != HISTORY_CACHE_VERSION or payload.get("cache_key") != cache_key:
        return None
    frame = payload.get("frame")
    if not isinstance(frame, pd.DataFrame):
        return None
    skipped_sheets = payload.get("skipped_sheets") or []
    if not isinstance(skipped_sheets, list):
        skipped_sheets = []
    return frame.copy(), [str(item) for item in skipped_sheets]


def save_dataframe_cache(cache_dir: str | Path, cache_name: str, cache_key: str, frame: pd.DataFrame, skipped_sheets: list[str]) -> None:
    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path = dataframe_cache_path(cache_root, cache_name, cache_key)
    temp_path = cache_path.with_suffix(".tmp")
    payload = {
        "version": HISTORY_CACHE_VERSION,
        "cache_key": cache_key,
        "frame": frame,
        "skipped_sheets": skipped_sheets,
    }
    with temp_path.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    temp_path.replace(cache_path)


def quality_report_status(issues: list[DataQualityIssue], blocked: bool = False) -> str:
    if blocked:
        return "blocked"
    if issues:
        return "completed_with_issues"
    return "clean"


def load_cached_history_collection(
    history_dir: str | Path,
    holiday_file: str | Path | None,
    require_target: bool,
    model_root: str | Path,
    progress_callback: ProgressCallback | None = None,
    progress_start: int | None = None,
    progress_end: int | None = None,
    progress_label: str = "正在加载历史数据",
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    leading_days: int = 0,
) -> tuple[pd.DataFrame, list[str], set[pd.Timestamp], dict, list[DataQualityIssue]]:
    holiday_dates = load_holiday_calendar(holiday_file)
    scoped_files = list_excel_files_for_date_window(history_dir, start_date, end_date, leading_days=leading_days)
    scope = {
        "start_date": str(parse_optional_date(start_date).date()) if parse_optional_date(start_date) is not None else None,
        "end_date": str(parse_optional_date(end_date).date()) if parse_optional_date(end_date) is not None else None,
        "leading_days": int(leading_days or 0),
    }
    signature = build_history_source_signature(history_dir, holiday_file, require_target, excel_files=scoped_files, scope=scope)
    cache_dir = Path(model_root) / "cache"
    cached = load_dataframe_cache(cache_dir, "history_raw", signature["cache_key"])
    if cached is not None:
        emit_progress(progress_callback, "历史数据未变化，已复用缓存", progress_end)
        cached_frame, skipped_sheets = cached
        return cached_frame, skipped_sheets, holiday_dates, signature, []

    builder = DayAheadDataBuilder(holiday_dates)
    try:
        history_df = builder.load_excel_collection(
            history_dir,
            require_target=require_target,
            progress_callback=progress_callback,
            progress_start=progress_start,
            progress_end=progress_end,
            progress_label=progress_label,
            excel_files=scoped_files,
        )
    except ValueError as exc:
        if builder.quality_issues:
            raise DataQualityValidationError(str(exc), builder.quality_issues) from exc
        raise
    save_dataframe_cache(cache_dir, "history_raw", signature["cache_key"], history_df, builder.skipped_sheets)
    return history_df, builder.skipped_sheets, holiday_dates, signature, builder.quality_issues


def to_numeric(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("，", "", regex=False)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan, "None": np.nan, "--": np.nan, "-": np.nan})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def calculate_thermal_space_load_ratio(thermal_space: pd.Series, total_load: pd.Series) -> pd.Series:
    ratio = pd.to_numeric(thermal_space, errors="coerce") / pd.to_numeric(total_load, errors="coerce").replace(0, np.nan)
    return ratio.replace([np.inf, -np.inf], np.nan)


def load_holiday_calendar(holiday_file: str | Path | None) -> dict[pd.Timestamp, str]:
    if not holiday_file:
        return {}
    holiday_path = Path(holiday_file)
    if not holiday_path.exists():
        raise FileNotFoundError(f"节假日文件不存在: {holiday_path}")
    if holiday_path.suffix.lower() == ".csv":
        holiday_df = pd.read_csv(holiday_path)
    else:
        holiday_df = pd.read_excel(holiday_path)
    if holiday_df.empty:
        return {}
    date_series = holiday_df["date"] if "date" in holiday_df.columns else holiday_df.iloc[:, 0]
    parsed_dates = pd.to_datetime(date_series, errors="coerce").dt.normalize()
    if "type" in holiday_df.columns:
        type_series = holiday_df["type"].astype(str).str.strip().str.lower()
    else:
        type_series = pd.Series(["holiday"] * len(holiday_df), index=holiday_df.index)
    calendar: dict[pd.Timestamp, str] = {}
    for date_value, type_value in zip(parsed_dates, type_series):
        if pd.isna(date_value):
            continue
        normalized_type = str(type_value).strip().lower()
        if normalized_type in {"holiday", "节假日", "法定节假日", "休息日"}:
            calendar[pd.Timestamp(date_value)] = "holiday"
        elif normalized_type in {"workday", "working_day", "调休上班", "工作日"}:
            calendar[pd.Timestamp(date_value)] = "workday"
    return calendar


def load_holiday_dates(holiday_file: str | Path | None) -> set[pd.Timestamp]:
    return {date_value for date_value, day_type in load_holiday_calendar(holiday_file).items() if day_type == "holiday"}


def day_type_of(date_value: pd.Timestamp, holiday_dates: set[pd.Timestamp] | dict[pd.Timestamp, str]) -> str:
    normalized = pd.Timestamp(date_value).normalize()
    if isinstance(holiday_dates, dict):
        override = holiday_dates.get(normalized)
        if override in {"holiday", "workday"}:
            return override
    elif normalized in holiday_dates:
        return "holiday"
    if normalized.weekday() >= 5:
        return "weekend"
    return "workday"


def resolve_column(columns: Iterable[object], candidates: list[str], required: bool) -> str | None:
    normalized = {normalize_text(column): str(column) for column in columns}
    for candidate in candidates:
        key = normalize_text(candidate)
        if key in normalized:
            return normalized[key]
    for candidate in candidates:
        key = normalize_text(candidate)
        for normalized_name, original_name in normalized.items():
            if key in normalized_name or normalized_name in key:
                return original_name
    if required:
        raise KeyError(f"未找到字段: {candidates}")
    return None


def parse_sheet_date(sheet_name: str) -> pd.Timestamp | None:
    match = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", sheet_name)
    if match:
        year, month, day = map(int, match.groups())
        return pd.Timestamp(year=year, month=month, day=day).normalize()
    parsed = pd.to_datetime(sheet_name, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.normalize()


def infer_date_from_header(columns: Iterable[object], default_year: int) -> pd.Timestamp | None:
    for column in columns:
        text = str(column).strip()
        if not text or normalize_text(text).startswith("unnamed:"):
            continue
        match = re.search(r"(?<!\d)(\d{1,2})[./月-](\d{1,2})日?(?!\d)", text)
        if not match:
            continue
        month, day = map(int, match.groups())
        return pd.Timestamp(year=default_year, month=month, day=day).normalize()
    return None


def extract_month_day(text: object) -> tuple[int, int] | None:
    match = re.search(r"(?<!\d)(\d{1,2})[./月-](\d{1,2})日?(?!\d)", str(text).strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def convert_capacity_to_mw(value: float, unit: str | None) -> float:
    normalized_unit = (unit or "MW").lower()
    if normalized_unit == "gw":
        return value * 1000
    if normalized_unit in {"kw", "千瓦"}:
        return value / 1000
    if normalized_unit in {"万千瓦", "万kw", "万kw", "万kW".lower()}:
        return value * 10
    return value


def extract_thermal_on_capacity(text: object) -> float:
    if pd.isna(text):
        return np.nan
    content = str(text)
    patterns = [
        r"火电开机容量[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*(万千瓦|万kw|万kW|MW|mw|GW|gw|kW|kw|KW)?",
        r"运行机组容量[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*(万千瓦|万kw|万kW|MW|mw|GW|gw|kW|kw|KW)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, content)
        if not match:
            continue
        return convert_capacity_to_mw(float(match.group(1)), match.group(2))
    return np.nan


def assign_segments(periods: pd.Series) -> pd.Series:
    segment = pd.Series(index=periods.index, dtype="object")
    for name, (start, end) in SEGMENTS.items():
        segment.loc[periods.between(start, end)] = name
    if segment.isna().any():
        invalid = periods[segment.isna()].tolist()
        raise ValueError(f"存在无效 period: {invalid[:5]}")
    return segment


class DayAheadDataBuilder:
    def __init__(self, holiday_dates: set[pd.Timestamp] | None = None) -> None:
        self.holiday_dates = holiday_dates or set()
        self.skipped_sheets: list[str] = []
        self.quality_issues: list[DataQualityIssue] = []

    def load_excel_collection(
        self,
        source: str | Path,
        require_target: bool,
        progress_callback: ProgressCallback | None = None,
        progress_start: int | None = None,
        progress_end: int | None = None,
        progress_label: str = "正在读取数据",
        excel_files: list[Path] | None = None,
    ) -> pd.DataFrame:
        all_days: list[pd.DataFrame] = []
        self.skipped_sheets = []
        self.quality_issues = []
        excel_files = excel_files if excel_files is not None else list_excel_files(source)
        total_files = len(excel_files)
        for file_index, file_path in enumerate(excel_files, start=1):
            if progress_callback is not None and progress_start is not None and progress_end is not None and total_files > 0:
                percent = progress_start + int((file_index - 1) / total_files * max(progress_end - progress_start, 1))
                emit_progress(progress_callback, f"{progress_label} {file_index}/{total_files}: {file_path.name}", percent)
            workbook = pd.read_excel(file_path, sheet_name=None)
            for sheet_name, raw_df in workbook.items():
                trade_date = parse_sheet_date(str(sheet_name))
                if trade_date is None:
                    self.quality_issues.append(
                        DataQualityIssue(
                            task_type="train",
                            severity="error",
                            action="skipped",
                            issue_type="unrecognized_sheet_date",
                            file_path=str(file_path),
                            sheet_name=str(sheet_name),
                            message="Sheet 名称无法识别为日期",
                        )
                    )
                    if require_target:
                        self.skipped_sheets.append(f"{file_path.name} | {sheet_name} | Sheet 名称无法识别为日期")
                    continue
                validation_issues = validate_history_sheet(
                    raw_df,
                    file_path=file_path,
                    sheet_name=str(sheet_name),
                    trade_date=trade_date,
                    require_target=require_target,
                )
                self.quality_issues.extend(validation_issues)
                if has_blocking_issues(validation_issues):
                    if require_target:
                        first_issue = validation_issues[0]
                        self.skipped_sheets.append(f"{file_path.name} | {sheet_name} | {first_issue.message}")
                        continue
                    raise DataQualityValidationError("历史数据存在关键字段异常", validation_issues)
                try:
                    day_df = self.prepare_single_sheet(raw_df, file_path, str(sheet_name), trade_date, require_target)
                    all_days.append(day_df)
                except (KeyError, ValueError) as exc:
                    self.quality_issues.append(
                        DataQualityIssue(
                            task_type="train",
                            severity="error",
                            action="skipped" if require_target else "blocked",
                            issue_type="parse_error",
                            file_path=str(file_path),
                            sheet_name=str(sheet_name),
                            date=trade_date.strftime("%Y-%m-%d"),
                            message=str(exc),
                        )
                    )
                    if require_target:
                        self.skipped_sheets.append(f"{file_path.name} | {sheet_name} | {exc}")
                        continue
                    raise
        if not all_days:
            raise ValueError(f"未解析到可用的日级 Sheet: {source}")
        if self.skipped_sheets:
            preview = "\n".join(f"  - {item}" for item in self.skipped_sheets[:10])
            warnings.warn(
                f"训练数据中跳过了 {len(self.skipped_sheets)} 个异常 Sheet，这些 Sheet 缺少关键字段或数据不完整：\n{preview}",
                stacklevel=2,
            )
        return pd.concat(all_days, ignore_index=True).sort_values(["date", "period"]).reset_index(drop=True)

    def prepare_single_sheet(
        self,
        raw_df: pd.DataFrame,
        file_path: Path,
        sheet_name: str,
        trade_date: pd.Timestamp,
        require_target: bool,
    ) -> pd.DataFrame:
        day_df = raw_df.copy().iloc[:96].reset_index(drop=True)
        if len(day_df) < 96:
            raise ValueError(f"{file_path.name} - {sheet_name} 不是 96 行时段数据")
        day_df.columns = [str(column).strip() for column in day_df.columns]

        total_power_col = resolve_column(day_df.columns, ["总加电力值(MW)", "总加电力值"], required=True)
        power_col = resolve_column(day_df.columns, ["电力值(MW)", "电力值"], required=True)
        target_col = resolve_column(
            day_df.columns,
            ["日前出清价格(元/MWh)", "日前-出清价格(元/MWh)", "日前出清价格", "出清价格"],
            required=require_target,
        )
        overview_col = resolve_column(day_df.columns, ["日前-出清概况", "日前出清概况", "出清概况"], required=False)

        overview_series = pd.Series([np.nan] * len(day_df))
        thermal_series = pd.Series([np.nan] * len(day_df))
        if overview_col:
            overview_series = day_df[overview_col].ffill().bfill()
            thermal_series = overview_series.map(extract_thermal_on_capacity)

        periods = np.arange(1, 97)
        date_value = trade_date.normalize()
        day_type = day_type_of(date_value, self.holiday_dates)
        total_load = to_numeric(day_df[total_power_col])
        renewable_power = to_numeric(day_df[power_col])
        thermal_space = total_load - renewable_power
        result = pd.DataFrame(
            {
                "date": date_value,
                "period": periods,
                "hour": ((periods - 1) // 4).astype(int),
                "weekday": int(date_value.weekday()),
                "month": int(date_value.month),
                "is_weekend": int(day_type == "weekend"),
                "is_holiday": int(day_type == "holiday"),
                DAY_TYPE_COLUMN: day_type,
                TOTAL_LOAD_COLUMN: total_load,
                "net_load": thermal_space,
                RENEWABLE_POWER_COLUMN: renewable_power,
                THERMAL_SPACE_LOAD_RATIO_COLUMN: calculate_thermal_space_load_ratio(thermal_space, total_load),
                "thermal_on_capacity": to_numeric(thermal_series),
                "overview_text": overview_series,
                "sheet_name": sheet_name,
                "source_file": str(file_path),
            }
        )
        result["segment"] = assign_segments(result["period"])
        if target_col:
            result[TARGET_COLUMN] = to_numeric(day_df[target_col])
        return result


def split_train_valid(data: pd.DataFrame, valid_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if valid_days <= 0:
        return data, data.iloc[0:0].copy()
    unique_dates = sorted(pd.to_datetime(data["date"]).drop_duplicates().tolist())
    if len(unique_dates) <= valid_days:
        return data, data.iloc[0:0].copy()
    valid_dates = set(unique_dates[-valid_days:])
    valid_df = data[data["date"].isin(valid_dates)].copy()
    train_df = data[~data["date"].isin(valid_dates)].copy()
    if train_df.empty or valid_df.empty:
        return data, data.iloc[0:0].copy()
    return train_df, valid_df


def calculate_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    errors = actual - predicted
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    return {"mae": round(mae, 4), "rmse": round(rmse, 4)}


def nearest_similarity_price(target_loads: np.ndarray, ref_loads: np.ndarray, ref_prices: np.ndarray, k: int = 3) -> tuple[np.ndarray, np.ndarray]:
    if len(ref_loads) == 0:
        return np.full(len(target_loads), np.nan), np.full(len(target_loads), np.nan)
    ref_loads = ref_loads.astype(float)
    ref_prices = ref_prices.astype(float)
    target_loads = target_loads.astype(float)
    diff = np.abs(target_loads[:, None] - ref_loads[None, :])
    top_k = min(k, len(ref_loads))
    indices = np.argpartition(diff, top_k - 1, axis=1)[:, :top_k]
    top_diff = np.take_along_axis(diff, indices, axis=1)
    top_price = ref_prices[indices]
    weights = 1.0 / (top_diff + 1e-6)
    weighted_price = np.sum(weights * top_price, axis=1) / np.sum(weights, axis=1)
    min_gap = top_diff.min(axis=1)
    return weighted_price, min_gap


def normalize_similarity_reference_days(reference_days: int | None) -> int:
    value = int(reference_days or DEFAULT_SIMILARITY_REFERENCE_DAYS)
    if value <= 0:
        raise ValueError("similarity_reference_days 必须大于等于 1")
    return value


def day_type_penalty(target_type: object, reference_types: pd.Series) -> pd.Series:
    target_text = str(target_type or "").strip().lower()
    reference_text = reference_types.astype(str).str.strip().str.lower()
    return (reference_text != target_text).astype(float)


def normalized_numeric_gap(target_value: object, reference_values: pd.Series) -> pd.Series:
    numeric_reference = pd.to_numeric(reference_values, errors="coerce")
    numeric_target = pd.to_numeric(pd.Series([target_value]), errors="coerce").iloc[0]
    if pd.isna(numeric_target):
        return pd.Series(np.nan, index=reference_values.index, dtype=float)
    normalizer = max(float(abs(numeric_target)), float(numeric_reference.abs().median(skipna=True) or 0.0), 1.0)
    return (numeric_reference - float(numeric_target)).abs() / normalizer


def ensure_similarity_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if TOTAL_LOAD_COLUMN not in result.columns:
        result[TOTAL_LOAD_COLUMN] = np.nan
    if RENEWABLE_POWER_COLUMN not in result.columns:
        result[RENEWABLE_POWER_COLUMN] = np.nan
    if "thermal_on_capacity" not in result.columns:
        result["thermal_on_capacity"] = np.nan
    if THERMAL_SPACE_LOAD_RATIO_COLUMN not in result.columns:
        thermal_space = result["net_load"] if "net_load" in result.columns else pd.Series([np.nan] * len(result), index=result.index)
        result[THERMAL_SPACE_LOAD_RATIO_COLUMN] = calculate_thermal_space_load_ratio(thermal_space, result[TOTAL_LOAD_COLUMN])
    if DAY_TYPE_COLUMN not in result.columns:
        if "date" in result.columns:
            result[DAY_TYPE_COLUMN] = pd.to_datetime(result["date"], errors="coerce").map(lambda value: day_type_of(value, set()) if pd.notna(value) else "")
        else:
            result[DAY_TYPE_COLUMN] = ""
    return result


def nearest_multicondition_similarity_price(
    target_df: pd.DataFrame,
    reference_df: pd.DataFrame,
    k: int = 3,
    similarity_weights: dict[str, object] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    target_frame = ensure_similarity_columns(target_df)
    reference_frame = ensure_similarity_columns(reference_df)
    weights = normalize_similarity_weights(similarity_weights)
    similar_prices: list[float] = []
    similar_gaps: list[float] = []
    for _, target_row in target_frame.iterrows():
        candidates = reference_frame[reference_frame["period"].astype(int) == int(target_row["period"])].copy()
        candidates = candidates.dropna(subset=[TARGET_COLUMN])
        if candidates.empty:
            similar_prices.append(np.nan)
            similar_gaps.append(np.nan)
            continue
        score = pd.Series(0.0, index=candidates.index)
        used_weight = pd.Series(0.0, index=candidates.index)
        for weight_key, weight in weights.items():
            column = SIMILARITY_WEIGHT_COLUMN_MAP[weight_key]
            if column == DAY_TYPE_COLUMN:
                gap = day_type_penalty(target_row.get(DAY_TYPE_COLUMN), candidates[DAY_TYPE_COLUMN])
            else:
                gap = normalized_numeric_gap(target_row.get(column), candidates[column])
            valid = gap.notna()
            score.loc[valid] += gap.loc[valid] * weight
            used_weight.loc[valid] += weight
        score = score.where(used_weight <= 0, score / used_weight.clip(lower=1e-9))
        score = score.replace([np.inf, -np.inf], np.nan).fillna(float("inf"))
        top_k = min(k, len(candidates))
        selected_index = score.nsmallest(top_k).index
        selected_score = score.loc[selected_index].to_numpy(dtype=float)
        selected_prices = candidates.loc[selected_index, TARGET_COLUMN].to_numpy(dtype=float)
        weights = 1.0 / (selected_score + 1e-6)
        similar_prices.append(float(np.sum(weights * selected_prices) / np.sum(weights)))
        similar_gaps.append(float(np.min(selected_score)))
    return np.asarray(similar_prices), np.asarray(similar_gaps)


def attach_multicondition_similarity_features(
    target_df: pd.DataFrame,
    reference_df: pd.DataFrame,
    k: int = 3,
    similarity_weights: dict[str, object] | None = None,
) -> pd.DataFrame:
    result = ensure_similarity_columns(target_df)
    reference_frame = ensure_similarity_columns(reference_df)
    similar_price, similar_gap = nearest_multicondition_similarity_price(result, reference_frame, k=k, similarity_weights=similarity_weights)
    result[SIMILAR_PRICE_COLUMN] = similar_price
    result[SIMILAR_GAP_COLUMN] = similar_gap
    return result


def attach_lag_96(base_df: pd.DataFrame, history_df: pd.DataFrame) -> pd.DataFrame:
    history_price = history_df[["date", "period", TARGET_COLUMN]].copy()
    history_price["lag_date"] = history_price["date"] + pd.Timedelta(days=1)
    history_price = history_price.rename(columns={TARGET_COLUMN: "lag_96"})
    return base_df.merge(history_price[["lag_date", "period", "lag_96"]], left_on=["date", "period"], right_on=["lag_date", "period"], how="left").drop(columns=["lag_date"])


def attach_similarity_features(
    history_df: pd.DataFrame,
    reference_days: int | None = None,
    similarity_weights: dict[str, object] | None = None,
) -> pd.DataFrame:
    result = ensure_similarity_columns(history_df)
    result[SIMILAR_PRICE_COLUMN] = np.nan
    result[SIMILAR_GAP_COLUMN] = np.nan
    result[NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN] = np.nan
    result[NET_LOAD_ONLY_SIMILAR_GAP_COLUMN] = np.nan
    unique_dates = sorted(pd.to_datetime(result["date"]).drop_duplicates().tolist())
    reference_days = normalize_similarity_reference_days(reference_days)
    for index in range(1, len(unique_dates)):
        current_date = unique_dates[index]
        ref_dates = unique_dates[max(0, index - reference_days):index]
        ref_day = result[result["date"].isin(ref_dates)]
        current_mask = result["date"] == current_date
        current_day = result.loc[current_mask]
        multi_price, multi_gap = nearest_multicondition_similarity_price(current_day, ref_day, similarity_weights=similarity_weights)
        similar_price, similar_gap = nearest_similarity_price(
            current_day["net_load"].to_numpy(dtype=float),
            ref_day["net_load"].to_numpy(dtype=float),
            ref_day[TARGET_COLUMN].to_numpy(dtype=float),
        )
        result.loc[current_mask, SIMILAR_PRICE_COLUMN] = multi_price
        result.loc[current_mask, SIMILAR_GAP_COLUMN] = multi_gap
        result.loc[current_mask, NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN] = similar_price
        result.loc[current_mask, NET_LOAD_ONLY_SIMILAR_GAP_COLUMN] = similar_gap
    result[RESIDUAL_TARGET_COLUMN] = result[TARGET_COLUMN] - result[SIMILAR_PRICE_COLUMN]
    return result


def filter_date_range(data: pd.DataFrame, start_date: str | None, end_date: str | None) -> pd.DataFrame:
    filtered = data.copy()
    if start_date:
        filtered = filtered[filtered["date"] >= pd.Timestamp(start_date)]
    if end_date:
        filtered = filtered[filtered["date"] <= pd.Timestamp(end_date)]
    return filtered.reset_index(drop=True)


def build_training_frame(
    config: TrainConfig,
    progress_callback: ProgressCallback | None = None,
) -> tuple[pd.DataFrame, list[str], Path]:
    try:
        history_df, skipped_sheets, _, history_signature, quality_issues = load_cached_history_collection(
            config.history_dir,
            config.holiday_file,
            True,
            config.model_root,
            progress_callback=progress_callback,
            progress_start=6,
            progress_end=18,
            progress_label="正在加载历史数据文件",
            start_date=config.start_date,
            end_date=config.end_date,
            leading_days=1,
        )
    except DataQualityValidationError as exc:
        report_path = save_quality_report(
            task_type="train",
            status="blocked",
            issues=exc.issues,
            metadata={
                "history_dir": str(config.history_dir),
                "start_date": config.start_date,
                "end_date": config.end_date,
            },
        )
        exc.report_path = report_path
        raise
    quality_report_path = save_quality_report(
        task_type="train",
        status=quality_report_status(quality_issues),
        issues=quality_issues,
        metadata={
            "history_dir": str(config.history_dir),
            "skipped_sheets": skipped_sheets,
            "start_date": config.start_date,
            "end_date": config.end_date,
        },
    )
    similarity_reference_days = normalize_similarity_reference_days(config.similarity_reference_days)
    similarity_weights = normalize_similarity_weights(config.similarity_weights)
    weights_cache_key = json.dumps(dict(similarity_weights), ensure_ascii=False, sort_keys=True)
    feature_cache_key = derived_cache_key(
        history_signature["cache_key"],
        f"training_features_{similarity_reference_days}_lag_{int(config.use_lag_96)}_weights_{weights_cache_key}",
    )
    feature_cache_dir = config.model_root / "cache"
    cached_features = load_dataframe_cache(feature_cache_dir, "training_features", feature_cache_key)
    if cached_features is not None:
        history_df, _ = cached_features
        emit_progress(progress_callback, "训练特征未变化，已复用缓存", 21)
    else:
        if config.use_lag_96:
            emit_progress(progress_callback, "正在构建 lag_96 特征", 19)
            history_df = attach_lag_96(history_df, history_df)
        emit_progress(progress_callback, "正在构建相似法特征", 20)
        history_df = attach_similarity_features(history_df, similarity_reference_days, similarity_weights=similarity_weights)
        save_dataframe_cache(feature_cache_dir, "training_features", feature_cache_key, history_df, skipped_sheets)
        emit_progress(progress_callback, "相似法特征构建完成", 21)
    history_df = filter_date_range(history_df, config.start_date, config.end_date)
    emit_progress(progress_callback, "正在过滤日期范围", 22)
    required_columns = [TARGET_COLUMN, SIMILAR_PRICE_COLUMN, RESIDUAL_TARGET_COLUMN]
    if config.use_lag_96:
        required_columns.append(LAG_96_COLUMN)
    history_df = history_df.dropna(subset=required_columns).reset_index(drop=True)
    if history_df.empty:
        raise ValueError("数据加载后经清洗为空，请检查历史数据文件是否包含有效数据。")
    return history_df, skipped_sheets, quality_report_path

def make_dmatrix(frame: pd.DataFrame, feature_columns: list[str], label_column: str | None = None):
    import xgboost as xgb

    feature_frame = frame[feature_columns].astype(float)
    if label_column:
        return xgb.DMatrix(feature_frame, label=frame[label_column].astype(float), feature_names=feature_columns)
    return xgb.DMatrix(feature_frame, feature_names=feature_columns)


def best_iteration_range(booster) -> tuple[int, int] | None:
    best_iteration = booster.attr("best_iteration")
    if best_iteration is None:
        return None
    return 0, int(best_iteration) + 1


def train_segment_models(
    history_df: pd.DataFrame,
    output_dir: Path,
    valid_days: int,
    num_boost_round: int,
    feature_columns: list[str],
    progress_callback: ProgressCallback | None = None,
) -> tuple[dict[str, dict[str, float | int | None]], list[str], list[str]]:
    import xgboost as xgb

    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_summary: dict[str, dict[str, float | int | None]] = {}
    unique_dates = sorted(pd.to_datetime(history_df["date"]).dt.strftime("%Y-%m-%d").unique().tolist())
    valid_dates = unique_dates[-valid_days:] if valid_days > 0 and len(unique_dates) > valid_days else []
    train_dates = unique_dates[:-valid_days] if valid_dates else unique_dates

    total_segments = len(SEGMENTS)
    for idx, segment_name in enumerate(SEGMENTS, start=1):
        emit_progress(progress_callback, f"正在训练分时段模型：{segment_name}", 25 + int(idx / total_segments * 45))
        segment_df = history_df[history_df["segment"] == segment_name].copy()
        if segment_df.empty:
            raise ValueError(f"时段 {segment_name} 无训练数据")
        train_df, valid_df = split_train_valid(segment_df, valid_days)
        dtrain = make_dmatrix(train_df, feature_columns, RESIDUAL_TARGET_COLUMN)
        evals = [(dtrain, "train")]
        train_kwargs = {
            "params": DEFAULT_XGB_PARAMS,
            "dtrain": dtrain,
            "num_boost_round": num_boost_round,
            "evals": evals,
            "verbose_eval": False,
        }
        if not valid_df.empty:
            dvalid = make_dmatrix(valid_df, feature_columns, RESIDUAL_TARGET_COLUMN)
            evals.append((dvalid, "valid"))
            train_kwargs["early_stopping_rounds"] = 50
        booster = xgb.train(**train_kwargs)
        booster.save_model(str(output_dir / f"{segment_name}.json"))

        segment_metrics: dict[str, float | int | None] = {
            "train_rows": int(len(train_df)),
            "valid_rows": int(len(valid_df)),
            "best_iteration": int(booster.attr("best_iteration")) if booster.attr("best_iteration") else None,
        }
        if not valid_df.empty:
            iteration_range = best_iteration_range(booster)
            residual_pred = booster.predict(dvalid, iteration_range=iteration_range) if iteration_range else booster.predict(dvalid)
            final_pred = valid_df[SIMILAR_PRICE_COLUMN].to_numpy(dtype=float) + residual_pred
            baseline_pred = valid_df[SIMILAR_PRICE_COLUMN].to_numpy(dtype=float)
            actual = valid_df[TARGET_COLUMN].to_numpy(dtype=float)
            segment_metrics.update(
                {
                    "baseline_mae": calculate_metrics(actual, baseline_pred)["mae"],
                    "baseline_rmse": calculate_metrics(actual, baseline_pred)["rmse"],
                    "final_mae": calculate_metrics(actual, final_pred)["mae"],
                    "final_rmse": calculate_metrics(actual, final_pred)["rmse"],
                }
            )
        metrics_summary[segment_name] = segment_metrics
    emit_progress(progress_callback, "分时段模型训练完成", 75)
    return metrics_summary, train_dates, valid_dates


def ensure_model_dirs(model_root: Path) -> tuple[Path, Path, Path]:
    current_dir = model_root / "current"
    previous_dir = model_root / "previous"
    history_dir = model_root / "history"
    model_root.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    return current_dir, previous_dir, history_dir


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(data, ensure_ascii=False) + "\n")


def training_preferences_path(model_root: str | Path = DEFAULT_MODEL_ROOT) -> Path:
    return Path(model_root) / "training_preferences.json"


def default_training_preferences() -> dict:
    return {"similarity_weights": dict(normalize_similarity_weights())}


def load_training_preferences(model_root: str | Path = DEFAULT_MODEL_ROOT) -> dict:
    path = training_preferences_path(model_root)
    if not path.exists():
        return default_training_preferences()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_training_preferences()
    preferences = default_training_preferences()
    if isinstance(data, dict) and isinstance(data.get("similarity_weights"), dict):
        preferences["similarity_weights"] = dict(normalize_similarity_weights(data["similarity_weights"]))
    return preferences


def save_training_preferences(model_root: str | Path, preferences: dict) -> dict:
    current = load_training_preferences(model_root)
    if isinstance(preferences.get("similarity_weights"), dict):
        current["similarity_weights"] = dict(normalize_similarity_weights(preferences["similarity_weights"]))
    path = training_preferences_path(model_root)
    write_json(path, current)
    return current


def default_model_pointer_path(model_root: Path) -> Path:
    return model_root / "default_model.json"


def read_pinned_default_version(model_root: Path) -> str | None:
    pointer_path = default_model_pointer_path(model_root)
    if not pointer_path.exists():
        return None
    try:
        data = json.loads(pointer_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    version_key = str(data.get("version_key", "")).strip()
    if not version_key:
        return None
    if not (model_root / "history" / version_key).exists():
        try:
            pointer_path.unlink()
        except OSError:
            pass
        return None
    return version_key


def write_pinned_default_version(model_root: Path, version_key: str | None) -> None:
    pointer_path = default_model_pointer_path(model_root)
    if not version_key:
        if pointer_path.exists():
            pointer_path.unlink()
        return
    write_json(
        pointer_path,
        {
            "version_key": version_key,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )


def find_version_key_by_run_id(model_root: Path, run_id: str | None) -> str | None:
    if not run_id:
        return None
    _, _, history_dir = ensure_model_dirs(model_root)
    for run_dir in history_dir.iterdir():
        if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
            continue
        metadata = read_model_metadata(run_dir)
        if metadata and metadata.get("run_id") == run_id:
            return run_dir.name
    return None


def finalize_model_version(model_root: Path, staging_dir: Path, run_id: str) -> tuple[Path, Path]:
    current_dir, previous_dir, history_dir = ensure_model_dirs(model_root)
    run_dir = history_dir / run_id
    if current_dir.exists():
        if previous_dir.exists():
            shutil.rmtree(previous_dir)
        shutil.copytree(current_dir, previous_dir)
        shutil.rmtree(current_dir)
    shutil.copytree(staging_dir, current_dir)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    shutil.copytree(staging_dir, run_dir)
    shutil.rmtree(staging_dir)
    return current_dir, run_dir


def train_and_register(config: TrainConfig, progress_callback: ProgressCallback | None = None) -> TrainResult:
    ensure_xgboost_available()
    emit_progress(progress_callback, "开始加载历史数据", 5)
    history_df, skipped_sheets, quality_report_path = build_training_frame(config, progress_callback=progress_callback)
    emit_progress(progress_callback, "历史数据加载完成，开始生成训练样本", 20)
    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    staging_dir = config.model_root / "_staging" / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    feature_columns = training_feature_columns(config)
    similarity_weights = normalize_similarity_weights(config.similarity_weights)
    metrics_summary, train_dates, valid_dates = train_segment_models(
        history_df,
        staging_dir,
        config.valid_days,
        config.num_boost_round,
        feature_columns,
        progress_callback=progress_callback,
    )

    metadata = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target_column": TARGET_COLUMN,
        "feature_columns": feature_columns,
        "segments": [{"name": name, "start": start, "end": end} for name, (start, end) in SEGMENTS.items()],
        "valid_days": config.valid_days,
        "num_boost_round": config.num_boost_round,
        "similarity_reference_days": normalize_similarity_reference_days(config.similarity_reference_days),
        "similarity_weights": dict(similarity_weights),
        "use_lag_96": bool(config.use_lag_96),
        "xgboost_params": DEFAULT_XGB_PARAMS,
        "train_start_date": train_dates[0] if train_dates else None,
        "train_end_date": train_dates[-1] if train_dates else None,
        "train_dates": train_dates,
        "valid_dates": valid_dates,
        "sample_rows": int(len(history_df)),
        "skipped_sheets": skipped_sheets,
        "quality_report_path": str(quality_report_path),
        "train_config": {
            "history_dir": str(config.history_dir),
            "holiday_file": str(config.holiday_file) if config.holiday_file else None,
            "start_date": config.start_date,
            "end_date": config.end_date,
            "similarity_reference_days": normalize_similarity_reference_days(config.similarity_reference_days),
            "similarity_weights": dict(similarity_weights),
            "use_lag_96": bool(config.use_lag_96),
        },
        "blend_method": "similarity_baseline_plus_xgboost_residual",
        "metrics": metrics_summary,
    }
    metadata_path = staging_dir / "metadata.json"
    emit_progress(progress_callback, "正在写入模型元数据", 82)
    write_json(metadata_path, metadata)
    emit_progress(progress_callback, "正在注册当前模型版本", 90)
    current_dir, history_dir = finalize_model_version(config.model_root, staging_dir, run_id)
    pinned_version_key = read_pinned_default_version(config.model_root)
    if pinned_version_key and pinned_version_key != run_id:
        current_dir = activate_model_version(config.model_root, pinned_version_key, persist_default=False)

    log_entry = {
        "run_id": run_id,
        "created_at": metadata["created_at"],
        "train_start_date": metadata["train_start_date"],
        "train_end_date": metadata["train_end_date"],
        "valid_dates": valid_dates,
        "sample_rows": metadata["sample_rows"],
        "start_date_filter": config.start_date,
        "end_date_filter": config.end_date,
        "use_lag_96": bool(config.use_lag_96),
        "similarity_reference_days": normalize_similarity_reference_days(config.similarity_reference_days),
        "similarity_weights": dict(similarity_weights),
        "metrics": metrics_summary,
    }
    append_jsonl(config.model_root / "training_runs.jsonl", log_entry)
    emit_progress(progress_callback, f"训练完成，当前默认模型：{run_id}", 100)
    return TrainResult(
        run_id=run_id,
        current_model_dir=current_dir,
        history_model_dir=history_dir,
        metrics=metrics_summary,
        train_dates=train_dates,
        valid_dates=valid_dates,
        skipped_sheets=skipped_sheets,
        metadata_path=current_dir / "metadata.json",
        quality_report_path=quality_report_path,
    )


def rollback_to_previous(model_root: Path = DEFAULT_MODEL_ROOT) -> Path:
    current_dir, previous_dir, history_dir = ensure_model_dirs(model_root)
    if not previous_dir.exists():
        raise FileNotFoundError("未找到上一版模型，无法回退")
    rollback_backup = history_dir / datetime.now().strftime("rollback_backup_%Y%m%d_%H%M%S")
    if current_dir.exists():
        shutil.copytree(current_dir, rollback_backup)
        shutil.rmtree(current_dir)
    shutil.copytree(previous_dir, current_dir)
    current_metadata = read_model_metadata(current_dir)
    write_pinned_default_version(model_root, find_version_key_by_run_id(model_root, current_metadata.get("run_id") if current_metadata else None))
    return current_dir


def resolve_active_model_dir(model_root: str | Path) -> Path:
    root = Path(model_root)
    current_dir = root / "current"
    metadata_path = current_dir / "metadata.json"
    if metadata_path.exists():
        return current_dir
    legacy_metadata = root / "metadata.json"
    if legacy_metadata.exists():
        return root
    raise FileNotFoundError(f"未找到可用模型目录: {root}")


def load_models(model_root: str | Path) -> tuple[dict, dict[str, object], Path]:
    import xgboost as xgb

    active_dir = resolve_active_model_dir(model_root)
    metadata = json.loads((active_dir / "metadata.json").read_text(encoding="utf-8"))
    models = {}
    for segment in metadata["segments"]:
        segment_name = segment["name"]
        booster = xgb.Booster()
        booster.load_model(str(active_dir / f"{segment_name}.json"))
        models[segment_name] = booster
    return metadata, models, active_dir


def resolve_forecast_template_column(columns: Iterable[object], target_date: pd.Timestamp, candidates: list[str], required: bool) -> str | None:
    month_day_tokens = [f"{target_date.month}.{target_date.day}", f"{target_date.month}月{target_date.day}"]
    names = [str(column).strip() for column in columns]
    matched = []
    for name in names:
        if not any(token in name for token in month_day_tokens):
            continue
        normalized_name = normalize_text(name)
        for candidate in candidates:
            if normalize_text(candidate) in normalized_name:
                matched.append(name)
                break
    if matched:
        return matched[0]
    return resolve_column(names, candidates, required=required)


def try_load_forecast_template(
    forecast_file: str | Path,
    holiday_dates: set[pd.Timestamp],
    default_year: int,
    require_lag_96: bool = True,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, list[DataQualityIssue]]:
    workbook = pd.read_excel(forecast_file, sheet_name=None)
    non_empty_sheets = [(str(name), df) for name, df in workbook.items() if not df.empty and len(df.columns) > 0]
    if not non_empty_sheets:
        return None, None, []
    template_sheet_name, template_raw_df = non_empty_sheets[0]
    raw_df = template_raw_df.copy().reset_index(drop=True)
    raw_df.columns = [str(column).strip() for column in raw_df.columns]
    header_dates = []
    for column in raw_df.columns:
        month_day = extract_month_day(column)
        if month_day is None:
            continue
        header_dates.append(pd.Timestamp(year=default_year, month=month_day[0], day=month_day[1]).normalize())
    unique_dates = sorted(set(header_dates))
    if len(unique_dates) < 2:
        return None, None, []

    quality_issues = validate_forecast_template(
        raw_df,
        file_path=Path(forecast_file),
        sheet_name=template_sheet_name,
        default_year=default_year,
        require_reference_price=require_lag_96,
    )
    if has_blocking_issues(quality_issues):
        raise DataQualityValidationError("预测文件关键字段异常，已停止预测", quality_issues)

    target_date = unique_dates[-1]
    reference_date = unique_dates[-2]
    target_net_load_col = resolve_forecast_template_column(raw_df.columns, target_date, ["剩余电力值(MW)", "剩余电力值", "火电空间", "火电剩余空间"], required=False)
    target_total_col = resolve_forecast_template_column(raw_df.columns, target_date, ["总加电力值(MW)", "总加电力值"], required=False)
    target_power_col = resolve_forecast_template_column(raw_df.columns, target_date, ["风光电力值(MW)", "风光电力值", "电力值(MW)", "电力值"], required=False)
    reference_net_load_col = resolve_forecast_template_column(raw_df.columns, reference_date, ["剩余电力值(MW)", "剩余电力值", "火电空间", "火电剩余空间"], required=False)
    reference_total_col = resolve_forecast_template_column(raw_df.columns, reference_date, ["总加电力值(MW)", "总加电力值"], required=False)
    reference_power_col = resolve_forecast_template_column(raw_df.columns, reference_date, ["风光电力值(MW)", "风光电力值", "电力值(MW)", "电力值"], required=False)
    reference_price_col = resolve_forecast_template_column(
        raw_df.columns,
        reference_date,
        ["日前出清价格(元/MWh)", "日前-出清价格(元/MWh)", "日前出清价格", "出清价格"],
        required=require_lag_96,
    )
    thermal_col = resolve_column(raw_df.columns, ["火电开机容量(MW)", "火电开机容量", "运行机组容量"], required=False)
    period_col = resolve_column(raw_df.columns, ["序号", "时段", "period"], required=False)

    def build_net_load(df: pd.DataFrame, net_col: str | None, total_col: str | None, power_col: str | None) -> pd.Series:
        if net_col:
            return to_numeric(df[net_col])
        if total_col and power_col:
            return to_numeric(df[total_col]) - to_numeric(df[power_col])
        raise KeyError("预测文件缺少火电空间相关字段")

    def build_total_load(df: pd.DataFrame, total_col: str | None) -> pd.Series:
        if total_col:
            return to_numeric(df[total_col])
        return pd.Series([np.nan] * len(df), index=df.index)

    target_net_load = build_net_load(raw_df, target_net_load_col, target_total_col, target_power_col)
    reference_net_load = build_net_load(raw_df, reference_net_load_col, reference_total_col, reference_power_col)
    target_total_load = build_total_load(raw_df, target_total_col)
    reference_total_load = build_total_load(raw_df, reference_total_col)
    target_renewable_power = to_numeric(raw_df[target_power_col]) if target_power_col else pd.Series([np.nan] * len(raw_df))
    reference_renewable_power = to_numeric(raw_df[reference_power_col]) if reference_power_col else pd.Series([np.nan] * len(raw_df))
    thermal_series = pd.Series([np.nan] * len(raw_df))
    if thermal_col:
        thermal_series = to_numeric(raw_df[thermal_col]).ffill().bfill()
    periods = to_numeric(raw_df[period_col]).fillna(0).astype(int).to_numpy() if period_col else np.arange(1, len(raw_df) + 1)
    if len(periods) < 96:
        raise ValueError("预测文件有效行数不足 96")
    periods = periods[:96]
    target_date = target_date.normalize()
    target_day_type = day_type_of(target_date, holiday_dates)
    forecast_df = pd.DataFrame(
        {
            "date": target_date,
            "period": periods,
            "hour": ((periods - 1) // 4).astype(int),
            "weekday": int(target_date.weekday()),
            "month": int(target_date.month),
            "is_weekend": int(target_day_type == "weekend"),
            "is_holiday": int(target_day_type == "holiday"),
            DAY_TYPE_COLUMN: target_day_type,
            TOTAL_LOAD_COLUMN: target_total_load.iloc[:96].to_numpy(),
            "net_load": target_net_load.iloc[:96].to_numpy(),
            RENEWABLE_POWER_COLUMN: target_renewable_power.iloc[:96].to_numpy(),
            THERMAL_SPACE_LOAD_RATIO_COLUMN: calculate_thermal_space_load_ratio(target_net_load, target_total_load).iloc[:96].to_numpy(),
            "thermal_on_capacity": thermal_series.iloc[:96].to_numpy(),
            "sheet_name": "forecast_template",
            "source_file": str(forecast_file),
        }
    )
    if reference_price_col:
        forecast_df[LAG_96_COLUMN] = to_numeric(raw_df[reference_price_col]).iloc[:96].to_numpy()
    forecast_df["segment"] = assign_segments(forecast_df["period"])

    reference_df = None
    if reference_price_col:
        reference_df = pd.DataFrame(
            {
                "date": reference_date.normalize(),
                "period": periods,
                TOTAL_LOAD_COLUMN: reference_total_load.iloc[:96].to_numpy(),
                "net_load": reference_net_load.iloc[:96].to_numpy(),
                RENEWABLE_POWER_COLUMN: reference_renewable_power.iloc[:96].to_numpy(),
                THERMAL_SPACE_LOAD_RATIO_COLUMN: calculate_thermal_space_load_ratio(reference_net_load, reference_total_load).iloc[:96].to_numpy(),
                "thermal_on_capacity": thermal_series.iloc[:96].to_numpy(),
                DAY_TYPE_COLUMN: day_type_of(reference_date, holiday_dates),
                TARGET_COLUMN: to_numeric(raw_df[reference_price_col]).iloc[:96].to_numpy(),
            }
        )
    return forecast_df, reference_df, quality_issues


def load_forecast_generic(
    history_df: pd.DataFrame,
    forecast_file: str | Path,
    holiday_dates: set[pd.Timestamp],
    require_lag_96: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame | None, list[DataQualityIssue]]:
    default_year = int(pd.to_datetime(history_df["date"]).max().year)
    template_df, template_reference, quality_issues = try_load_forecast_template(forecast_file, holiday_dates, default_year, require_lag_96=require_lag_96)
    if template_df is not None:
        return template_df, template_reference, quality_issues

    workbook = pd.read_excel(forecast_file, sheet_name=None)
    all_days = []
    quality_issues = []
    for sheet_name, raw_df in workbook.items():
        trade_date = parse_sheet_date(str(sheet_name))
        if trade_date is None:
            trade_date = infer_date_from_header(raw_df.columns, default_year)
        if trade_date is None:
            quality_issues.append(
                DataQualityIssue(
                    task_type="predict",
                    severity="warning",
                    action="recorded",
                    issue_type="unrecognized_sheet_date",
                    file_path=str(forecast_file),
                    sheet_name=str(sheet_name),
                    message="Sheet 名称和字段表头均无法识别预测日期，已忽略该 Sheet",
                )
            )
            continue
        sheet_issues = validate_history_sheet(
            raw_df,
            file_path=Path(forecast_file),
            sheet_name=str(sheet_name),
            trade_date=trade_date,
            require_target=False,
            task_type="predict",
            blocking_action="blocked",
        )
        quality_issues.extend(sheet_issues)
        if has_blocking_issues(sheet_issues):
            raise DataQualityValidationError("预测文件关键字段异常，已停止预测", sheet_issues)
        day_df = raw_df.copy().iloc[:96].reset_index(drop=True)
        if len(day_df) < 96:
            raise ValueError(f"{sheet_name} 不是 96 行时段数据")
        day_df.columns = [str(column).strip() for column in day_df.columns]
        total_power_col = resolve_column(day_df.columns, ["总加电力值(MW)", "总加电力值"], required=True)
        power_col = resolve_column(day_df.columns, ["电力值(MW)", "电力值"], required=True)
        thermal_col = resolve_column(day_df.columns, ["火电开机容量(MW)", "火电开机容量", "运行机组容量"], required=False)
        overview_col = resolve_column(day_df.columns, ["日前-出清概况", "日前出清概况", "出清概况"], required=False)
        thermal_series = pd.Series([np.nan] * len(day_df))
        if overview_col:
            thermal_series = day_df[overview_col].ffill().bfill().map(extract_thermal_on_capacity)
        if thermal_col:
            thermal_series = to_numeric(day_df[thermal_col]).combine_first(to_numeric(thermal_series))
        periods = np.arange(1, 97)
        day_type = day_type_of(trade_date.normalize(), holiday_dates)
        total_load = to_numeric(day_df[total_power_col])
        renewable_power = to_numeric(day_df[power_col])
        thermal_space = total_load - renewable_power
        result = pd.DataFrame(
            {
                "date": trade_date.normalize(),
                "period": periods,
                "hour": ((periods - 1) // 4).astype(int),
                "weekday": int(trade_date.weekday()),
                "month": int(trade_date.month),
                "is_weekend": int(day_type == "weekend"),
                "is_holiday": int(day_type == "holiday"),
                DAY_TYPE_COLUMN: day_type,
                TOTAL_LOAD_COLUMN: total_load,
                "net_load": thermal_space,
                RENEWABLE_POWER_COLUMN: renewable_power,
                THERMAL_SPACE_LOAD_RATIO_COLUMN: calculate_thermal_space_load_ratio(thermal_space, total_load),
                "thermal_on_capacity": to_numeric(thermal_series),
                "sheet_name": sheet_name,
                "source_file": str(forecast_file),
            }
        )
        result["segment"] = assign_segments(result["period"])
        all_days.append(result)
    if not all_days:
        raise ValueError(f"未解析到可用的预测 Sheet: {forecast_file}")
    forecast_df = pd.concat(all_days, ignore_index=True).sort_values(["date", "period"]).reset_index(drop=True)
    return forecast_df, None, quality_issues


def default_forecast_year_from_model(model_root: str | Path) -> int:
    metadata = load_current_metadata(Path(model_root)) or {}
    for key in ("train_end_date", "created_at"):
        value = metadata.get(key)
        if not value:
            continue
        timestamp = pd.to_datetime(value, errors="coerce")
        if not pd.isna(timestamp):
            return int(pd.Timestamp(timestamp).year)
    return datetime.now().year


def peek_forecast_target_date(forecast_file: str | Path, default_year: int) -> pd.Timestamp | None:
    workbook = pd.read_excel(forecast_file, sheet_name=None)
    header_dates: list[pd.Timestamp] = []
    sheet_dates: list[pd.Timestamp] = []
    for sheet_name, raw_df in workbook.items():
        sheet_date = parse_sheet_date(str(sheet_name))
        if sheet_date is not None:
            sheet_dates.append(sheet_date.normalize())
        if raw_df.empty:
            continue
        for column in raw_df.columns:
            month_day = extract_month_day(column)
            if month_day is not None:
                header_dates.append(pd.Timestamp(year=default_year, month=month_day[0], day=month_day[1]).normalize())
    if header_dates:
        return max(header_dates)
    if sheet_dates:
        return max(sheet_dates)
    return None


def prediction_history_window(forecast_date: pd.Timestamp | None, reference_days: int) -> tuple[str | None, str | None]:
    if forecast_date is None:
        return None, None
    normalized_days = normalize_reference_days(reference_days)
    lookback_days = max(normalized_days, normalized_days * 8)
    start_date = pd.Timestamp(forecast_date).normalize() - pd.Timedelta(days=lookback_days)
    end_date = pd.Timestamp(forecast_date).normalize() - pd.Timedelta(days=1)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def build_reference_frame(
    history_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    template_reference_df: pd.DataFrame | None,
    reference_days: int,
    reference_strategy: str,
    holiday_dates: set[pd.Timestamp],
) -> tuple[pd.DataFrame, list[str]]:
    reference_days = normalize_reference_days(reference_days)
    reference_strategy = normalize_reference_strategy(reference_strategy)
    forecast_date = pd.to_datetime(forecast_df["date"]).min().normalize()
    forecast_day_type = day_type_of(forecast_date, holiday_dates)
    history_dates = pd.to_datetime(history_df["date"], errors="coerce").dropna().dt.normalize()
    selected_dates: list[pd.Timestamp] = []
    selected_frames: list[pd.DataFrame] = []

    def is_eligible_reference(ref_date: pd.Timestamp) -> bool:
        if reference_strategy == "recent_n_days":
            return True
        return day_type_of(ref_date, holiday_dates) == forecast_day_type

    def reference_columns(frame: pd.DataFrame) -> list[str]:
        desired = [
            "date",
            "period",
            TOTAL_LOAD_COLUMN,
            "net_load",
            RENEWABLE_POWER_COLUMN,
            THERMAL_SPACE_LOAD_RATIO_COLUMN,
            "thermal_on_capacity",
            DAY_TYPE_COLUMN,
            TARGET_COLUMN,
        ]
        return [column for column in desired if column in frame.columns]

    if template_reference_df is not None and not template_reference_df.empty and len(selected_dates) < reference_days:
        template_reference = template_reference_df[reference_columns(template_reference_df)].copy()
        template_reference["date"] = pd.to_datetime(template_reference["date"], errors="coerce").dt.normalize()
        template_date = pd.to_datetime(template_reference["date"]).iloc[0].normalize()
        if is_eligible_reference(template_date):
            selected_frames.append(template_reference)
            selected_dates.append(template_date)

    used_dates = set(selected_dates)
    recent_history_dates = [
        ref_date
        for ref_date in sorted(set(history_dates.tolist()), reverse=True)
        if ref_date < forecast_date and ref_date not in used_dates and is_eligible_reference(ref_date)
    ]
    for ref_date in recent_history_dates:
        if len(selected_dates) >= reference_days:
            break
        history_reference = history_df.loc[history_dates == ref_date, reference_columns(history_df)].copy()
        if history_reference.empty:
            continue
        selected_frames.append(history_reference)
        selected_dates.append(ref_date)

    if not selected_frames:
        raise ValueError("未找到可用于相似法预测的参考日数据")
    if len(selected_dates) < reference_days:
        warnings.warn(
            f"请求使用最近 {reference_days} 天参考数据，但仅找到 {len(selected_dates)} 天可用样本，已自动降级为现有样本。",
            stacklevel=2,
        )

    reference_df = pd.concat(selected_frames, ignore_index=True)
    reference_df["date"] = pd.to_datetime(reference_df["date"], errors="coerce").dt.normalize()
    reference_df = ensure_similarity_columns(reference_df)
    reference_df = reference_df.dropna(subset=["net_load", TARGET_COLUMN]).reset_index(drop=True)
    if reference_df.empty:
        raise ValueError("参考日样本缺少有效火电空间或价格数据，无法构造相似法特征")
    reference_dates = [pd.Timestamp(ref_date).strftime("%Y-%m-%d") for ref_date in selected_dates]
    return reference_df, reference_dates


def attach_forecast_similarity_features(
    forecast_df: pd.DataFrame,
    reference_df: pd.DataFrame,
    similarity_weights: dict[str, object] | None = None,
) -> pd.DataFrame:
    result = attach_multicondition_similarity_features(forecast_df, reference_df, similarity_weights=similarity_weights)
    similar_price, similar_gap = nearest_similarity_price(
        result["net_load"].to_numpy(dtype=float),
        reference_df["net_load"].to_numpy(dtype=float),
        reference_df[TARGET_COLUMN].to_numpy(dtype=float),
    )
    result[NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN] = similar_price
    result[NET_LOAD_ONLY_SIMILAR_GAP_COLUMN] = similar_gap
    return result


def clip_price_series(values: pd.Series | np.ndarray) -> pd.Series | np.ndarray:
    return np.clip(values, PRICE_FLOOR, PRICE_CAP)


def ensure_prediction_lag_96(forecast_df: pd.DataFrame, history_df: pd.DataFrame, metadata: dict) -> pd.DataFrame:
    if not model_requires_lag_96(metadata):
        return forecast_df
    result = forecast_df
    if LAG_96_COLUMN not in result.columns:
        result = attach_lag_96(result, history_df)
    if result[LAG_96_COLUMN].isna().any():
        missing = result.loc[result[LAG_96_COLUMN].isna(), ["date", "period"]].head(10)
        raise ValueError(f"Missing lag_96 for date/period:\n{missing.to_string(index=False)}")
    return result


def prepare_prediction_inputs(
    history_dir: str | Path,
    forecast_file: str | Path,
    model_root: str | Path,
    holiday_file: str | Path | None,
    reference_days: int = 1,
    progress_callback: ProgressCallback | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None, set[pd.Timestamp], dict, dict[str, object], Path]:
    emit_progress(progress_callback, "开始加载预测所需数据", 5)
    forecast_default_year = default_forecast_year_from_model(model_root)
    forecast_target_date = peek_forecast_target_date(forecast_file, forecast_default_year)
    history_start_date, history_end_date = prediction_history_window(forecast_target_date, reference_days)
    try:
        history_df, _, holiday_dates, _, history_quality_issues = load_cached_history_collection(
            history_dir,
            holiday_file,
            True,
            model_root,
            progress_callback=progress_callback,
            progress_start=6,
            progress_end=18,
            progress_label="正在加载历史数据",
            start_date=history_start_date,
            end_date=history_end_date,
        )
    except DataQualityValidationError as exc:
        report_path = save_quality_report(
            task_type="predict",
            status="blocked",
            issues=exc.issues,
            metadata={"forecast_file": str(forecast_file), "history_dir": str(history_dir)},
        )
        exc.report_path = report_path
        raise
    emit_progress(progress_callback, "历史数据加载完成，正在加载预测文件", 20)
    emit_progress(progress_callback, "正在加载当前默认模型", 21)
    metadata, models, _ = load_models(model_root)
    quality_issues = list(history_quality_issues)
    try:
        forecast_df, template_reference_df, forecast_quality_issues = load_forecast_generic(
            history_df,
            forecast_file,
            holiday_dates,
            require_lag_96=model_requires_lag_96(metadata),
        )
        quality_issues.extend(forecast_quality_issues)
    except DataQualityValidationError as exc:
        quality_issues.extend(exc.issues)
        report_path = save_quality_report(
            task_type="predict",
            status="blocked",
            issues=quality_issues,
            metadata={"forecast_file": str(forecast_file), "history_dir": str(history_dir)},
        )
        exc.report_path = report_path
        raise
    forecast_df = ensure_prediction_lag_96(forecast_df, history_df, metadata)
    emit_progress(progress_callback, "预测输入准备完成", 45)
    report_path = save_quality_report(
        task_type="predict",
        status=quality_report_status(quality_issues),
        issues=quality_issues,
        metadata={"forecast_file": str(forecast_file), "history_dir": str(history_dir)},
    )
    return history_df, forecast_df, template_reference_df, holiday_dates, metadata, models, report_path


def run_prediction_with_strategy(
    history_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    template_reference_df: pd.DataFrame | None,
    holiday_dates: set[pd.Timestamp],
    metadata: dict,
    models: dict[str, object],
    reference_days: int,
    reference_strategy: str,
    progress_callback: ProgressCallback | None = None,
    segment_progress_start: int = 55,
    segment_progress_span: int = 30,
) -> tuple[pd.DataFrame, list[str], str, str]:
    strategy_key = normalize_reference_strategy(reference_strategy)
    strategy_label = REFERENCE_STRATEGIES[strategy_key]
    reference_df, reference_dates = build_reference_frame(
        history_df=history_df,
        forecast_df=forecast_df,
        template_reference_df=template_reference_df,
        reference_days=reference_days,
        reference_strategy=strategy_key,
        holiday_dates=holiday_dates,
    )
    metadata_weights = metadata.get("similarity_weights")
    model_similarity_weights = normalize_similarity_weights(metadata_weights, fill_missing_with_defaults=False) if metadata_weights else None
    strategy_forecast_df = attach_forecast_similarity_features(forecast_df, reference_df, similarity_weights=model_similarity_weights)

    prediction_frames: list[pd.DataFrame] = []
    total_segments = len(metadata["segments"])
    for idx, segment in enumerate(metadata["segments"], start=1):
        segment_name = segment["name"]
        if progress_callback is not None:
            segment_percent = segment_progress_start + int(idx / max(total_segments, 1) * segment_progress_span)
            emit_progress(progress_callback, f"正在预测 {strategy_label} / 时段{segment_name}", segment_percent)
        segment_df = strategy_forecast_df[strategy_forecast_df["segment"] == segment_name].copy()
        if segment_df.empty:
            continue
        dmatrix = make_dmatrix(segment_df, metadata["feature_columns"])
        booster = models[segment_name]
        iteration_range = best_iteration_range(booster)
        residual_pred = booster.predict(dmatrix, iteration_range=iteration_range) if iteration_range else booster.predict(dmatrix)
        raw_predicted_price = segment_df[SIMILAR_PRICE_COLUMN].to_numpy(dtype=float) + residual_pred
        clipped_predicted_price = clip_price_series(raw_predicted_price)
        segment_df["predicted_price"] = clipped_predicted_price
        segment_df["residual_pred"] = segment_df["predicted_price"] - segment_df[SIMILAR_PRICE_COLUMN]
        prediction_frames.append(segment_df)

    result_df = pd.concat(prediction_frames, ignore_index=True).sort_values(["date", "period"]).reset_index(drop=True)
    return result_df, reference_dates, strategy_key, strategy_label


def predict_prices(
    history_dir: str | Path,
    forecast_file: str | Path,
    model_root: str | Path = DEFAULT_MODEL_ROOT,
    output_file: str | Path = DEFAULT_OUTPUT_FILE,
    holiday_file: str | Path | None = None,
    reference_days: int = 1,
    reference_strategy: str = "recent_n_days",
    progress_callback: ProgressCallback | None = None,
) -> PredictResult:
    ensure_xgboost_available()
    reference_days = normalize_reference_days(reference_days)
    history_df, forecast_df, template_reference_df, holiday_dates, metadata, models, quality_report_path = prepare_prediction_inputs(
        history_dir=history_dir,
        forecast_file=forecast_file,
        model_root=model_root,
        holiday_file=holiday_file,
        reference_days=reference_days,
        progress_callback=progress_callback,
    )
    emit_progress(progress_callback, "正在执行预测策略", 50)
    result_df, reference_dates, strategy_key, strategy_label = run_prediction_with_strategy(
        history_df=history_df,
        forecast_df=forecast_df,
        template_reference_df=template_reference_df,
        holiday_dates=holiday_dates,
        metadata=metadata,
        models=models,
        reference_days=reference_days,
        reference_strategy=reference_strategy,
        progress_callback=progress_callback,
    )
    emit_progress(progress_callback, "正在导出预测结果", 92)
    export_prediction(result_df, output_file)
    template_updated = write_prediction_to_template(forecast_file, result_df)
    emit_progress(progress_callback, "预测任务完成", 100)
    forecast_date = pd.to_datetime(result_df["date"]).dt.strftime("%Y-%m-%d").iloc[0]
    return PredictResult(
        forecast_date=forecast_date,
        output_file=Path(output_file),
        template_updated=template_updated,
        reference_strategy_key=strategy_key,
        reference_strategy_label=strategy_label,
        reference_days_requested=reference_days,
        reference_dates=reference_dates,
        result_df=result_df,
        quality_report_path=quality_report_path,
    )


def predict_prices_compare(
    history_dir: str | Path,
    forecast_file: str | Path,
    model_root: str | Path = DEFAULT_MODEL_ROOT,
    output_file: str | Path = DEFAULT_OUTPUT_FILE,
    holiday_file: str | Path | None = None,
    reference_days: int = 1,
    selected_strategy: str = "recent_n_days",
    progress_callback: ProgressCallback | None = None,
) -> PredictCompareResult:
    ensure_xgboost_available()
    reference_days = normalize_reference_days(reference_days)
    selected_strategy_key = normalize_reference_strategy(selected_strategy)
    history_df, forecast_df, template_reference_df, holiday_dates, metadata, models, quality_report_path = prepare_prediction_inputs(
        history_dir=history_dir,
        forecast_file=forecast_file,
        model_root=model_root,
        holiday_file=holiday_file,
        reference_days=reference_days,
        progress_callback=progress_callback,
    )

    strategy_keys = list(REFERENCE_STRATEGIES.keys())
    strategy_results: dict[str, PredictResult] = {}
    total_strategies = len(strategy_keys)
    for strategy_index, strategy_key in enumerate(strategy_keys, start=1):
        emit_progress(progress_callback, f"正在对比策略 {strategy_index}/{total_strategies}: {REFERENCE_STRATEGIES[strategy_key]}", 48 + int((strategy_index - 1) / total_strategies * 6))
        result_df, reference_dates, normalized_strategy_key, strategy_label = run_prediction_with_strategy(
            history_df=history_df,
            forecast_df=forecast_df,
            template_reference_df=template_reference_df,
            holiday_dates=holiday_dates,
            metadata=metadata,
            models=models,
            reference_days=reference_days,
            reference_strategy=strategy_key,
            progress_callback=progress_callback,
            segment_progress_start=55 + int((strategy_index - 1) * 15),
            segment_progress_span=12,
        )
        forecast_date = pd.to_datetime(result_df["date"]).dt.strftime("%Y-%m-%d").iloc[0]
        strategy_results[strategy_key] = PredictResult(
            forecast_date=forecast_date,
            output_file=Path(output_file),
            template_updated=False,
            reference_strategy_key=normalized_strategy_key,
            reference_strategy_label=strategy_label,
            reference_days_requested=reference_days,
            reference_dates=reference_dates,
            result_df=result_df,
            quality_report_path=quality_report_path,
        )

    selected_result = strategy_results[selected_strategy_key]
    emit_progress(progress_callback, "正在导出预测结果", 92)
    export_prediction(selected_result.result_df, output_file)
    template_updated = write_prediction_to_template(forecast_file, selected_result.result_df)
    emit_progress(progress_callback, f"预测完成，已选择策略 {selected_result.reference_strategy_label}", 100)

    return PredictCompareResult(
        forecast_date=selected_result.forecast_date,
        output_file=Path(output_file),
        template_updated=template_updated,
        selected_strategy_key=selected_strategy_key,
        selected_strategy_label=REFERENCE_STRATEGIES[selected_strategy_key],
        strategy_results={
            key: PredictResult(
                forecast_date=value.forecast_date,
                output_file=value.output_file,
                template_updated=template_updated if key == selected_strategy_key else False,
                reference_strategy_key=value.reference_strategy_key,
                reference_strategy_label=value.reference_strategy_label,
                reference_days_requested=value.reference_days_requested,
                reference_dates=value.reference_dates,
                result_df=value.result_df.copy(),
                quality_report_path=value.quality_report_path,
            )
            for key, value in strategy_results.items()
        },
        quality_report_path=quality_report_path,
    )

def export_prediction(result_df: pd.DataFrame, output_file: str | Path) -> None:
    output_path = Path(output_file)
    export_columns = [
        "date",
        "period",
        "segment",
        "hour",
        "net_load",
        RENEWABLE_POWER_COLUMN,
        "thermal_on_capacity",
        DAY_TYPE_COLUMN,
        LAG_96_COLUMN,
        SIMILAR_PRICE_COLUMN,
        NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN,
        "residual_pred",
        "predicted_price",
    ]
    export_df = result_df[[column for column in export_columns if column in result_df.columns]].copy()
    export_df["date"] = pd.to_datetime(export_df["date"]).dt.strftime("%Y-%m-%d")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".csv":
        export_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        return
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="prediction")


def write_prediction_to_template(forecast_file: str | Path, result_df: pd.DataFrame) -> bool:
    workbook = load_workbook(forecast_file)
    for sheet in workbook.worksheets:
        if sheet.max_row < 2 or sheet.max_column < 1:
            continue
        headers = [sheet.cell(row=1, column=col).value for col in range(1, sheet.max_column + 1)]
        target_col = None
        for idx, header in enumerate(headers, start=1):
            if normalize_text(header) == normalize_text("预测价格"):
                target_col = idx
                break
        if target_col is None:
            continue
        predicted_values = result_df.sort_values("period")["predicted_price"].tolist()
        for row_idx, value in enumerate(predicted_values, start=2):
            sheet.cell(row=row_idx, column=target_col).value = round(float(value), 4)
        workbook.save(forecast_file)
        return True
    return False


def load_training_log(model_root: Path = DEFAULT_MODEL_ROOT) -> pd.DataFrame:
    log_path = model_root / "training_runs.jsonl"
    if not log_path.exists():
        return pd.DataFrame()
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return pd.DataFrame(rows)


def load_current_metadata(model_root: Path = DEFAULT_MODEL_ROOT) -> dict | None:
    try:
        current_dir = resolve_active_model_dir(model_root)
    except FileNotFoundError:
        return None
    return json.loads((current_dir / "metadata.json").read_text(encoding="utf-8"))


def read_model_metadata(model_dir: Path) -> dict | None:
    metadata_path = model_dir / "metadata.json"
    if not metadata_path.exists():
        return None
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def summarize_model_quality_metrics(metrics: dict | None) -> dict[str, float | None]:
    if not isinstance(metrics, dict) or not metrics:
        return {
            "baseline_mae": None,
            "baseline_rmse": None,
            "final_mae": None,
            "final_rmse": None,
        }

    total_valid_rows = 0.0
    baseline_mae_weighted = 0.0
    baseline_rmse_squared_weighted = 0.0
    final_mae_weighted = 0.0
    final_rmse_squared_weighted = 0.0

    for segment_metrics in metrics.values():
        if not isinstance(segment_metrics, dict):
            continue
        valid_rows = segment_metrics.get("valid_rows")
        if valid_rows is None:
            continue
        try:
            valid_rows_value = float(valid_rows)
        except (TypeError, ValueError):
            continue
        if valid_rows_value <= 0:
            continue

        baseline_mae = segment_metrics.get("baseline_mae")
        baseline_rmse = segment_metrics.get("baseline_rmse")
        final_mae = segment_metrics.get("final_mae")
        final_rmse = segment_metrics.get("final_rmse")
        if any(value is None for value in (baseline_mae, baseline_rmse, final_mae, final_rmse)):
            continue

        try:
            baseline_mae_value = float(baseline_mae)
            baseline_rmse_value = float(baseline_rmse)
            final_mae_value = float(final_mae)
            final_rmse_value = float(final_rmse)
        except (TypeError, ValueError):
            continue

        total_valid_rows += valid_rows_value
        baseline_mae_weighted += valid_rows_value * baseline_mae_value
        baseline_rmse_squared_weighted += valid_rows_value * (baseline_rmse_value**2)
        final_mae_weighted += valid_rows_value * final_mae_value
        final_rmse_squared_weighted += valid_rows_value * (final_rmse_value**2)

    if total_valid_rows <= 0:
        return {
            "baseline_mae": None,
            "baseline_rmse": None,
            "final_mae": None,
            "final_rmse": None,
        }

    return {
        "baseline_mae": round(baseline_mae_weighted / total_valid_rows, 4),
        "baseline_rmse": round(float(np.sqrt(baseline_rmse_squared_weighted / total_valid_rows)), 4),
        "final_mae": round(final_mae_weighted / total_valid_rows, 4),
        "final_rmse": round(float(np.sqrt(final_rmse_squared_weighted / total_valid_rows)), 4),
    }


def list_model_versions(model_root: Path = DEFAULT_MODEL_ROOT) -> pd.DataFrame:
    current_dir, previous_dir, history_dir = ensure_model_dirs(model_root)
    current_metadata = read_model_metadata(current_dir)
    previous_metadata = read_model_metadata(previous_dir)
    current_run_id = current_metadata.get("run_id") if current_metadata else None
    previous_run_id = previous_metadata.get("run_id") if previous_metadata else None
    pinned_version_key = read_pinned_default_version(model_root)

    rows: list[dict] = []
    for run_dir in sorted(history_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        if not run_dir.name.startswith("run_"):
            continue
        metadata = read_model_metadata(run_dir)
        if metadata is None:
            continue
        quality_metrics = summarize_model_quality_metrics(metadata.get("metrics"))
        rows.append(
            {
                "version_key": run_dir.name,
                "run_id": metadata.get("run_id", run_dir.name),
                "created_at": metadata.get("created_at"),
                "train_start_date": metadata.get("train_start_date"),
                "train_end_date": metadata.get("train_end_date"),
                "sample_rows": metadata.get("sample_rows"),
                "is_default": metadata.get("run_id") == current_run_id,
                "is_previous": metadata.get("run_id") == previous_run_id,
                "is_pinned_default": run_dir.name == pinned_version_key,
                "baseline_mae": quality_metrics.get("baseline_mae"),
                "baseline_rmse": quality_metrics.get("baseline_rmse"),
                "final_mae": quality_metrics.get("final_mae"),
                "final_rmse": quality_metrics.get("final_rmse"),
                "path": str(run_dir),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("created_at", ascending=False).reset_index(drop=True)
    return df


def activate_model_version(model_root: Path, version_key: str, persist_default: bool = True) -> Path:
    current_dir, previous_dir, history_dir = ensure_model_dirs(model_root)
    selected_dir = history_dir / version_key
    if not selected_dir.exists():
        raise FileNotFoundError(f"未找到指定模型版本: {version_key}")
    if current_dir.exists():
        if previous_dir.exists():
            shutil.rmtree(previous_dir)
        shutil.copytree(current_dir, previous_dir)
        shutil.rmtree(current_dir)
    shutil.copytree(selected_dir, current_dir)
    if persist_default:
        write_pinned_default_version(model_root, version_key)
    return current_dir


def delete_model_versions(model_root: Path, version_keys: list[str]) -> list[str]:
    _, _, history_dir = ensure_model_dirs(model_root)
    deleted: list[str] = []
    pinned_version_key = read_pinned_default_version(model_root)
    for version_key in version_keys:
        target_dir = history_dir / version_key
        if target_dir.exists():
            shutil.rmtree(target_dir)
            deleted.append(version_key)
    if pinned_version_key and pinned_version_key in deleted:
        write_pinned_default_version(model_root, None)
    return deleted


def print_metrics(metrics_summary: dict[str, dict[str, float | int | None]]) -> None:
    print("训练完成，各分时段验证结果：")
    for segment_name, metric in metrics_summary.items():
        final_mae = metric.get("final_mae")
        final_rmse = metric.get("final_rmse")
        baseline_rmse = metric.get("baseline_rmse")
        if final_mae is None or final_rmse is None:
            print(f"  - {segment_name}: train_rows={metric['train_rows']}, valid_rows={metric['valid_rows']}")
        else:
            print(
                f"  - {segment_name}: baseline_RMSE={baseline_rmse}, "
                f"final_MAE={final_mae}, final_RMSE={final_rmse}"
            )
