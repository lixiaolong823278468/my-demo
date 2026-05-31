from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def write_metadata(path: Path, metadata: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")


class ModelVersionListingTests(unittest.TestCase):
    def test_realtime_version_activation_does_not_replace_dayahead_current(self) -> None:
        from api_server import activate_model_version_for_target

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "models"
            write_metadata(root / "current", {"run_id": "run_day"})
            write_metadata(root / "realtime_price" / "current", {"run_id": "run_rt_old"})
            write_metadata(root / "realtime_price" / "history" / "run_rt_new", {"run_id": "run_rt_new"})

            activate_model_version_for_target("realtime", "run_rt_new", model_root=root)

            day = json.loads((root / "current" / "metadata.json").read_text(encoding="utf-8"))
            realtime = json.loads((root / "realtime_price" / "current" / "metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(day["run_id"], "run_day")
        self.assertEqual(realtime["run_id"], "run_rt_new")

    def test_protected_versions_are_scoped_to_realtime_root(self) -> None:
        from api_server import protected_versions

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "models"
            write_metadata(root / "current", {"run_id": "run_shared"})
            write_metadata(root / "history" / "run_shared", {"run_id": "run_shared"})
            write_metadata(root / "realtime_price" / "current", {"run_id": "run_rt"})
            write_metadata(root / "realtime_price" / "history" / "run_rt", {"run_id": "run_rt"})
            write_metadata(root / "realtime_price" / "history" / "run_shared", {"run_id": "run_shared"})

            realtime_protected = protected_versions("realtime", model_root=root)

        self.assertIn("run_rt", realtime_protected)
        self.assertNotIn("run_shared", realtime_protected)

    def test_model_versions_endpoint_can_list_realtime_versions(self) -> None:
        from api_server import list_model_versions_for_target

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "models"
            metadata = {"run_id": "run_rt", "target_market": "realtime", "created_at": "2026-05-31 10:00:00"}
            write_metadata(root / "realtime_price" / "current", metadata)
            write_metadata(root / "realtime_price" / "history" / "run_rt", metadata)

            versions = list_model_versions_for_target("realtime", model_root=root)

        self.assertEqual(versions[0]["run_id"], "run_rt")
        self.assertEqual(versions[0]["target_market"], "realtime")

    def test_segment_selection_updates_realtime_metadata_only(self) -> None:
        from api_server import update_segment_price_model_selection_for_target

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "models"
            day_metadata = {
                "run_id": "run_day",
                "segment_config": [{"name": "segment_1"}],
                "model_variants": {"no_lag_96_lightgbm": {}},
            }
            rt_metadata = {
                "run_id": "run_rt",
                "segment_config": [{"name": "segment_1"}],
                "model_variants": {"no_lag_96_xgboost": {}},
            }
            write_metadata(root / "current", day_metadata)
            write_metadata(root / "history" / "run_day", day_metadata)
            write_metadata(root / "realtime_price" / "current", rt_metadata)
            write_metadata(root / "realtime_price" / "history" / "run_rt", rt_metadata)

            update_segment_price_model_selection_for_target(
                "realtime",
                {"segment_1": "no_lag_96_xgboost"},
                model_root=root,
            )

            day = json.loads((root / "current" / "metadata.json").read_text(encoding="utf-8"))
            rt = json.loads((root / "realtime_price" / "current" / "metadata.json").read_text(encoding="utf-8"))

        self.assertNotIn("selected_segment_price_models", day)
        self.assertEqual(rt["selected_segment_price_models"]["segment_1"], "no_lag_96_xgboost")

    def test_thermal_capacity_variant_selection_uses_lowest_score(self) -> None:
        from dayahead_core import select_best_thermal_capacity_variant

        selected = select_best_thermal_capacity_variant(
            {
                "thermal_capacity_xgboost": {"overall": {"score": 15.0}},
                "thermal_capacity_ridge": {"overall": {"score": 8.0}},
                "thermal_capacity_catboost": {"overall": {"score": None}},
            }
        )

        self.assertEqual(selected, "thermal_capacity_ridge")

    def test_thermal_capacity_model_metadata_records_candidate_variants(self) -> None:
        import pandas as pd

        from dayahead_core import train_thermal_capacity_model

        rows = []
        for day in range(12):
            date = pd.Timestamp("2026-05-01") + pd.Timedelta(days=day)
            for period in range(1, 97):
                total_load = 10000 + day * 80 + period * 2
                renewable = 2500 + (period % 12) * 20
                rows.append(
                    {
                        "date": date,
                        "period": period,
                        "total_load": total_load,
                        "renewable_power": renewable,
                        "net_load": total_load - renewable,
                        "thermal_space_load_ratio": 0.55,
                        "weekday": date.weekday(),
                        "month": date.month,
                        "is_weekend": int(date.weekday() >= 5),
                        "is_holiday": 0,
                        "thermal_on_capacity": 7200 + day * 60,
                    }
                )

        with TemporaryDirectory() as temp_dir:
            metadata = train_thermal_capacity_model(
                pd.DataFrame(rows),
                Path(temp_dir) / "thermal_capacity_model",
                valid_days=3,
                num_boost_round=5,
                backends={"ridge": "Ridge", "xgboost": "XGBoost"},
            )

        self.assertTrue(metadata["enabled"])
        self.assertIn(metadata["selected_model_key"], metadata["model_variants"])
        self.assertIn(metadata["selected_model_key"], metadata["variant_metrics"])
        self.assertEqual(set(metadata["model_variants"]), {"thermal_capacity_ridge", "thermal_capacity_xgboost"})
        selected_variant = metadata["model_variants"][metadata["selected_model_key"]]
        self.assertEqual(metadata["selected_model_backend"], selected_variant["model_backend"])
        self.assertEqual(metadata["metrics"], metadata["variant_metrics"][metadata["selected_model_key"]])
        self.assertTrue(str(metadata["model_path"]).startswith("thermal_capacity_model/"))

    def test_versions_include_summary_and_detail_for_all_model_modules(self) -> None:
        from dayahead_core import list_model_versions

        with TemporaryDirectory() as temp_dir:
            model_root = Path(temp_dir)
            metadata = {
                "run_id": "run_20260520_120000",
                "created_at": "2026-05-20 12:00:00",
                "train_start_date": "2026-04-01",
                "train_end_date": "2026-05-19",
                "training_window_days": 45,
                "valid_days": 5,
                "num_boost_round": 180,
                "sample_rows": 4320,
                "training_mode": "rolling_window",
                "selected_model_key": "no_lag_96",
                "selected_model_backend": "xgboost",
                "selected_model_backend_label": "XGBoost",
                "segment_config": [{"name": "morning_peak"}, {"name": "evening_peak"}],
                "metrics": {
                    "morning_peak": {
                        "baseline_mae": 62.5,
                        "baseline_rmse": 81.2,
                        "final_mae": 31.4,
                        "final_rmse": 45.1,
                        "valid_rows": 240,
                    }
                },
                "rolling_backtest_metrics": {
                    "30": {
                        "overall": {"mae": 35.2, "rmse": 49.3},
                        "spike_errors": {"high": {"mae": 88.1}},
                    }
                },
                "price_model_training_config": {
                    "training_window_days": 45,
                    "valid_days": 5,
                    "start_date": "2026-04-01",
                    "end_date": "2026-05-19",
                },
                "price_interval_model": {
                    "enabled": True,
                    "selected_model_key": "interval_xgboost",
                    "selected_model_backend_label": "XGBoost",
                    "intervals": [{"label": "0-300"}, {"label": "300-1500"}],
                    "metrics": {"overall": {"interval_accuracy": 0.72, "top2_accuracy": 0.91, "high_price_recall": 0.66}},
                    "feature_columns": ["net_load", "thermal_on_capacity"],
                    "variant_metrics": {
                        "interval_xgboost": {
                            "segments": {
                                "morning_peak": {"train_rows": 100, "valid_rows": 20},
                                "evening_peak": {"train_rows": 120, "valid_rows": 24},
                            }
                        }
                    },
                },
                "interval_model_training_config": {
                    "training_window_days": 60,
                    "valid_days": 7,
                },
                "thermal_capacity_model": {
                    "enabled": True,
                    "selected_model_key": "thermal_capacity_ridge",
                    "selected_model_backend": "ridge",
                    "selected_model_backend_label": "Ridge",
                    "model_variants": {
                        "thermal_capacity_ridge": {"model_backend": "ridge", "model_backend_label": "Ridge"},
                        "thermal_capacity_xgboost": {"model_backend": "xgboost", "model_backend_label": "XGBoost"},
                    },
                    "feature_columns": ["net_load", "renewable_power", "previous_thermal_on_capacity"],
                    "metrics": {"overall": {"mae": 510.2, "rmse": 702.7, "max_error": 1400.0, "bias": -20.5}},
                    "train_rows": 55,
                    "valid_rows": 7,
                },
                "thermal_capacity_model_training_config": {
                    "training_window_days": 90,
                    "valid_days": 7,
                },
            }
            write_metadata(model_root / "current", metadata)
            write_metadata(model_root / "history" / "run_20260520_120000", metadata)

            rows = list_model_versions(model_root).to_dict("records")

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("version_summary", row)
        self.assertIn("version_detail", row)
        self.assertEqual(row["version_summary"]["price_model"]["backend_label"], "XGBoost")
        self.assertEqual(row["version_summary"]["price_model"]["mae"], 31.4)
        self.assertEqual(row["version_summary"]["price_interval_model"]["accuracy"], 0.72)
        self.assertEqual(row["version_summary"]["thermal_capacity_model"]["mae"], 510.2)
        self.assertEqual(row["version_summary"]["thermal_capacity_model"]["selected_model_backend_label"], "Ridge")
        self.assertEqual(row["version_summary"]["thermal_capacity_model"]["candidate_count"], 2)
        self.assertEqual(row["version_detail"]["training"]["price"]["training_window_days"], 45)
        self.assertEqual(row["version_detail"]["training"]["interval"]["training_window_days"], 60)
        self.assertEqual(row["version_detail"]["training"]["thermal_capacity"]["training_window_days"], 90)
        self.assertEqual(row["version_detail"]["price_interval_model"]["interval_count"], 2)
        self.assertEqual(row["version_detail"]["price_interval_model"]["selected_model_backend_label"], "XGBoost")
        self.assertEqual(row["version_detail"]["price_interval_model"]["train_rows"], 220)
        self.assertEqual(row["version_detail"]["price_interval_model"]["valid_rows"], 44)
        self.assertEqual(row["version_detail"]["price_interval_model"]["feature_count"], 2)
        self.assertEqual(row["version_detail"]["thermal_capacity_model"]["feature_count"], 3)
        self.assertEqual(row["version_detail"]["thermal_capacity_model"]["selected_model_key"], "thermal_capacity_ridge")
        self.assertEqual(len(row["version_detail"]["thermal_capacity_model"]["model_variants"]), 2)


if __name__ == "__main__":
    unittest.main()
