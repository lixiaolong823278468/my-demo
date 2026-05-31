from __future__ import annotations

import unittest

import pandas as pd


class HighPriceAdjustmentTests(unittest.TestCase):
    def test_high_price_adjustment_adds_auxiliary_columns_without_replacing_prediction(self) -> None:
        from dayahead_core import (
            HIGH_PRICE_ADJUSTED_PRICE_COLUMN,
            HIGH_PRICE_ADJUSTMENT_COLUMN,
            apply_high_price_probability_adjustment,
        )

        frame = pd.DataFrame(
            {
                "predicted_price": [350.0, 350.0, 700.0],
                "high_price_probability": [0.4, 0.2, 0.8],
                "extreme_price_probability": [0.0, 0.0, 0.2],
            }
        )

        result = apply_high_price_probability_adjustment(frame)

        self.assertEqual(result["predicted_price"].tolist(), [350.0, 350.0, 700.0])
        self.assertEqual(result[HIGH_PRICE_ADJUSTMENT_COLUMN].round(4).tolist(), [100.0, 0.0, 0.0])
        self.assertEqual(result[HIGH_PRICE_ADJUSTED_PRICE_COLUMN].round(4).tolist(), [450.0, 350.0, 700.0])

    def test_extreme_probability_allows_larger_but_capped_adjustment(self) -> None:
        from dayahead_core import HIGH_PRICE_ADJUSTED_PRICE_COLUMN, apply_high_price_probability_adjustment

        frame = pd.DataFrame(
            {
                "predicted_price": [250.0],
                "high_price_probability": [0.9],
                "extreme_price_probability": [0.12],
            }
        )

        result = apply_high_price_probability_adjustment(frame)

        self.assertEqual(float(result[HIGH_PRICE_ADJUSTED_PRICE_COLUMN].iloc[0]), 430.0)

    def test_high_price_adjustment_comparison_reports_original_and_adjusted_metrics(self) -> None:
        from dayahead_core import (
            HIGH_PRICE_ADJUSTED_PRICE_COLUMN,
            apply_high_price_probability_adjustment,
            summarize_high_price_adjustment_effect,
        )

        frame = pd.DataFrame(
            {
                "actual": [650.0, 100.0],
                "predicted": [350.0, 120.0],
                "high_price_probability": [0.4, 0.7],
                "extreme_price_probability": [0.0, 0.0],
            }
        )
        adjusted = apply_high_price_probability_adjustment(frame, price_column="predicted")

        comparison = summarize_high_price_adjustment_effect(
            adjusted,
            original_column="predicted",
            adjusted_column=HIGH_PRICE_ADJUSTED_PRICE_COLUMN,
            high_threshold=600.0,
        )

        self.assertEqual(comparison["overall"]["original"]["mae"], 160.0)
        self.assertEqual(comparison["overall"]["adjusted"]["mae"], 110.0)
        self.assertEqual(comparison["high_price"]["original"]["mae"], 300.0)
        self.assertEqual(comparison["high_price"]["adjusted"]["mae"], 200.0)

    def test_selected_validation_predictions_get_interval_probabilities_before_comparison(self) -> None:
        from dayahead_core import build_selected_validation_adjustment_frame

        validation_records = [
            {"model_key": "model_a", "segment": "s1", "date": "2026-05-01", "period": 1, "actual": 650.0, "predicted": 350.0},
            {"model_key": "model_b", "segment": "s1", "date": "2026-05-01", "period": 1, "actual": 650.0, "predicted": 500.0},
            {"model_key": "model_c", "segment": "s2", "date": "2026-05-01", "period": 2, "actual": 100.0, "predicted": 110.0},
        ]
        interval_features = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-01", "2026-05-01"]),
                "period": [1, 2],
                "segment": ["s1", "s2"],
                "high_price_probability": [0.4, 0.0],
                "extreme_price_probability": [0.0, 0.0],
                "predicted_interval": ["400-600", "0-250"],
            }
        )

        result = build_selected_validation_adjustment_frame(
            validation_records,
            {"s1": "model_a", "s2": "model_c"},
            interval_features,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result["model_key"].tolist(), ["model_a", "model_c"])
        self.assertEqual(float(result["high_price_adjustment"].iloc[0]), 100.0)
        self.assertEqual(float(result["high_price_adjusted_price"].iloc[0]), 450.0)

    def test_similarity_reference_adds_downward_reference_without_replacing_prediction(self) -> None:
        from dayahead_core import (
            SCENARIO_SIMILARITY_ADJUSTED_PRICE_COLUMN,
            SIMILARITY_ADJUSTMENT_REASON_COLUMN,
            SIMILARITY_BLEND_WEIGHT_COLUMN,
            apply_scenario_similarity_reference_adjustment,
        )

        frame = pd.DataFrame(
            {
                "date": ["2026-05-17", "2026-05-17", "2026-05-17"],
                "segment": ["segment_3", "segment_3", "segment_2"],
                "predicted_price": [500.0, 360.0, 420.0],
                "total_load": [1000.0, 1000.0, 1000.0],
                "renewable_power": [300.0, 100.0, 120.0],
                "net_load": [700.0, 900.0, 880.0],
                "net_load_only_similar_price": [320.0, 330.0, 410.0],
            }
        )

        result = apply_scenario_similarity_reference_adjustment(frame)

        self.assertEqual(result["predicted_price"].tolist(), [500.0, 360.0, 420.0])
        self.assertLess(float(result[SCENARIO_SIMILARITY_ADJUSTED_PRICE_COLUMN].iloc[0]), 500.0)
        self.assertGreater(float(result[SCENARIO_SIMILARITY_ADJUSTED_PRICE_COLUMN].iloc[0]), 320.0)
        self.assertGreater(float(result[SIMILARITY_BLEND_WEIGHT_COLUMN].iloc[0]), 0.0)
        self.assertEqual(result[SIMILARITY_ADJUSTMENT_REASON_COLUMN].iloc[0], "renewable_high_net_load_low_model_above_similarity")
        self.assertAlmostEqual(float(result[SCENARIO_SIMILARITY_ADJUSTED_PRICE_COLUMN].iloc[1]), 360.0)
        self.assertEqual(float(result[SIMILARITY_BLEND_WEIGHT_COLUMN].iloc[1]), 0.0)

    def test_similarity_reference_does_not_adjust_high_risk_or_evening_peak(self) -> None:
        from dayahead_core import (
            SCENARIO_SIMILARITY_ADJUSTED_PRICE_COLUMN,
            SIMILARITY_BLEND_WEIGHT_COLUMN,
            apply_scenario_similarity_reference_adjustment,
        )

        frame = pd.DataFrame(
            {
                "date": ["2026-05-18", "2026-05-18"],
                "segment": ["segment_3", "segment_5"],
                "predicted_price": [500.0, 520.0],
                "total_load": [1000.0, 1000.0],
                "renewable_power": [350.0, 330.0],
                "net_load": [650.0, 670.0],
                "net_load_only_similar_price": [300.0, 310.0],
                "high_price_probability": [0.45, 0.0],
                "extreme_price_probability": [0.0, 0.0],
            }
        )

        result = apply_scenario_similarity_reference_adjustment(frame)

        self.assertEqual(result[SCENARIO_SIMILARITY_ADJUSTED_PRICE_COLUMN].tolist(), [500.0, 520.0])
        self.assertEqual(result[SIMILARITY_BLEND_WEIGHT_COLUMN].tolist(), [0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
