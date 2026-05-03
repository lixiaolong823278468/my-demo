from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_REPORT_DIR = BASE_DIR / "output" / "data_quality_reports"

HISTORY_TOTAL_POWER_CANDIDATES = ["总加电力值(MW)", "总加电力值"]
HISTORY_POWER_CANDIDATES = ["电力值(MW)", "电力值", "风光电力值(MW)", "风光电力值"]
HISTORY_TARGET_CANDIDATES = ["日前出清价格(元/MWh)", "日前-出清价格(元/MWh)", "日前出清价格", "出清价格"]
THERMAL_CANDIDATES = ["火电开机容量(MW)", "火电开机容量", "运行机组容量"]
OVERVIEW_CANDIDATES = ["日前-出清概况", "日前出清概况", "出清概况"]

FORECAST_NET_LOAD_CANDIDATES = ["剩余电力值(MW)", "剩余电力值", "火电空间", "火电剩余空间"]
FORECAST_TOTAL_POWER_CANDIDATES = HISTORY_TOTAL_POWER_CANDIDATES
FORECAST_POWER_CANDIDATES = HISTORY_POWER_CANDIDATES
PERIOD_CANDIDATES = ["序号", "时段", "period"]


@dataclass
class DataQualityIssue:
    task_type: str
    severity: str
    action: str
    issue_type: str
    file_path: str
    sheet_name: str
    message: str
    date: str | None = None
    period: int | None = None
    field: str | None = None
    value: object | None = None


class DataQualityValidationError(ValueError):
    def __init__(self, message: str, issues: list[DataQualityIssue], report_path: Path | None = None) -> None:
        super().__init__(message)
        self.issues = issues
        self.report_path = report_path


def normalize_text(text: object) -> str:
    return re.sub(r"\s+", "", str(text)).strip().lower()


def extract_month_day(value: object) -> tuple[int, int] | None:
    text = str(value)
    match = re.search(r"(\d{1,2})\s*[月/.\-]\s*(\d{1,2})\s*(?:日)?", text)
    if not match:
        return None
    month, day = map(int, match.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return month, day


def resolve_column(columns: Iterable[object], candidates: list[str]) -> str | None:
    normalized = {normalize_text(column): str(column).strip() for column in columns}
    for candidate in candidates:
        key = normalize_text(candidate)
        if key in normalized:
            return normalized[key]
    for candidate in candidates:
        key = normalize_text(candidate)
        for normalized_name, original_name in normalized.items():
            if key in normalized_name or normalized_name in key:
                return original_name
    return None


def resolve_forecast_template_column(columns: Iterable[object], target_date: pd.Timestamp, candidates: list[str]) -> str | None:
    target = pd.Timestamp(target_date)
    month_day_tokens = {
        f"{target.month}月{target.day}日",
        f"{target.month}月{target.day}",
        f"{target.month}/{target.day}",
        f"{target.month}-{target.day}",
    }
    matched: list[str] = []
    for column in columns:
        name = str(column).strip()
        if not any(token in name for token in month_day_tokens):
            continue
        normalized_name = normalize_text(name)
        for candidate in candidates:
            if normalize_text(candidate) in normalized_name:
                matched.append(name)
                break
    if matched:
        return matched[0]
    return resolve_column(columns, candidates)


def numeric_masks(series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    raw = series.copy()
    text = raw.astype(str).str.replace(",", "", regex=False).str.strip()
    missing = raw.isna() | text.isin(["", "nan", "None", "none", "--", "-"])
    numeric = pd.to_numeric(text, errors="coerce")
    invalid = numeric.isna() & ~missing
    return numeric, missing, invalid


def convert_capacity_to_mw(value: float, unit: str | None) -> float:
    normalized = normalize_text(unit or "MW")
    if normalized in {"万千瓦", "万kw", "万kw"}:
        return value * 10.0
    if normalized == "gw":
        return value * 1000.0
    if normalized == "kw":
        return value / 1000.0
    return value


def extract_running_unit_capacity(text: object) -> float:
    if pd.isna(text):
        return np.nan
    content = str(text)
    patterns = [
        r"运行机组容量[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*(万千瓦|万kw|万kW|MW|mw|GW|gw|kW|kw|KW)?",
        r"火电开机容量[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*(万千瓦|万kw|万kW|MW|mw|GW|gw|kW|kw|KW)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return convert_capacity_to_mw(float(match.group(1)), match.group(2))
    return np.nan


def safe_value(value: object) -> object | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def add_missing_field_issue(
    issues: list[DataQualityIssue],
    *,
    task_type: str,
    action: str,
    file_path: Path,
    sheet_name: str,
    date: str | None,
    field: str,
    candidates: list[str],
) -> None:
    issues.append(
        DataQualityIssue(
            task_type=task_type,
            severity="error",
            action=action,
            issue_type="missing_required_field",
            file_path=str(file_path),
            sheet_name=str(sheet_name),
            date=date,
            field=field,
            message=f"缺少必要字段，可识别字段名：{', '.join(candidates)}",
        )
    )


def add_numeric_issues(
    issues: list[DataQualityIssue],
    *,
    task_type: str,
    severity: str,
    action: str,
    issue_type: str,
    file_path: Path,
    sheet_name: str,
    date: str | None,
    field: str,
    series: pd.Series,
) -> None:
    _, missing, invalid = numeric_masks(series.iloc[:96])
    for index in series.iloc[:96][missing | invalid].index:
        period = int(index) + 1
        is_missing = bool(missing.loc[index])
        issues.append(
            DataQualityIssue(
                task_type=task_type,
                severity=severity,
                action=action,
                issue_type="missing_value" if is_missing else issue_type,
                file_path=str(file_path),
                sheet_name=str(sheet_name),
                date=date,
                period=period,
                field=field,
                value=safe_value(series.loc[index]),
                message="字段为空" if is_missing else "字段无法转换为数字",
            )
        )


def validate_history_sheet(
    raw_df: pd.DataFrame,
    *,
    file_path: Path,
    sheet_name: str,
    trade_date: pd.Timestamp | None,
    require_target: bool,
    task_type: str = "train",
    blocking_action: str = "skipped",
) -> list[DataQualityIssue]:
    date_text = pd.Timestamp(trade_date).strftime("%Y-%m-%d") if trade_date is not None else None
    issues: list[DataQualityIssue] = []
    if len(raw_df) < 96:
        issues.append(
            DataQualityIssue(
                task_type=task_type,
                severity="error",
                action=blocking_action,
                issue_type="insufficient_rows",
                file_path=str(file_path),
                sheet_name=str(sheet_name),
                date=date_text,
                message=f"有效时点不足 96 行，当前 {len(raw_df)} 行",
            )
        )
        return issues

    day_df = raw_df.copy().iloc[:96].reset_index(drop=True)
    day_df.columns = [str(column).strip() for column in day_df.columns]
    required_fields = [
        ("总加电力值(MW)", HISTORY_TOTAL_POWER_CANDIDATES),
        ("电力值(MW)", HISTORY_POWER_CANDIDATES),
    ]
    if require_target:
        required_fields.append(("日前出清价格(元/MWh)", HISTORY_TARGET_CANDIDATES))

    for display_name, candidates in required_fields:
        column = resolve_column(day_df.columns, candidates)
        if not column:
            add_missing_field_issue(
                issues,
                task_type=task_type,
                action=blocking_action,
                file_path=file_path,
                sheet_name=sheet_name,
                date=date_text,
                field=display_name,
                candidates=candidates,
            )
            continue
        add_numeric_issues(
            issues,
            task_type=task_type,
            severity="error",
            action=blocking_action,
            issue_type="invalid_numeric",
            file_path=file_path,
            sheet_name=sheet_name,
            date=date_text,
            field=column,
            series=day_df[column],
        )

    thermal_col = resolve_column(day_df.columns, THERMAL_CANDIDATES)
    if task_type == "predict":
        if not thermal_col:
            add_missing_field_issue(
                issues,
                task_type=task_type,
                action=blocking_action,
                file_path=file_path,
                sheet_name=sheet_name,
                date=date_text,
                field="火电开机容量",
                candidates=THERMAL_CANDIDATES,
            )
            return issues
        add_numeric_issues(
            issues,
            task_type=task_type,
            severity="error",
            action=blocking_action,
            issue_type="invalid_numeric",
            file_path=file_path,
            sheet_name=sheet_name,
            date=date_text,
            field=thermal_col,
            series=day_df[thermal_col].ffill().bfill(),
        )
        return issues

    overview_col = resolve_column(day_df.columns, OVERVIEW_CANDIDATES)
    if not overview_col:
        add_missing_field_issue(
            issues,
            task_type=task_type,
            action=blocking_action,
            file_path=file_path,
            sheet_name=sheet_name,
            date=date_text,
            field="日前-出清概况",
            candidates=OVERVIEW_CANDIDATES,
        )
        return issues

    overview_series = day_df[overview_col].ffill().bfill()
    extracted_capacity = overview_series.map(extract_running_unit_capacity)
    missing_capacity = extracted_capacity.isna()
    for index in extracted_capacity[missing_capacity].index:
        issues.append(
            DataQualityIssue(
                task_type=task_type,
                severity="error",
                action=blocking_action,
                issue_type="missing_thermal_capacity",
                file_path=str(file_path),
                sheet_name=str(sheet_name),
                date=date_text,
                period=int(index) + 1,
                field=overview_col,
                value=safe_value(day_df.loc[index, overview_col]),
                message="日前-出清概况中无法提取“运行机组容量”，该字段是火电开机容量的关键来源",
            )
        )
    return issues


def validate_forecast_template(
    raw_df: pd.DataFrame,
    *,
    file_path: Path,
    sheet_name: str,
    default_year: int,
    require_reference_price: bool = True,
) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    if len(raw_df) < 96:
        issues.append(
            DataQualityIssue(
                task_type="predict",
                severity="error",
                action="blocked",
                issue_type="insufficient_rows",
                file_path=str(file_path),
                sheet_name=str(sheet_name),
                message=f"有效时点不足 96 行，当前 {len(raw_df)} 行",
            )
        )
        return issues

    df = raw_df.copy().reset_index(drop=True)
    df.columns = [str(column).strip() for column in df.columns]
    header_dates = []
    for column in df.columns:
        month_day = extract_month_day(column)
        if month_day is not None:
            header_dates.append(pd.Timestamp(year=default_year, month=month_day[0], day=month_day[1]).normalize())
    unique_dates = sorted(set(header_dates))
    if len(unique_dates) < 2:
        issues.append(
            DataQualityIssue(
                task_type="predict",
                severity="error",
                action="blocked",
                issue_type="unrecognized_forecast_dates",
                file_path=str(file_path),
                sheet_name=str(sheet_name),
                message="预测模板至少需要识别参考日和预测日两个日期列；支持日期格式示例：5月1日、5.1日、5/1、5-1，并建议写在字段表头中，例如 5.1日剩余电力值、5.1日日前出清价格、5.2日剩余电力值",
            )
        )
        return issues

    reference_date = unique_dates[-2]
    target_date = unique_dates[-1]
    reference_text = reference_date.strftime("%Y-%m-%d")
    target_text = target_date.strftime("%Y-%m-%d")

    target_net_load_col = resolve_forecast_template_column(df.columns, target_date, FORECAST_NET_LOAD_CANDIDATES)
    target_total_col = resolve_forecast_template_column(df.columns, target_date, FORECAST_TOTAL_POWER_CANDIDATES)
    target_power_col = resolve_forecast_template_column(df.columns, target_date, FORECAST_POWER_CANDIDATES)
    reference_net_load_col = resolve_forecast_template_column(df.columns, reference_date, FORECAST_NET_LOAD_CANDIDATES)
    reference_total_col = resolve_forecast_template_column(df.columns, reference_date, FORECAST_TOTAL_POWER_CANDIDATES)
    reference_power_col = resolve_forecast_template_column(df.columns, reference_date, FORECAST_POWER_CANDIDATES)
    reference_price_col = resolve_forecast_template_column(df.columns, reference_date, HISTORY_TARGET_CANDIDATES)

    if target_net_load_col:
        add_numeric_issues(issues, task_type="predict", severity="error", action="blocked", issue_type="invalid_numeric", file_path=file_path, sheet_name=sheet_name, date=target_text, field=target_net_load_col, series=df[target_net_load_col])
    elif target_total_col and target_power_col:
        add_numeric_issues(issues, task_type="predict", severity="error", action="blocked", issue_type="invalid_numeric", file_path=file_path, sheet_name=sheet_name, date=target_text, field=target_total_col, series=df[target_total_col])
        add_numeric_issues(issues, task_type="predict", severity="error", action="blocked", issue_type="invalid_numeric", file_path=file_path, sheet_name=sheet_name, date=target_text, field=target_power_col, series=df[target_power_col])
    else:
        add_missing_field_issue(issues, task_type="predict", action="blocked", file_path=file_path, sheet_name=sheet_name, date=target_text, field="预测日火电空间", candidates=FORECAST_NET_LOAD_CANDIDATES + FORECAST_TOTAL_POWER_CANDIDATES + FORECAST_POWER_CANDIDATES)

    if reference_net_load_col:
        add_numeric_issues(issues, task_type="predict", severity="error", action="blocked", issue_type="invalid_numeric", file_path=file_path, sheet_name=sheet_name, date=reference_text, field=reference_net_load_col, series=df[reference_net_load_col])
    elif reference_total_col and reference_power_col:
        add_numeric_issues(issues, task_type="predict", severity="error", action="blocked", issue_type="invalid_numeric", file_path=file_path, sheet_name=sheet_name, date=reference_text, field=reference_total_col, series=df[reference_total_col])
        add_numeric_issues(issues, task_type="predict", severity="error", action="blocked", issue_type="invalid_numeric", file_path=file_path, sheet_name=sheet_name, date=reference_text, field=reference_power_col, series=df[reference_power_col])
    else:
        add_missing_field_issue(issues, task_type="predict", action="blocked", file_path=file_path, sheet_name=sheet_name, date=reference_text, field="参考日火电空间", candidates=FORECAST_NET_LOAD_CANDIDATES + FORECAST_TOTAL_POWER_CANDIDATES + FORECAST_POWER_CANDIDATES)

    if not reference_price_col and require_reference_price:
        add_missing_field_issue(issues, task_type="predict", action="blocked", file_path=file_path, sheet_name=sheet_name, date=reference_text, field="参考日前日价格", candidates=HISTORY_TARGET_CANDIDATES)
    elif reference_price_col:
        add_numeric_issues(issues, task_type="predict", severity="error", action="blocked", issue_type="invalid_numeric", file_path=file_path, sheet_name=sheet_name, date=reference_text, field=reference_price_col, series=df[reference_price_col])

    period_col = resolve_column(df.columns, PERIOD_CANDIDATES)
    if period_col:
        add_numeric_issues(issues, task_type="predict", severity="error", action="blocked", issue_type="invalid_period", file_path=file_path, sheet_name=sheet_name, date=target_text, field=period_col, series=df[period_col])

    thermal_col = resolve_column(df.columns, THERMAL_CANDIDATES)
    if not thermal_col:
        add_missing_field_issue(issues, task_type="predict", action="blocked", file_path=file_path, sheet_name=sheet_name, date=target_text, field="火电开机容量", candidates=THERMAL_CANDIDATES)
    else:
        add_numeric_issues(issues, task_type="predict", severity="error", action="blocked", issue_type="invalid_numeric", file_path=file_path, sheet_name=sheet_name, date=target_text, field=thermal_col, series=df[thermal_col].ffill().bfill())

    return issues


def has_blocking_issues(issues: list[DataQualityIssue]) -> bool:
    return any(issue.severity == "error" and issue.action in {"skipped", "blocked"} for issue in issues)


def issue_to_dict(issue: DataQualityIssue) -> dict:
    return asdict(issue)


def build_quality_summary(issues: list[DataQualityIssue]) -> dict[str, int]:
    skipped_sheet_keys = {
        (issue.file_path, issue.sheet_name, issue.date)
        for issue in issues
        if issue.action == "skipped"
    }
    return {
        "total_issues": len(issues),
        "errors": sum(1 for issue in issues if issue.severity == "error"),
        "warnings": sum(1 for issue in issues if issue.severity == "warning"),
        "skipped_sheets": len(skipped_sheet_keys),
        "blocked_issues": sum(1 for issue in issues if issue.action == "blocked"),
        "recorded_issues": sum(1 for issue in issues if issue.action == "recorded"),
    }


def save_quality_report(
    *,
    task_type: str,
    status: str,
    issues: list[DataQualityIssue],
    report_dir: Path = DEFAULT_REPORT_DIR,
    metadata: dict | None = None,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    report_id = f"{task_type}_{timestamp}"
    payload = {
        "report_id": report_id,
        "task_type": task_type,
        "status": status,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": build_quality_summary(issues),
        "metadata": metadata or {},
        "issues": [issue_to_dict(issue) for issue in issues],
    }
    report_path = report_dir / f"{report_id}.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def load_quality_report(report_id: str, report_dir: Path = DEFAULT_REPORT_DIR) -> dict:
    safe_id = Path(report_id).stem
    path = report_dir / f"{safe_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"数据异常报告不存在：{safe_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_quality_reports(report_dir: Path = DEFAULT_REPORT_DIR) -> list[dict]:
    if not report_dir.exists():
        return []
    reports: list[dict] = []
    for path in sorted(report_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        reports.append(
            {
                "report_id": payload.get("report_id") or path.stem,
                "task_type": payload.get("task_type"),
                "status": payload.get("status"),
                "created_at": payload.get("created_at"),
                "summary": payload.get("summary") or {},
                "path": str(path),
            }
        )
    return reports


def latest_quality_report(report_dir: Path = DEFAULT_REPORT_DIR) -> dict | None:
    reports = list_quality_reports(report_dir)
    if not reports:
        return None
    return load_quality_report(str(reports[0]["report_id"]), report_dir)
