from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class PredictionArchiveTests(unittest.TestCase):
    def test_fingerprint_uses_prices_rounded_to_two_decimals(self) -> None:
        from prediction_archive import prediction_fingerprint

        base = {
            "forecast_date": "2026-05-15",
            "reference_strategy_key": "recent_n_days",
            "reference_days_requested": 3,
            "model_run_id": "run_a",
            "selected_segment_price_models": {"segment_1": "model_a"},
            "rows": [
                {"period": 1, "predicted_price": 100.004},
                {"period": 2, "predicted_price": 200.005},
            ],
        }
        same_after_rounding = {
            **base,
            "rows": [
                {"period": 1, "predicted_price": 100.003},
                {"period": 2, "predicted_price": 200.004},
            ],
        }
        different_after_rounding = {
            **base,
            "rows": [
                {"period": 1, "predicted_price": 100.02},
                {"period": 2, "predicted_price": 200.005},
            ],
        }

        self.assertEqual(prediction_fingerprint(base), prediction_fingerprint(same_after_rounding))
        self.assertNotEqual(prediction_fingerprint(base), prediction_fingerprint(different_after_rounding))

    def test_archive_skips_duplicate_predictions(self) -> None:
        from prediction_archive import archive_prediction_bundle, list_prediction_archives

        root = Path(__file__).resolve().parent / ".test_tmp" / f"archive_{time.time_ns()}"
        prediction = {
            "forecast_date": "2026-05-15",
            "comparison_predictions": {
                "recent_n_days": {
                    "forecast_date": "2026-05-15",
                    "reference_strategy_key": "recent_n_days",
                    "reference_strategy_label": "最近 N 天",
                    "reference_days_requested": 3,
                    "reference_dates": ["2026-05-14"],
                    "rows": [{"date": "2026-05-15", "period": 1, "predicted_price": 100.004}],
                }
            },
        }
        metadata = {
            "run_id": "run_a",
            "model_type": "direct_price_multi_model",
            "segment_config": [{"name": "segment_1", "start": 1, "end": 96}],
            "selected_segment_price_models": {"segment_1": "model_a"},
        }

        first = archive_prediction_bundle(prediction, metadata, root, "forecast.xlsx", "output.xlsx")
        second = archive_prediction_bundle(prediction, metadata, root, "forecast.xlsx", "output.xlsx")
        archives = list_prediction_archives(root, "2026-05-15")

        self.assertEqual(len(first["saved"]), 1)
        self.assertEqual(len(second["saved"]), 0)
        self.assertEqual(len(second["skipped_duplicates"]), 1)
        self.assertEqual(len(archives), 1)

    def test_archive_detail_reports_missing_actual_prices(self) -> None:
        from prediction_archive import archive_prediction_bundle, load_prediction_archive_detail

        root = Path(__file__).resolve().parent / ".test_tmp" / f"archive_missing_actual_{time.time_ns()}"
        prediction = {
            "forecast_date": "2026-05-15",
            "comparison_predictions": {
                "recent_n_days": {
                    "forecast_date": "2026-05-15",
                    "reference_strategy_key": "recent_n_days",
                    "reference_strategy_label": "最近 N 天",
                    "reference_days_requested": 1,
                    "reference_dates": [],
                    "rows": [{"date": "2026-05-15", "period": 1, "predicted_price": 100.0}],
                }
            },
        }
        metadata = {"run_id": "run_a", "selected_segment_price_models": {}}

        saved = archive_prediction_bundle(prediction, metadata, root, "forecast.xlsx", "output.xlsx")["saved"][0]
        detail = load_prediction_archive_detail(root, saved["archive_id"], history_dir=root / "empty_history")

        self.assertFalse(detail["actual_available"])
        self.assertEqual(detail["message"], "暂无实际价格数据")
        self.assertIsNone(detail["metrics"])

    def test_archive_detail_computes_metrics_when_actual_prices_exist(self) -> None:
        from prediction_archive import archive_prediction_bundle, load_prediction_archive_detail

        root = Path(__file__).resolve().parent / ".test_tmp" / f"archive_actual_{time.time_ns()}"
        history_dir = root / "history"
        history_dir.mkdir(parents=True)
        frame = pd.DataFrame(
            {
                "序号": list(range(1, 97)),
                "总加电力值(MW)": [1000.0] * 96,
                "电力值(MW)": [100.0] * 96,
                "日前出清价格(元/MWh)": [90.0, 220.0, *([100.0] * 94)],
                "日前-出清概况": ["火电开机容量1000MW"] * 96,
            }
        )
        with pd.ExcelWriter(history_dir / "2026年5月.xlsx", engine="openpyxl") as writer:
            frame.to_excel(writer, sheet_name="2026-05-15", index=False)
        prediction = {
            "forecast_date": "2026-05-15",
            "comparison_predictions": {
                "recent_n_days": {
                    "forecast_date": "2026-05-15",
                    "reference_strategy_key": "recent_n_days",
                    "reference_strategy_label": "最近 N 天",
                    "reference_days_requested": 1,
                    "reference_dates": [],
                    "rows": [
                        {"date": "2026-05-15", "period": 1, "predicted_price": 100.0, "net_load_only_similar_price": 95.0},
                        {"date": "2026-05-15", "period": 2, "predicted_price": 200.0, "net_load_only_similar_price": 210.0},
                    ],
                }
            },
        }
        metadata = {"run_id": "run_a", "model_root": str(root / "models"), "selected_segment_price_models": {}}

        saved = archive_prediction_bundle(prediction, metadata, root, "forecast.xlsx", "output.xlsx")["saved"][0]
        with patch("prediction_archive.DayAheadDataBuilder.load_excel_collection", side_effect=AssertionError("should not load full history")):
            detail = load_prediction_archive_detail(root, saved["archive_id"], history_dir=history_dir, model_root=root / "models")

        self.assertTrue(detail["actual_available"])
        self.assertEqual(detail["metrics"]["mae"], 15.0)
        self.assertEqual(len(detail["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
