from __future__ import annotations

import unittest


class WindowOptimizationSegmentSearchTests(unittest.TestCase):
    def test_backend_default_segment_config_uses_six_segments(self) -> None:
        from dayahead_core import DEFAULT_SEGMENT_CONFIG

        self.assertEqual(len(DEFAULT_SEGMENT_CONFIG), 6)
        self.assertEqual(DEFAULT_SEGMENT_CONFIG[0]["start_time"], "00:00")
        self.assertEqual(DEFAULT_SEGMENT_CONFIG[-1]["end_time"], "24:00")

    def test_even_segment_config_covers_full_day(self) -> None:
        from api_server import build_even_segment_config

        rows = build_even_segment_config(3)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["start_time"], "00:00")
        self.assertEqual(rows[-1]["end_time"], "24:00")
        self.assertEqual(rows[0]["end_time"], rows[1]["start_time"])

    def test_segment_search_configs_use_selected_counts_only(self) -> None:
        from api_server import normalize_segment_search_configs

        payload = {
            "segment_search_enabled": True,
            "segment_search_counts": [3, 6],
            "segment_search_configs": [
                {"segment_count": 3},
                {"segment_count": 6},
                {"segment_count": 8},
            ],
        }

        configs = normalize_segment_search_configs(payload, None)

        self.assertEqual([item["segment_count"] for item in configs], [3, 6])
        self.assertTrue(all(len(item["segment_config"]) == item["segment_count"] for item in configs))

    def test_segment_search_defaults_to_six_segments(self) -> None:
        from api_server import normalize_segment_search_configs

        configs = normalize_segment_search_configs({"segment_search_enabled": True}, None)

        self.assertEqual([item["segment_count"] for item in configs], [6])
        self.assertEqual(len(configs[0]["segment_config"]), 6)

    def test_segment_search_disabled_uses_current_config(self) -> None:
        from api_server import normalize_segment_search_configs

        current_config = [
            {"name": "a", "start_time": "00:00", "end_time": "12:00"},
            {"name": "b", "start_time": "12:00", "end_time": "24:00"},
        ]

        configs = normalize_segment_search_configs({"segment_search_enabled": False}, current_config)

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0]["segment_count"], 2)
        self.assertEqual(configs[0]["segment_config"], current_config)

    def test_rolling_backtest_horizons_are_configurable(self) -> None:
        from api_server import parse_rolling_backtest_horizons

        self.assertEqual(parse_rolling_backtest_horizons({"rolling_backtest_horizons": "7,14,30"}), (7, 14, 30))
        self.assertEqual(parse_rolling_backtest_horizons({"rolling_backtest_horizons": [14, "30"]}), (14, 30))
        self.assertEqual(parse_rolling_backtest_horizons({}), (14,))

    def test_window_optimization_defaults_prefer_saved_state(self) -> None:
        from api_server import window_optimization_config_defaults

        defaults = window_optimization_config_defaults(
            {
                "valid_days": 8,
                "rolling_backtest_horizons": [7, 14],
            }
        )

        self.assertEqual(defaults["valid_days"], 8)
        self.assertEqual(defaults["rolling_backtest_horizons"], [7, 14])

    def test_business_score_uses_configured_rolling_horizon(self) -> None:
        from api_server import business_window_score

        _score, detail = business_window_score(
            {"mae": 100, "rmse": 0},
            {
                "10": {
                    "overall": {"mae": 10, "rmse": 0},
                    "spike_errors": {"high": {"mae": 20, "rmse": 0}},
                }
            },
        )

        part_names = [item["name"] for item in detail["parts"]]
        self.assertIn("rolling_10_days", part_names)
        self.assertIn("high_price_spike", part_names)

    def test_rolling_backtest_cache_key_includes_target_and_horizon(self) -> None:
        from dayahead_core import rolling_backtest_cache_key

        day = rolling_backtest_cache_key("dayahead", "run_a", 30, {"window": 100})
        realtime = rolling_backtest_cache_key("realtime", "run_a", 30, {"window": 100})
        fourteen = rolling_backtest_cache_key("dayahead", "run_a", 14, {"window": 100})

        self.assertNotEqual(day, realtime)
        self.assertNotEqual(day, fourteen)

    def test_rolling_backtest_uses_cached_horizon_result(self) -> None:
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory

        import pandas as pd

        from dayahead_core import rolling_backtest_cache_key, rolling_backtest_cache_path, rolling_backtest_selected_model

        config_payload = {"window": 100}
        cached_metrics = {"rows": 96, "overall": {"mae": 12.5}}
        with TemporaryDirectory() as temp_dir:
            cache_key = rolling_backtest_cache_key("realtime", "run_a", 14, config_payload)
            cache_path = rolling_backtest_cache_path(temp_dir, cache_key)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cached_metrics), encoding="utf-8")

            result = rolling_backtest_selected_model(
                pd.DataFrame({"date": pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"])}),
                [],
                "xgboost",
                100,
                10,
                horizons=(14,),
                cache_root=Path(temp_dir),
                cache_target="realtime",
                cache_run_id="run_a",
                cache_config_payload=config_payload,
            )

        self.assertEqual(result, {"14": cached_metrics})

    def test_rerank_candidates_take_top_three_and_expand_close_scores(self) -> None:
        from api_server import select_window_rerank_candidates

        rows = [
            {"window_days": 30, "score": 10.0, "metrics": {"mae": 10.0}},
            {"window_days": 45, "score": 11.0, "metrics": {"mae": 11.0}},
            {"window_days": 60, "score": 12.0, "metrics": {"mae": 12.0}},
            {"window_days": 75, "score": 12.3, "metrics": {"mae": 12.3}},
            {"window_days": 90, "score": 12.4, "metrics": {"mae": 12.4}},
            {"window_days": 120, "score": 20.0, "metrics": {"mae": 20.0}},
        ]

        candidates = select_window_rerank_candidates(rows, top_n=3, max_n=5, tie_tolerance=0.5)

        self.assertEqual([item["window_days"] for item in candidates], [30, 45, 60, 75, 90])

    def test_price_lightweight_window_training_config_limits_variants_and_skips_interval(self) -> None:
        from api_server import build_window_train_config

        config = build_window_train_config(
            window_days=90,
            model_root="tmp",
            valid_days=7,
            num_boost_round=100,
            interval_valid_days=7,
            interval_num_boost_round=100,
            rolling_backtest_horizons=(10,),
            segment_config=None,
            high_price_weighting={"enabled": False, "quantile": 0.8, "multiplier": 2.0},
            price_intervals=[],
            enable_rolling_backtest=False,
            search_target="price",
        )

        self.assertEqual(config.direct_feature_variant_keys, ("no_lag_96",))
        self.assertEqual(config.model_backend_keys, ("xgboost",))
        self.assertFalse(config.train_interval_model)

    def test_window_training_config_accepts_shared_feature_cache_root(self) -> None:
        from pathlib import Path

        from api_server import build_window_train_config

        shared_cache_root = Path("tmp") / "shared_feature_cache"

        config = build_window_train_config(
            window_days=90,
            model_root=Path("tmp") / "candidate_model",
            feature_cache_root=shared_cache_root,
            valid_days=7,
            num_boost_round=100,
            interval_valid_days=7,
            interval_num_boost_round=100,
            rolling_backtest_horizons=(10,),
            segment_config=None,
            high_price_weighting={"enabled": False, "quantile": 0.8, "multiplier": 2.0},
            price_intervals=[],
            enable_rolling_backtest=False,
            search_target="price",
        )

        self.assertEqual(config.model_root, Path("tmp") / "candidate_model")
        self.assertEqual(config.feature_cache_root, shared_cache_root)

    def test_interval_lightweight_window_training_config_keeps_interval_independent(self) -> None:
        from api_server import build_window_train_config

        config = build_window_train_config(
            window_days=90,
            model_root="tmp",
            valid_days=7,
            num_boost_round=100,
            interval_valid_days=7,
            interval_num_boost_round=100,
            rolling_backtest_horizons=(10,),
            segment_config=None,
            high_price_weighting={"enabled": False, "quantile": 0.8, "multiplier": 2.0},
            price_intervals=[],
            enable_rolling_backtest=False,
            search_target="interval",
        )

        self.assertEqual(config.direct_feature_variant_keys, ("no_lag_96",))
        self.assertEqual(config.model_backend_keys, ("xgboost",))
        self.assertTrue(config.train_interval_model)
        self.assertEqual(config.interval_backend_keys, ("xgboost",))

    def test_realtime_full_window_training_config_trains_price_and_interval_only(self) -> None:
        from api_server import build_window_train_config
        from dayahead_core import REALTIME_DATA_MODE

        config = build_window_train_config(
            window_days=90,
            model_root="tmp",
            valid_days=7,
            num_boost_round=100,
            interval_valid_days=7,
            interval_num_boost_round=100,
            rolling_backtest_horizons=(10,),
            segment_config=None,
            high_price_weighting={"enabled": False, "quantile": 0.8, "multiplier": 2.0},
            price_intervals=[],
            enable_rolling_backtest=True,
            search_target="full",
            data_mode=REALTIME_DATA_MODE,
            include_thermal_capacity=False,
        )

        self.assertEqual(config.data_mode, REALTIME_DATA_MODE)
        self.assertTrue(config.train_interval_model)
        self.assertFalse(config.train_thermal_capacity_model)

    def test_thermal_capacity_lightweight_window_training_config_skips_price_and_interval(self) -> None:
        from api_server import build_window_train_config

        config = build_window_train_config(
            window_days=45,
            model_root="tmp",
            valid_days=7,
            num_boost_round=100,
            interval_valid_days=7,
            interval_num_boost_round=100,
            rolling_backtest_horizons=(10,),
            segment_config=None,
            high_price_weighting={"enabled": False, "quantile": 0.8, "multiplier": 2.0},
            price_intervals=[],
            enable_rolling_backtest=False,
            search_target="thermal_capacity",
        )

        self.assertFalse(config.train_interval_model)
        self.assertTrue(config.train_thermal_capacity_model)
        self.assertEqual(config.thermal_capacity_training_window_days, 45)
        self.assertEqual(config.direct_feature_variant_keys, ("no_lag_96",))
        self.assertEqual(config.model_backend_keys, ("xgboost",))
        self.assertEqual(config.thermal_capacity_backend_keys, ("xgboost", "ridge"))

    def test_thermal_capacity_window_result_sort_key_uses_capacity_score(self) -> None:
        from api_server import thermal_capacity_window_result_sort_key

        best = {"thermal_capacity_score": 1.0, "window_days": 90}
        worse = {"thermal_capacity_score": 2.0, "window_days": 30}

        self.assertLess(thermal_capacity_window_result_sort_key(best), thermal_capacity_window_result_sort_key(worse))

    def test_combined_rerank_windows_keep_price_and_interval_lines_separate(self) -> None:
        from api_server import combine_rerank_window_days

        price_rows = [
            {"window_days": 30, "score": 1.0, "metrics": {"mae": 1.0}},
            {"window_days": 45, "score": 2.0, "metrics": {"mae": 2.0}},
            {"window_days": 60, "score": 3.0, "metrics": {"mae": 3.0}},
        ]
        interval_rows = [
            {"window_days": 75, "interval_score": 1.0},
            {"window_days": 90, "interval_score": 2.0},
            {"window_days": 45, "interval_score": 3.0},
        ]

        self.assertEqual(combine_rerank_window_days(price_rows, interval_rows), [30, 45, 60, 75, 90])


if __name__ == "__main__":
    unittest.main()
