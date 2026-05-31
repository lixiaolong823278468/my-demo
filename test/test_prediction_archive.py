from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class PredictionArchiveTests(unittest.TestCase):
    def test_archive_detail_reports_realtime_direction_accuracy(self) -> None:
        from prediction_archive import archive_prediction_metrics

        merged = pd.DataFrame(
            {
                "date": ["2026-05-15"] * 3,
                "period": [1, 2, 3],
                "actual_price": [100.0, 110.0, 105.0],
                "predicted_price": [101.0, 111.0, 106.0],
                "realtime_actual_price": [90.0, 120.0, 100.0],
                "realtime_predicted_price": [91.0, 119.0, 101.0],
            }
        )

        metrics = archive_prediction_metrics(merged, {"forecast_date": "2026-05-15"})

        self.assertIn("direction_accuracy", metrics["realtime_predicted_price"])

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

    def test_fingerprint_changes_when_scenario_reference_price_changes(self) -> None:
        from prediction_archive import prediction_fingerprint

        base = {
            "forecast_date": "2026-05-15",
            "reference_strategy_key": "recent_n_days",
            "reference_days_requested": 3,
            "model_run_id": "run_a",
            "selected_segment_price_models": {"segment_1": "model_a"},
            "rows": [
                {"period": 1, "predicted_price": 100.0, "scenario_similarity_adjusted_price": 95.0},
            ],
        }
        changed_reference = {
            **base,
            "rows": [
                {"period": 1, "predicted_price": 100.0, "scenario_similarity_adjusted_price": 90.0},
            ],
        }

        self.assertNotEqual(prediction_fingerprint(base), prediction_fingerprint(changed_reference))

    def test_fingerprint_changes_when_realtime_prediction_changes(self) -> None:
        from prediction_archive import prediction_fingerprint

        base = {
            "forecast_date": "2026-05-15",
            "reference_strategy_key": "recent_n_days",
            "reference_days_requested": 3,
            "model_run_id": "run_a",
            "selected_segment_price_models": {"segment_1": "model_a"},
            "rows": [
                {"period": 1, "predicted_price": 100.0, "realtime_predicted_price": 95.0},
            ],
        }
        changed_realtime_prediction = {
            **base,
            "rows": [
                {"period": 1, "predicted_price": 100.0, "realtime_predicted_price": 90.0},
            ],
        }

        self.assertNotEqual(prediction_fingerprint(base), prediction_fingerprint(changed_realtime_prediction))

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

    def test_archive_combines_reference_strategies_into_one_record(self) -> None:
        from prediction_archive import archive_prediction_bundle, load_prediction_archive_detail, list_prediction_archives

        root = Path(__file__).resolve().parent / ".test_tmp" / f"archive_combined_{time.time_ns()}"
        prediction = {
            "forecast_date": "2026-05-15",
            "selected_strategy_key": "recent_n_days",
            "comparison_predictions": {
                "recent_n_days": {
                    "forecast_date": "2026-05-15",
                    "reference_strategy_key": "recent_n_days",
                    "reference_strategy_label": "最近 N 天",
                    "reference_days_requested": 3,
                    "reference_dates": ["2026-05-14", "2026-05-13", "2026-05-12"],
                    "rows": [{"date": "2026-05-15", "period": 1, "predicted_price": 100.0}],
                },
                "recent_same_type_days": {
                    "forecast_date": "2026-05-15",
                    "reference_strategy_key": "recent_same_type_days",
                    "reference_strategy_label": "最近 N 个同类型日",
                    "reference_days_requested": 8,
                    "reference_dates": ["2026-05-08"],
                    "rows": [{"date": "2026-05-15", "period": 1, "predicted_price": 102.0}],
                },
            },
        }
        metadata = {"run_id": "run_a", "selected_segment_price_models": {}}

        saved = archive_prediction_bundle(prediction, metadata, root, "forecast.xlsx", "output.xlsx")
        archives = list_prediction_archives(root, "2026-05-15")
        detail = load_prediction_archive_detail(root, saved["saved"][0]["archive_id"], history_dir=root / "empty_history")

        self.assertEqual(len(saved["saved"]), 1)
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0]["reference_days_by_strategy"]["recent_n_days"], 3)
        self.assertEqual(archives[0]["reference_days_by_strategy"]["recent_same_type_days"], 8)
        self.assertIn("recent_n_days", detail["comparison_predictions"])
        self.assertIn("recent_same_type_days", detail["comparison_predictions"])

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
                        {
                            "date": "2026-05-15",
                            "period": 1,
                            "predicted_price": 100.0,
                            "scenario_similarity_adjusted_price": 92.0,
                            "similarity_blend_weight": 0.4,
                            "similarity_adjustment_reason": "renewable_high_net_load_low_model_above_similarity",
                            "net_load_only_similar_price": 95.0,
                        },
                        {
                            "date": "2026-05-15",
                            "period": 2,
                            "predicted_price": 200.0,
                            "scenario_similarity_adjusted_price": 215.0,
                            "similarity_blend_weight": 0.3,
                            "similarity_adjustment_reason": "renewable_high_net_load_low_model_above_similarity",
                            "net_load_only_similar_price": 210.0,
                        },
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
        self.assertEqual(detail["prediction_metrics"]["predicted_price"]["mae"], 15.0)
        self.assertEqual(detail["prediction_metrics"]["scenario_similarity_adjusted_price"]["mae"], 3.5)
        self.assertEqual(len(detail["rows"]), 2)
        self.assertEqual(detail["rows"][0]["scenario_similarity_adjusted_price"], 92.0)
        self.assertEqual(
            detail["comparison_predictions"]["recent_n_days"]["prediction_metrics"]["scenario_similarity_adjusted_price"]["mae"],
            3.5,
        )

    def test_archive_detail_computes_realtime_metrics_against_realtime_actual_prices(self) -> None:
        from prediction_archive import archive_prediction_bundle, load_prediction_archive_detail

        root = Path(__file__).resolve().parent / ".test_tmp" / f"archive_realtime_actual_{time.time_ns()}"
        history_dir = root / "history"
        history_dir.mkdir(parents=True)
        frame = pd.DataFrame(
            {
                "序号": list(range(1, 97)),
                "总加电力值(MW)": [1000.0] * 96,
                "电力值(MW)": [100.0] * 96,
                "日前出清价格(元/MWh)": [90.0, 220.0, *([100.0] * 94)],
                "实时出清价格(元/MWh)": [80.0, 240.0, *([100.0] * 94)],
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
                        {"date": "2026-05-15", "period": 1, "predicted_price": 100.0, "realtime_predicted_price": 85.0},
                        {"date": "2026-05-15", "period": 2, "predicted_price": 200.0, "realtime_predicted_price": 230.0},
                    ],
                }
            },
        }
        metadata = {"run_id": "run_a", "model_root": str(root / "models"), "selected_segment_price_models": {}}

        saved = archive_prediction_bundle(prediction, metadata, root, "forecast.xlsx", "output.xlsx")["saved"][0]
        detail = load_prediction_archive_detail(root, saved["archive_id"], history_dir=history_dir, model_root=root / "models")

        self.assertEqual(detail["rows"][0]["actual_price"], 90.0)
        self.assertEqual(detail["rows"][0]["realtime_actual_price"], 80.0)
        self.assertEqual(detail["prediction_metrics"]["predicted_price"]["mae"], 15.0)
        self.assertEqual(detail["prediction_metrics"]["realtime_predicted_price"]["mae"], 7.5)
        self.assertEqual(
            detail["comparison_predictions"]["recent_n_days"]["prediction_metrics"]["realtime_predicted_price"]["mae"],
            7.5,
        )


if __name__ == "__main__":
    unittest.main()
