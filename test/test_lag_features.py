from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class LagFeatureTests(unittest.TestCase):
    def test_attach_lag_features_uses_only_prior_same_period_prices(self) -> None:
        from dayahead_core import TARGET_COLUMN, attach_lag_features

        rows = []
        for day_index, date in enumerate(pd.date_range("2026-05-01", periods=8), start=1):
            for period in (1, 2):
                rows.append(
                    {
                        "date": date,
                        "period": period,
                        TARGET_COLUMN: day_index * 100 + period,
                        "net_load": day_index * 10 + period,
                    }
                )
        frame = pd.DataFrame(rows)

        result = attach_lag_features(frame)
        target = result[(result["date"] == pd.Timestamp("2026-05-08")) & (result["period"] == 1)].iloc[0]

        self.assertEqual(target["price_lag_1d"], 701)
        self.assertEqual(target["price_lag_2d"], 601)
        self.assertEqual(target["price_lag_3d"], 501)
        self.assertEqual(target["price_lag_7d"], 101)
        self.assertEqual(target["net_load_lag_1d"], 71)
        self.assertAlmostEqual(target["price_ma_3d"], (501 + 601 + 701) / 3)
        self.assertAlmostEqual(target["price_ma_7d"], (101 + 201 + 301 + 401 + 501 + 601 + 701) / 7)

        first_day = result[(result["date"] == pd.Timestamp("2026-05-01")) & (result["period"] == 1)].iloc[0]
        self.assertTrue(pd.isna(first_day["price_lag_1d"]))

    def test_attach_forecast_lag_features_uses_history_when_forecast_has_no_target(self) -> None:
        from dayahead_core import TARGET_COLUMN, attach_forecast_lag_features

        history = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-15", "2026-05-16", "2026-05-17"]),
                "period": [1, 1, 1],
                TARGET_COLUMN: [300.0, 330.0, 360.0],
                "net_load": [100.0, 110.0, 120.0],
            }
        )
        forecast = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-18"]),
                "period": [1],
                "net_load": [125.0],
            }
        )

        result = attach_forecast_lag_features(forecast, history)

        self.assertEqual(float(result["price_lag_1d"].iloc[0]), 360.0)
        self.assertEqual(float(result["price_lag_2d"].iloc[0]), 330.0)
        self.assertEqual(float(result["price_lag_3d"].iloc[0]), 300.0)
        self.assertAlmostEqual(float(result["price_ma_3d"].iloc[0]), 330.0)

    def test_attach_lag_features_does_not_expand_duplicate_date_period_rows(self) -> None:
        from dayahead_core import TARGET_COLUMN, attach_lag_features

        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-01", "2026-05-01", "2026-05-02"]),
                "period": [1, 1, 1],
                TARGET_COLUMN: [100.0, 120.0, 200.0],
                "net_load": [50.0, 70.0, 80.0],
            }
        )

        result = attach_lag_features(frame)

        self.assertEqual(len(result), len(frame))
        self.assertEqual(result.loc[2, "price_lag_1d"], 110.0)
        self.assertEqual(result.loc[2, "net_load_lag_1d"], 60.0)

    def test_direct_model_variants_include_lag_variant(self) -> None:
        from dayahead_core import LAG_FEATURE_COLUMNS, direct_model_variants

        variants = direct_model_variants()

        self.assertIn("no_lag_96", variants)
        self.assertIn("with_lag_96", variants)
        self.assertNotIn("with_lag_knn_96", variants)
        self.assertEqual(variants["with_lag_96"], LAG_FEATURE_COLUMNS)
        self.assertIn("price_lag_1d", variants["with_lag_96"])

    def test_required_training_feature_cache_columns_exclude_knn_reference_columns(self) -> None:
        from dayahead_core import KNN_FEATURE_COLUMNS, required_training_feature_cache_columns

        columns = required_training_feature_cache_columns()

        for column in KNN_FEATURE_COLUMNS:
            self.assertNotIn(column, columns)

    def test_knn_training_feature_builder_is_not_exposed(self) -> None:
        import dayahead_core

        self.assertFalse(hasattr(dayahead_core, "attach_knn_training_features"))

    def test_build_training_frame_loads_enough_leading_days_for_model_features(self) -> None:
        from dayahead_core import TARGET_COLUMN, TrainConfig, build_training_frame

        captured: dict[str, object] = {}

        def fake_load_collection(*args, **kwargs):
            captured["leading_days"] = kwargs.get("leading_days")
            frame = pd.DataFrame(
                {
                    "date": pd.to_datetime(["2026-05-01"]),
                    "period": [1],
                    "segment": ["night"],
                    "total_load": [1000.0],
                    "net_load": [800.0],
                    "renewable_power": [200.0],
                    "thermal_space_load_ratio": [0.8],
                    "thermal_on_capacity": [500.0],
                    "hour": [0],
                    "weekday": [4],
                    "month": [5],
                    "is_weekend": [0],
                    "is_holiday": [0],
                    TARGET_COLUMN: [300.0],
                }
            )
            return frame, [], set(), {"cache_key": "fake"}, []

        root = Path(__file__).resolve().parent / ".test_tmp" / "lag_leading_days"
        with patch("dayahead_core.load_cached_history_collection", side_effect=fake_load_collection):
            build_training_frame(
                TrainConfig(
                    history_dir=root / "history",
                    model_root=root / "models",
                    start_date="2026-05-01",
                    similarity_reference_days=30,
                )
            )

        self.assertEqual(captured["leading_days"], 30)


if __name__ == "__main__":
    unittest.main()
