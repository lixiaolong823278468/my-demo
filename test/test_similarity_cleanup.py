from __future__ import annotations

import unittest

import pandas as pd


class SimilarityCleanupTests(unittest.TestCase):
    def test_forecast_similarity_keeps_only_net_load_baseline(self) -> None:
        from dayahead_core import (
            NET_LOAD_ONLY_SIMILAR_GAP_COLUMN,
            NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN,
            TARGET_COLUMN,
            attach_forecast_similarity_features,
        )

        forecast_df = pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-05-12"), pd.Timestamp("2026-05-12")],
                "period": [1, 2],
                "net_load": [100.0, 200.0],
            }
        )
        reference_df = pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-05-11"), pd.Timestamp("2026-05-11")],
                "period": [1, 2],
                "net_load": [102.0, 198.0],
                TARGET_COLUMN: [300.0, 420.0],
            }
        )

        result = attach_forecast_similarity_features(forecast_df, reference_df)

        self.assertIn(NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN, result.columns)
        self.assertIn(NET_LOAD_ONLY_SIMILAR_GAP_COLUMN, result.columns)
        self.assertNotIn("similar_price", result.columns)
        self.assertNotIn("similar_gap", result.columns)
        self.assertEqual(len(result[NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN].dropna()), 2)


if __name__ == "__main__":
    unittest.main()
