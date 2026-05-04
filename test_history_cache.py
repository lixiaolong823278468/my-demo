from __future__ import annotations

import time
import unittest
from pathlib import Path

import pandas as pd


class HistoryCacheTests(unittest.TestCase):
    removed_previous_day_feature = "lag_" + "96"

    def test_training_feature_columns_do_not_include_previous_day_price(self) -> None:
        from dayahead_core import TrainConfig, training_feature_columns

        self.assertNotIn(self.removed_previous_day_feature, training_feature_columns(TrainConfig()))
        self.assertNotIn("similar_price", training_feature_columns(TrainConfig()))
        self.assertNotIn("similar_gap", training_feature_columns(TrainConfig()))

    def test_no_lag_model_metadata_defines_single_variant(self) -> None:
        from dayahead_core import direct_model_variants

        variants = direct_model_variants()

        self.assertEqual(list(variants), ["no_lag_96"])
        self.assertNotIn(self.removed_previous_day_feature, variants["no_lag_96"])
        self.assertNotIn("similar_price", variants["no_lag_96"])

    def test_prediction_variant_prefers_no_lag_and_skips_legacy_lag(self) -> None:
        from dayahead_core import select_prediction_model_variant

        metadata = {
            "model_variants": {
                "no_lag_96": {"feature_columns": ["net_load"]},
                "legacy_lag": {"feature_columns": ["net_load", self.removed_previous_day_feature]},
            }
        }

        forecast_df = pd.DataFrame({"net_load": [100.0], self.removed_previous_day_feature: [pd.NA]})

        self.assertEqual(select_prediction_model_variant(metadata, forecast_df), "no_lag_96")

        legacy_metadata = {
            "model_variants": {
                "legacy_lag": {"feature_columns": ["net_load", self.removed_previous_day_feature]},
                "legacy_direct": {"feature_columns": ["net_load"]},
            }
        }
        self.assertEqual(select_prediction_model_variant(legacy_metadata, forecast_df), "legacy_direct")

    def test_training_window_resolves_latest_train_and_validation_range(self) -> None:
        from dayahead_core import TrainConfig, resolve_training_date_range

        frame = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=30, freq="D")})

        start_date, end_date = resolve_training_date_range(frame, TrainConfig(training_window_days=10, valid_days=5))

        self.assertEqual(start_date, "2026-01-16")
        self.assertEqual(end_date, "2026-01-30")

    def test_forecast_template_allows_missing_reference_price(self) -> None:
        from dayahead_core import try_load_forecast_template

        root = Path(__file__).resolve().parent / ".test_tmp"
        root.mkdir(exist_ok=True)
        forecast_file = root / f"direct_price_forecast_{time.time_ns()}.xlsx"
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
        )

        self.assertIsNotNone(forecast_df)
        self.assertIsNone(reference_df)
        self.assertNotIn(self.removed_previous_day_feature, forecast_df.columns)
        self.assertFalse(any(issue.field == "参考日前日价格" for issue in issues))

    def test_template_reference_day_feeds_similarity_before_history(self) -> None:
        from dayahead_core import TARGET_COLUMN, build_reference_frame, try_load_forecast_template

        root = Path(__file__).resolve().parent / ".test_tmp"
        root.mkdir(exist_ok=True)
        forecast_file = root / f"template_reference_{time.time_ns()}.xlsx"
        periods = list(range(1, 97))
        frame = pd.DataFrame(
            {
                "序号": periods,
                "5.3日剩余电力值": [80.0] * 96,
                "5.3日日前出清价格(元/MWh)": [9000.0 + period for period in periods],
                "5.4日剩余电力值": [85.0] * 96,
                "火电开机容量": [36095.0] * 96,
            }
        )
        frame.to_excel(forecast_file, index=False)

        forecast_df, template_reference_df, _ = try_load_forecast_template(forecast_file, set(), 2026)

        self.assertIsNotNone(forecast_df)
        self.assertIsNotNone(template_reference_df)

        history_rows = []
        for date_text, price_base in [("2026-05-01", 1000.0), ("2026-05-02", 2000.0), ("2026-05-03", 3000.0)]:
            for period in periods:
                history_rows.append(
                    {
                        "date": pd.Timestamp(date_text),
                        "period": period,
                        "net_load": 70.0,
                        "thermal_on_capacity": 36095.0,
                        TARGET_COLUMN: price_base + period,
                    }
                )
        history_df = pd.DataFrame(history_rows)

        reference_df, reference_dates = build_reference_frame(
            history_df=history_df,
            forecast_df=forecast_df,
            template_reference_df=template_reference_df,
            reference_days=3,
            reference_strategy="recent_n_days",
            holiday_dates=set(),
        )

        self.assertEqual(reference_dates, ["2026-05-03", "2026-05-02", "2026-05-01"])
        template_period_one = reference_df[(reference_df["date"] == pd.Timestamp("2026-05-03")) & (reference_df["period"] == 1)]
        self.assertEqual(float(template_period_one[TARGET_COLUMN].iloc[0]), 9001.0)

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

    def test_multicondition_similarity_handles_multiple_target_rows(self) -> None:
        from dayahead_core import SIMILAR_PRICE_COLUMN, TARGET_COLUMN, attach_multicondition_similarity_features

        target_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-04", "2026-05-04"]),
                "period": [1, 2],
                "net_load": [100.0, 200.0],
                "renewable_power": [50.0, 80.0],
                "thermal_on_capacity": [1000.0, 1000.0],
                "day_type": ["workday", "workday"],
            }
        )
        reference_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-01", "2026-05-01"]),
                "period": [1, 2],
                "net_load": [101.0, 201.0],
                "renewable_power": [50.0, 80.0],
                "thermal_on_capacity": [1000.0, 1000.0],
                "day_type": ["workday", "workday"],
                TARGET_COLUMN: [10.0, 20.0],
            }
        )

        result = attach_multicondition_similarity_features(target_df, reference_df, k=1)

        self.assertEqual(result[SIMILAR_PRICE_COLUMN].tolist(), [10.0, 20.0])

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

    def test_api_prediction_payload_parses_similarity_weights(self) -> None:
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

    def test_build_training_frame_rebuilds_stale_feature_cache_missing_direct_columns(self) -> None:
        from dayahead_core import (
            TARGET_COLUMN,
            THERMAL_SPACE_LOAD_RATIO_COLUMN,
            TOTAL_LOAD_COLUMN,
            TrainConfig,
            build_training_frame,
            derived_cache_key,
            load_cached_history_collection,
            save_dataframe_cache,
        )

        root = Path(__file__).resolve().parent / ".test_tmp" / f"stale_feature_cache_{time.time_ns()}"
        history_dir = root / "history"
        model_root = root / "models"
        history_dir.mkdir(parents=True)
        model_root.mkdir(parents=True)
        periods = list(range(96))
        history_frame = pd.DataFrame(
            {
                "总加电力值(MW)": [1000.0 + period for period in periods],
                "电力值(MW)": [200.0 for _ in periods],
                "日前出清价格(元/MWh)": [300.0 + period * 0.1 for period in periods],
                "日前-出清概况": ["火电开机容量 500MW" for _ in periods],
            }
        )
        with pd.ExcelWriter(history_dir / "2025年1月.xlsx", engine="openpyxl") as writer:
            history_frame.to_excel(writer, sheet_name="2025-01-01", index=False)

        _, _, _, signature, _ = load_cached_history_collection(history_dir, None, True, model_root, leading_days=1)
        stale_feature_key = derived_cache_key(signature["cache_key"], "direct_price_training_features_v0")
        stale_features = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01"]),
                "period": [1],
                "hour": [0],
                "weekday": [2],
                "month": [1],
                "is_weekend": [0],
                "is_holiday": [0],
                "day_type": ["workday"],
                "net_load": [800.0],
                "thermal_on_capacity": [500.0],
                "segment": ["night"],
                TARGET_COLUMN: [300.0],
            }
        )
        save_dataframe_cache(model_root / "cache", "training_features", stale_feature_key, stale_features, [])

        rebuilt_frame, _, _ = build_training_frame(TrainConfig(history_dir=history_dir, model_root=model_root))

        self.assertIn(TOTAL_LOAD_COLUMN, rebuilt_frame.columns)
        self.assertIn(THERMAL_SPACE_LOAD_RATIO_COLUMN, rebuilt_frame.columns)
        self.assertEqual(len(rebuilt_frame), 96)


if __name__ == "__main__":
    unittest.main()
