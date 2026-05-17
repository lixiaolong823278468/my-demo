from __future__ import annotations

import unittest


class WindowOptimizationSegmentSearchTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
