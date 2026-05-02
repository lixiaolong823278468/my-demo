from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd


class DataQualityTests(unittest.TestCase):
    overview_text = (
        "04月30日,直调用电预测最大负荷3082.25万千瓦，最小1941.21万千瓦；"
        "日前现货市场火电机组运行91台，运行机组容量36095.00MW；"
        "火电机组必开0台次、必开容量0MW。"
    )

    def make_history_frame(self, total_value: object = 100.0) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "总加电力值(MW)": [total_value] + [100.0] * 95,
                "电力值(MW)": [20.0] * 96,
                "日前出清价格(元/MWh)": [300.0] * 96,
                "日前-出清概况": [self.overview_text] * 96,
            }
        )

    def test_extracts_running_unit_capacity_from_overview(self) -> None:
        from dayahead_core import extract_thermal_on_capacity

        self.assertEqual(extract_thermal_on_capacity(self.overview_text), 36095.0)

    def test_does_not_use_must_run_capacity_as_thermal_capacity(self) -> None:
        from dayahead_core import extract_thermal_on_capacity

        text = "火电机组必开0台次、必开容量0MW，必停43台次、必停容量10461.00MW。"

        self.assertTrue(pd.isna(extract_thermal_on_capacity(text)))

    def test_history_sheet_invalid_numeric_marks_sheet_skipped(self) -> None:
        from data_quality import has_blocking_issues, validate_history_sheet

        issues = validate_history_sheet(
            self.make_history_frame(total_value="乱码"),
            file_path=Path("history.xlsx"),
            sheet_name="2026-05-01",
            trade_date=pd.Timestamp("2026-05-01"),
            require_target=True,
        )

        self.assertTrue(has_blocking_issues(issues))
        self.assertTrue(any(issue.period == 1 for issue in issues))
        self.assertTrue(any(issue.field == "总加电力值(MW)" for issue in issues))
        self.assertTrue(any(issue.action == "skipped" for issue in issues))

    def test_forecast_template_missing_reference_price_blocks_prediction(self) -> None:
        from data_quality import has_blocking_issues, validate_forecast_template

        frame = pd.DataFrame(
            {
                "序号": list(range(1, 97)),
                "5月1日剩余电力值(MW)": [80.0] * 96,
                "5月2日剩余电力值(MW)": [90.0] * 96,
            }
        )

        issues = validate_forecast_template(
            frame,
            file_path=Path("forecast.xlsx"),
            sheet_name="Sheet1",
            default_year=2026,
        )

        self.assertTrue(has_blocking_issues(issues))
        self.assertTrue(any(issue.issue_type == "missing_required_field" for issue in issues))
        self.assertTrue(any(issue.action == "blocked" for issue in issues))

    def test_forecast_template_accepts_dot_date_headers(self) -> None:
        from data_quality import has_blocking_issues, validate_forecast_template

        frame = pd.DataFrame(
            {
                "序号": list(range(1, 97)),
                "5.1日风光电力值(MW)": [20.0] * 96,
                "5.1日总加电力值(MW)": [100.0] * 96,
                "5.1日剩余电力值": [80.0] * 96,
                "5.1日日前出清价格(元/MWh)": [300.0] * 96,
                "5.2日风光电力值(MW)": [25.0] * 96,
                "5.2日总加电力值(MW)": [110.0] * 96,
                "5.2日剩余电力值": [85.0] * 96,
                "火电开机容量": [36095.0] * 96,
            }
        )

        issues = validate_forecast_template(
            frame,
            file_path=Path("forecast.xlsx"),
            sheet_name="Sheet1",
            default_year=2026,
        )

        self.assertFalse(has_blocking_issues(issues))

    def test_forecast_template_date_error_includes_supported_formats(self) -> None:
        from data_quality import validate_forecast_template

        frame = pd.DataFrame(
            {
                "序号": list(range(1, 97)),
                "预测日剩余电力值": [85.0] * 96,
            }
        )

        issues = validate_forecast_template(
            frame,
            file_path=Path("forecast.xlsx"),
            sheet_name="Sheet1",
            default_year=2026,
        )

        self.assertTrue(any("支持日期格式" in issue.message for issue in issues))

    def test_history_sheet_missing_running_unit_capacity_is_blocking(self) -> None:
        from data_quality import has_blocking_issues, validate_history_sheet

        frame = self.make_history_frame()
        frame["日前-出清概况"] = ["火电机组必开0台次、必开容量0MW。"] * 96

        issues = validate_history_sheet(
            frame,
            file_path=Path("history.xlsx"),
            sheet_name="2026-05-01",
            trade_date=pd.Timestamp("2026-05-01"),
            require_target=True,
        )

        self.assertTrue(has_blocking_issues(issues))
        self.assertTrue(any(issue.issue_type == "missing_thermal_capacity" for issue in issues))

    def test_forecast_thermal_capacity_column_is_required_and_blocking(self) -> None:
        from data_quality import has_blocking_issues, validate_forecast_template

        frame = pd.DataFrame(
            {
                "序号": list(range(1, 97)),
                "5.1日剩余电力值": [80.0] * 96,
                "5.1日日前出清价格(元/MWh)": [300.0] * 96,
                "5.2日剩余电力值": [85.0] * 96,
            }
        )

        issues = validate_forecast_template(
            frame,
            file_path=Path("forecast.xlsx"),
            sheet_name="Sheet1",
            default_year=2026,
        )

        self.assertTrue(has_blocking_issues(issues))
        self.assertTrue(any(issue.field == "火电开机容量" for issue in issues))

    def test_report_save_list_and_load_round_trip(self) -> None:
        from data_quality import DataQualityIssue, list_quality_reports, load_quality_report, save_quality_report

        report_dir = Path(__file__).resolve().parent / ".test_tmp" / "data_quality_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        for old_report in report_dir.glob("*.json"):
            old_report.unlink()

        report_path = save_quality_report(
            task_type="train",
            status="completed_with_issues",
            issues=[
                DataQualityIssue(
                    task_type="train",
                    severity="error",
                    action="skipped",
                    issue_type="invalid_numeric",
                    file_path="history.xlsx",
                    sheet_name="2026-05-01",
                    date="2026-05-01",
                    period=1,
                    field="总加电力值(MW)",
                    value="乱码",
                    message="字段无法转换为数字",
                )
            ],
            report_dir=report_dir,
        )

        raw = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["summary"]["total_issues"], 1)
        self.assertEqual(raw["summary"]["skipped_sheets"], 1)

        reports = list_quality_reports(report_dir)
        self.assertEqual(len(reports), 1)
        loaded = load_quality_report(raw["report_id"], report_dir)
        self.assertEqual(loaded["issues"][0]["field"], "总加电力值(MW)")

    def test_core_builder_skips_invalid_history_sheet_and_keeps_valid_sheet(self) -> None:
        from dayahead_core import DayAheadDataBuilder

        test_dir = Path(__file__).resolve().parent / ".test_tmp" / "history_quality"
        test_dir.mkdir(parents=True, exist_ok=True)
        workbook_path = test_dir / "history_quality.xlsx"
        with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
            self.make_history_frame().to_excel(writer, sheet_name="2026-05-01", index=False)
            self.make_history_frame(total_value="乱码").to_excel(writer, sheet_name="2026-05-02", index=False)

        builder = DayAheadDataBuilder()
        with self.assertWarns(UserWarning):
            frame = builder.load_excel_collection(workbook_path, require_target=True)

        self.assertEqual(len(frame), 96)
        self.assertEqual(frame["date"].dt.strftime("%Y-%m-%d").unique().tolist(), ["2026-05-01"])
        self.assertEqual(len(builder.skipped_sheets), 1)
        self.assertTrue(any(issue.period == 1 and issue.action == "skipped" for issue in builder.quality_issues))

    def test_core_builder_uses_overview_running_capacity_as_thermal_capacity(self) -> None:
        from dayahead_core import DayAheadDataBuilder

        builder = DayAheadDataBuilder()
        frame = builder.prepare_single_sheet(
            self.make_history_frame(),
            file_path=Path("history.xlsx"),
            sheet_name="2026-05-01",
            trade_date=pd.Timestamp("2026-05-01"),
            require_target=True,
        )

        self.assertEqual(float(frame.loc[0, "thermal_on_capacity"]), 36095.0)


if __name__ == "__main__":
    unittest.main()
