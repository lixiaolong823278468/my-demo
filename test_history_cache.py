from __future__ import annotations

import time
import unittest
from pathlib import Path

import pandas as pd


class HistoryCacheTests(unittest.TestCase):
    def test_train_config_can_disable_lag_96_feature_columns(self) -> None:
        from dayahead_core import TrainConfig, training_feature_columns

        self.assertIn("lag_96", training_feature_columns(TrainConfig()))
        self.assertNotIn("lag_96", training_feature_columns(TrainConfig(use_lag_96=False)))

    def test_no_lag_model_does_not_require_lag_96_prediction_input(self) -> None:
        from dayahead_core import ensure_prediction_lag_96

        forecast_df = pd.DataFrame({"date": pd.to_datetime(["2026-05-02"]), "period": [1]})
        history_df = pd.DataFrame({"date": pd.to_datetime(["2026-05-01"]), "period": [1], "日前出清价格(元/MWh)": [300.0]})

        result = ensure_prediction_lag_96(
            forecast_df,
            history_df,
            {"feature_columns": ["net_load", "similar_price"]},
        )

        self.assertNotIn("lag_96", result.columns)

    def test_lag_model_still_requires_lag_96_prediction_input(self) -> None:
        from dayahead_core import ensure_prediction_lag_96

        forecast_df = pd.DataFrame({"date": pd.to_datetime(["2026-05-03"]), "period": [1]})
        history_df = pd.DataFrame({"date": pd.to_datetime(["2026-05-01"]), "period": [1], "日前出清价格(元/MWh)": [300.0]})

        with self.assertRaises(ValueError):
            ensure_prediction_lag_96(
                forecast_df,
                history_df,
                {"feature_columns": ["net_load", "lag_96", "similar_price"]},
            )

    def test_no_lag_forecast_template_allows_missing_reference_price(self) -> None:
        from dayahead_core import try_load_forecast_template

        root = Path(__file__).resolve().parent / ".test_tmp"
        root.mkdir(exist_ok=True)
        forecast_file = root / f"no_lag_forecast_{time.time_ns()}.xlsx"
        frame = pd.DataFrame(
            {
                "序号": list(range(1, 97)),
                "5.1日剩余电力值": [80.0] * 96,
                "5.2日剩余电力值": [85.0] * 96,
                "火电开机容量": [36095.0] * 96,
            }
        )
        frame.to_excel(forecast_file, index=False)

        forecast_df, reference_df, issues = try_load_forecast_template(
            forecast_file,
            set(),
            2026,
            require_lag_96=False,
        )

        self.assertIsNotNone(forecast_df)
        self.assertIsNone(reference_df)
        self.assertNotIn("lag_96", forecast_df.columns)
        self.assertFalse(any(issue.field == "参考日前日价格" for issue in issues))

    def test_local_holiday_calendar_overrides_weekend_workday(self) -> None:
        from dayahead_core import day_type_of, load_holiday_calendar

        root = Path(__file__).resolve().parent / ".test_tmp"
        root.mkdir(exist_ok=True)
        calendar_file = root / f"holiday_calendar_{time.time_ns()}.csv"
        calendar_file.write_text(
            "date,type,name\n"
            "2026-02-15,workday,春节调休上班\n"
            "2026-02-16,holiday,春节\n",
            encoding="utf-8",
        )

        calendar = load_holiday_calendar(calendar_file)

        self.assertEqual(day_type_of(pd.Timestamp("2026-02-15"), calendar), "workday")
        self.assertEqual(day_type_of(pd.Timestamp("2026-02-16"), calendar), "holiday")
        self.assertEqual(day_type_of(pd.Timestamp("2026-02-14"), calendar), "weekend")

    def test_multicondition_similarity_uses_same_period_and_weighted_fields(self) -> None:
        from dayahead_core import SIMILAR_PRICE_COLUMN, TARGET_COLUMN, attach_multicondition_similarity_features

        target_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-04"]),
                "period": [1],
                "net_load": [100.0],
                "renewable_power": [50.0],
                "thermal_on_capacity": [1000.0],
                "day_type": ["workday"],
            }
        )
        reference_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"]),
                "period": [1, 1, 2],
                "net_load": [101.0, 130.0, 100.0],
                "renewable_power": [500.0, 50.0, 50.0],
                "thermal_on_capacity": [1000.0, 1000.0, 1000.0],
                "day_type": ["workday", "workday", "workday"],
                TARGET_COLUMN: [10.0, 200.0, 999.0],
            }
        )

        result = attach_multicondition_similarity_features(target_df, reference_df, k=1)

        self.assertEqual(float(result.loc[0, SIMILAR_PRICE_COLUMN]), 200.0)

    def test_multicondition_similarity_accepts_custom_weights(self) -> None:
        from dayahead_core import SIMILAR_PRICE_COLUMN, TARGET_COLUMN, attach_multicondition_similarity_features

        target_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-04"]),
                "period": [1],
                "net_load": [100.0],
                "renewable_power": [50.0],
                "thermal_on_capacity": [1000.0],
                "day_type": ["workday"],
            }
        )
        reference_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-01", "2026-05-02"]),
                "period": [1, 1],
                "net_load": [101.0, 130.0],
                "renewable_power": [500.0, 50.0],
                "thermal_on_capacity": [1000.0, 1000.0],
                "day_type": ["workday", "workday"],
                TARGET_COLUMN: [10.0, 200.0],
            }
        )

        result = attach_multicondition_similarity_features(
            target_df,
            reference_df,
            k=1,
            similarity_weights={
                "net_load": 1.0,
                "renewable_power": 0.0,
                "thermal_on_capacity": 0.0,
                "day_type": 0.0,
            },
        )

        self.assertEqual(float(result.loc[0, SIMILAR_PRICE_COLUMN]), 10.0)

    def test_multicondition_similarity_accepts_thermal_space_ratio_weight(self) -> None:
        from dayahead_core import SIMILAR_PRICE_COLUMN, TARGET_COLUMN, THERMAL_SPACE_LOAD_RATIO_COLUMN, attach_multicondition_similarity_features

        target_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-04"]),
                "period": [1],
                "net_load": [100.0],
                THERMAL_SPACE_LOAD_RATIO_COLUMN: [0.5],
                "renewable_power": [50.0],
                "thermal_on_capacity": [1000.0],
                "day_type": ["workday"],
            }
        )
        reference_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-01", "2026-05-02"]),
                "period": [1, 1],
                "net_load": [100.0, 100.0],
                THERMAL_SPACE_LOAD_RATIO_COLUMN: [0.9, 0.5],
                "renewable_power": [50.0, 50.0],
                "thermal_on_capacity": [1000.0, 1000.0],
                "day_type": ["workday", "workday"],
                TARGET_COLUMN: [10.0, 200.0],
            }
        )

        result = attach_multicondition_similarity_features(
            target_df,
            reference_df,
            k=1,
            similarity_weights={
                "thermal_space": 0.0,
                "renewable_power": 0.0,
                "thermal_on_capacity": 0.0,
                "day_type": 0.0,
                THERMAL_SPACE_LOAD_RATIO_COLUMN: 1.0,
            },
        )

        self.assertEqual(float(result.loc[0, SIMILAR_PRICE_COLUMN]), 200.0)

    def test_training_preferences_round_trip_similarity_weights(self) -> None:
        from dayahead_core import load_training_preferences, save_training_preferences

        root = Path(__file__).resolve().parent / ".test_tmp" / f"preferences_{time.time_ns()}"
        weights = {
            "thermal_space": 0.4,
            "renewable_power": 0.2,
            "thermal_on_capacity": 0.2,
            "day_type": 0.1,
            "thermal_space_load_ratio": 0.1,
        }

        saved = save_training_preferences(root, {"similarity_weights": weights})
        loaded = load_training_preferences(root)

        self.assertEqual(saved["similarity_weights"], weights)
        self.assertEqual(loaded["similarity_weights"], weights)

    def test_api_train_payload_parses_similarity_weights(self) -> None:
        from api_server import parse_similarity_weights_payload

        weights = parse_similarity_weights_payload(
            {
                "similarity_weights": {
                    "thermal_space": "0.5",
                    "renewable_power": 0.15,
                    "thermal_on_capacity": 0.15,
                    "day_type": 0.1,
                    "thermal_space_load_ratio": 0.1,
                }
            }
        )

        self.assertEqual(
            weights,
            {
                "thermal_space": 0.5,
                "renewable_power": 0.15,
                "thermal_on_capacity": 0.15,
                "day_type": 0.1,
                "thermal_space_load_ratio": 0.1,
            },
        )

    def test_forecast_similarity_keeps_net_load_only_reference_price(self) -> None:
        from dayahead_core import NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN, SIMILAR_PRICE_COLUMN, TARGET_COLUMN, attach_forecast_similarity_features

        target_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-04"]),
                "period": [1],
                "net_load": [100.0],
                "renewable_power": [50.0],
                "thermal_on_capacity": [1000.0],
                "day_type": ["workday"],
            }
        )
        reference_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-01", "2026-05-02"]),
                "period": [1, 1],
                "net_load": [101.0, 130.0],
                "renewable_power": [500.0, 50.0],
                "thermal_on_capacity": [1000.0, 1000.0],
                "day_type": ["workday", "workday"],
                TARGET_COLUMN: [10.0, 200.0],
            }
        )

        result = attach_forecast_similarity_features(target_df, reference_df)

        self.assertGreater(float(result.loc[0, SIMILAR_PRICE_COLUMN]), 100.0)
        self.assertLess(float(result.loc[0, NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN]), 50.0)

    def test_date_window_selects_only_overlapping_month_files(self) -> None:
        from dayahead_core import list_excel_files_for_date_window

        root = Path(__file__).resolve().parent / ".test_tmp"
        root.mkdir(exist_ok=True)
        marker = time.time_ns()
        selected_names = [
            f"{marker}_2025年12月.xlsx",
            f"{marker}_2026年1月.xlsx",
            f"{marker}_2026年4月.xlsx",
        ]
        excluded_names = [
            f"{marker}_2025年11月.xlsx",
            f"{marker}_2026年5月.xlsx",
        ]
        for name in [*selected_names, *excluded_names]:
            (root / name).write_bytes(b"x")

        files = list_excel_files_for_date_window(root, "2026-01-01", "2026-04-30", leading_days=1)
        result_names = {path.name for path in files if path.name.startswith(str(marker))}

        self.assertEqual(result_names, set(selected_names))

    def test_prediction_history_window_looks_back_enough_for_same_type_days(self) -> None:
        from dayahead_core import prediction_history_window

        start_date, end_date = prediction_history_window(pd.Timestamp("2026-05-02"), 4)

        self.assertEqual(start_date, "2026-03-31")
        self.assertEqual(end_date, "2026-05-01")

    def test_dataframe_cache_round_trip_and_signature_invalidation(self) -> None:
        from dayahead_core import (
            build_history_source_signature,
            load_dataframe_cache,
            save_dataframe_cache,
        )

        root = Path(__file__).resolve().parent / ".test_tmp"
        root.mkdir(exist_ok=True)
        source_file = root / f"history_cache_source_{time.time_ns()}.xlsx"
        source_file.write_bytes(b"first")

        cache_dir = root / "cache"
        cache_name = source_file.stem
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01"]),
                "period": [1],
                "net_load": [123.45],
            }
        )
        signature = build_history_source_signature(source_file, None, True)

        save_dataframe_cache(cache_dir, cache_name, signature["cache_key"], frame, ["skipped"])
        cached = load_dataframe_cache(cache_dir, cache_name, signature["cache_key"])

        self.assertIsNotNone(cached)
        cached_frame, skipped_sheets = cached
        pd.testing.assert_frame_equal(cached_frame, frame)
        self.assertEqual(skipped_sheets, ["skipped"])

        time.sleep(0.01)
        source_file.write_bytes(b"changed")
        changed_signature = build_history_source_signature(source_file, None, True)

        self.assertNotEqual(signature["cache_key"], changed_signature["cache_key"])
        self.assertIsNone(load_dataframe_cache(cache_dir, cache_name, changed_signature["cache_key"]))


if __name__ == "__main__":
    unittest.main()
