from __future__ import annotations

import unittest

import pandas as pd


class MultiFactorKnnSimilarityTests(unittest.TestCase):
    def test_multifactor_knn_filters_far_neighbors(self) -> None:
        from dayahead_core import TARGET_COLUMN, multi_factor_knn_similarity_price

        target = pd.DataFrame(
            {
                "net_load": [100.0],
                "total_load": [200.0],
                "renewable_power": [100.0],
                "thermal_on_capacity": [50.0],
                "thermal_space_load_ratio": [0.5],
                "period": [10],
                "day_type": ["weekday"],
            }
        )
        reference = pd.DataFrame(
            {
                "net_load": [101.0, 102.0, 500.0],
                "total_load": [201.0, 202.0, 900.0],
                "renewable_power": [100.0, 99.0, 10.0],
                "thermal_on_capacity": [51.0, 52.0, 300.0],
                "thermal_space_load_ratio": [0.5, 0.51, 0.95],
                "period": [10, 11, 80],
                "day_type": ["weekday", "weekday", "weekend"],
                TARGET_COLUMN: [300.0, 330.0, 1200.0],
            }
        )

        result = multi_factor_knn_similarity_price(target, reference, k=5)

        self.assertEqual(result["count"].tolist(), [2])
        self.assertAlmostEqual(result["plain_price"].iloc[0], 315.0, places=4)
        self.assertLess(result["weighted_price"].iloc[0], 330.0)

    def test_multifactor_knn_allows_separate_plain_and_weighted_config(self) -> None:
        from dayahead_core import TARGET_COLUMN, multi_factor_knn_similarity_price

        target = pd.DataFrame(
            {
                "net_load": [100.0],
                "total_load": [200.0],
                "renewable_power": [100.0],
                "thermal_on_capacity": [50.0],
                "thermal_space_load_ratio": [0.5],
                "period": [10],
                "day_type": ["weekday"],
            }
        )
        reference = pd.DataFrame(
            {
                "net_load": [100.5, 101.0],
                "total_load": [200.5, 201.0],
                "renewable_power": [100.0, 99.0],
                "thermal_on_capacity": [50.5, 51.0],
                "thermal_space_load_ratio": [0.505, 0.51],
                "period": [10, 11],
                "day_type": ["weekday", "weekday"],
                TARGET_COLUMN: [300.0, 360.0],
            }
        )

        result = multi_factor_knn_similarity_price(target, reference, k=1, weighted_k=2)

        self.assertEqual(result["count"].tolist(), [1])
        self.assertAlmostEqual(result["plain_price"].iloc[0], 300.0, places=4)
        self.assertGreater(float(result["weighted_price"].iloc[0]), 300.0)

    def test_forecast_similarity_features_include_knn_references(self) -> None:
        from dayahead_core import (
            KNN_SIMILAR_PRICE_COLUMN,
            TARGET_COLUMN,
            WEIGHTED_KNN_PRICE_COLUMN,
            attach_forecast_similarity_features,
        )

        forecast = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-18"]),
                "period": [1],
                "net_load": [100.0],
                "total_load": [200.0],
                "renewable_power": [100.0],
                "thermal_on_capacity": [50.0],
                "thermal_space_load_ratio": [0.5],
                "day_type": ["weekday"],
            }
        )
        reference = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-17", "2026-05-16"]),
                "period": [1, 2],
                "net_load": [101.0, 102.0],
                "total_load": [201.0, 202.0],
                "renewable_power": [100.0, 99.0],
                "thermal_on_capacity": [51.0, 52.0],
                "thermal_space_load_ratio": [0.5, 0.51],
                "day_type": ["weekday", "weekday"],
                TARGET_COLUMN: [300.0, 330.0],
            }
        )

        result = attach_forecast_similarity_features(forecast, reference)

        self.assertIn(KNN_SIMILAR_PRICE_COLUMN, result.columns)
        self.assertIn(WEIGHTED_KNN_PRICE_COLUMN, result.columns)
        self.assertAlmostEqual(float(result[KNN_SIMILAR_PRICE_COLUMN].iloc[0]), 315.0, places=4)


if __name__ == "__main__":
    unittest.main()
