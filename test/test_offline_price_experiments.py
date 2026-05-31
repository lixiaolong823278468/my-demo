from __future__ import annotations

import unittest

import pandas as pd


class OfflinePriceExperimentTests(unittest.TestCase):
    def test_error_metrics_report_bias_and_tail_error(self) -> None:
        from offline_price_experiments import compute_error_metrics

        frame = pd.DataFrame({"actual": [100.0, 200.0, 400.0], "predicted": [90.0, 240.0, 300.0]})

        metrics = compute_error_metrics(frame)

        self.assertEqual(metrics["rows"], 3)
        self.assertAlmostEqual(metrics["mae"], 50.0)
        self.assertAlmostEqual(metrics["bias"], -70.0 / 3.0)
        self.assertAlmostEqual(metrics["over_rate"], 100.0 / 3.0)
        self.assertAlmostEqual(metrics["under_rate"], 200.0 / 3.0)

    def test_segment_interval_residual_correction_uses_specific_offset_then_segment_fallback(self) -> None:
        from offline_price_experiments import apply_residual_correction, learn_residual_corrections

        validation = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_5", "segment_5", "segment_6"],
                "actual": [600.0, 620.0, 240.0, 330.0],
                "predicted": [450.0, 500.0, 210.0, 310.0],
            }
        )
        forecast = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_5", "segment_6"],
                "predicted": [480.0, 280.0, 300.0],
            }
        )

        corrections = learn_residual_corrections(validation)
        corrected = apply_residual_correction(forecast, corrections)

        # segment_5 + 400-600 learned offset is mean([150, 120]) = 135.
        self.assertAlmostEqual(float(corrected.iloc[0]), 615.0)
        # No segment_5 + 250-300 pair exists; fall back to segment_5 mean residual.
        self.assertAlmostEqual(float(corrected.iloc[1]), 380.0)
        # segment_6 + 300-400 learned offset is 20.
        self.assertAlmostEqual(float(corrected.iloc[2]), 320.0)

    def test_late_peak_high_uplift_only_changes_triggered_segment(self) -> None:
        from offline_price_experiments import apply_late_peak_high_uplift, learn_residual_corrections

        validation = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_5", "segment_1"],
                "actual": [1000.0, 900.0, 650.0],
                "predicted": [600.0, 500.0, 350.0],
            }
        )
        forecast = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_5", "segment_1"],
                "predicted": [420.0, 390.0, 430.0],
            }
        )

        corrections = learn_residual_corrections(validation)
        corrected = apply_late_peak_high_uplift(forecast, corrections, multiplier=0.5)

        # high600 residual mean is 366.666..., half uplift applies only to segment_5 with predicted >= 400.
        self.assertAlmostEqual(float(corrected.iloc[0]), 603.3333333333334)
        self.assertAlmostEqual(float(corrected.iloc[1]), 390.0)
        self.assertAlmostEqual(float(corrected.iloc[2]), 430.0)

    def test_strategy_comparison_includes_high_price_subset_metrics(self) -> None:
        from offline_price_experiments import compare_strategies

        validation = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_5", "segment_6"],
                "actual": [1000.0, 900.0, 320.0],
                "predicted": [600.0, 500.0, 300.0],
            }
        )
        test = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_5", "segment_6"],
                "actual": [1000.0, 600.0, 310.0],
                "predicted": [600.0, 420.0, 300.0],
            }
        )

        comparison = compare_strategies(test, validation)

        self.assertIn("baseline", set(comparison["strategy"]))
        self.assertIn("segment_interval_bias", set(comparison["strategy"]))
        self.assertIn("late_peak_high_uplift", set(comparison["strategy"]))
        self.assertIn("segment_interval_plus_late_peak_uplift", set(comparison["strategy"]))
        self.assertIn("high600_mae", comparison.columns)

    def test_strategy_comparison_includes_similarity_candidates(self) -> None:
        from offline_price_experiments import compare_strategies

        validation = pd.DataFrame(
            {
                "segment": ["segment_2", "segment_5", "segment_3"],
                "actual": [520.0, 620.0, 240.0],
                "predicted": [430.0, 500.0, 310.0],
            }
        )
        test = pd.DataFrame(
            {
                "segment": ["segment_2", "segment_5", "segment_3"],
                "actual": [500.0, 610.0, 260.0],
                "predicted": [420.0, 520.0, 330.0],
                "total_load": [1000.0, 1000.0, 1000.0],
                "renewable_power": [120.0, 180.0, 420.0],
                "net_load": [880.0, 820.0, 580.0],
                "net_load_only_similar_price": [500.0, 590.0, 255.0],
            }
        )

        comparison = compare_strategies(test, validation)
        strategies = set(comparison["strategy"])

        self.assertIn("net_load_similarity", strategies)
        self.assertIn("fixed_similarity_blend_50", strategies)
        self.assertIn("scenario_similarity_blend", strategies)

    def test_scenario_similarity_blend_moves_high_renewable_overprediction_toward_similarity(self) -> None:
        from offline_price_experiments import apply_scenario_similarity_blend

        frame = pd.DataFrame(
            {
                "segment": ["segment_3", "segment_5"],
                "predicted": [420.0, 500.0],
                "total_load": [1000.0, 1000.0],
                "renewable_power": [450.0, 100.0],
                "net_load": [550.0, 900.0],
                "net_load_only_similar_price": [280.0, 650.0],
            }
        )

        blended = apply_scenario_similarity_blend(frame)

        self.assertLess(float(blended.iloc[0]), 420.0)
        self.assertGreater(float(blended.iloc[0]), 280.0)
        self.assertAlmostEqual(float(blended.iloc[1]), 500.0)

    def test_scenario_similarity_blend_uses_per_date_thresholds_when_available(self) -> None:
        from offline_price_experiments import apply_scenario_similarity_blend

        frame = pd.DataFrame(
            {
                "forecast_date": ["2026-05-17", "2026-05-17", "2026-05-18", "2026-05-18"],
                "segment": ["segment_3", "segment_3", "segment_3", "segment_3"],
                "predicted": [500.0, 360.0, 480.0, 470.0],
                "total_load": [1000.0, 1000.0, 1000.0, 1000.0],
                "renewable_power": [260.0, 100.0, 700.0, 650.0],
                "net_load": [740.0, 900.0, 300.0, 350.0],
                "net_load_only_similar_price": [320.0, 330.0, 300.0, 310.0],
            }
        )

        blended = apply_scenario_similarity_blend(frame)

        self.assertLess(float(blended.iloc[0]), 500.0)
        self.assertAlmostEqual(float(blended.iloc[1]), 360.0)

    def test_available_backtest_dates_are_intersection_of_archives_and_actuals(self) -> None:
        from pathlib import Path

        from offline_price_experiments import available_backtest_dates

        actuals = {
            "2026-05-16": pd.Series([300.0]),
            "2026-05-18": pd.Series([320.0]),
            "2026-05-19": pd.Series([280.0]),
        }
        archives = {
            "2026-05-15": Path("missing_actual.json"),
            "2026-05-18": Path("matched_18.json"),
            "2026-05-19": Path("matched_19.json"),
        }

        self.assertEqual(available_backtest_dates(actuals, archives), ["2026-05-18", "2026-05-19"])

    def test_focus_subset_report_includes_renewable_and_peak_scenarios(self) -> None:
        from offline_price_experiments import build_focus_subset_report, build_strategy_predictions

        validation = pd.DataFrame(
            {
                "segment": ["segment_3", "segment_5", "segment_1"],
                "actual": [300.0, 900.0, 500.0],
                "predicted": [420.0, 550.0, 360.0],
            }
        )
        test = pd.DataFrame(
            {
                "segment": ["segment_3", "segment_3", "segment_5"],
                "actual": [300.0, 310.0, 900.0],
                "predicted": [500.0, 470.0, 520.0],
                "total_load": [1000.0, 1000.0, 1000.0],
                "renewable_power": [300.0, 280.0, 100.0],
                "net_load": [700.0, 720.0, 900.0],
                "net_load_only_similar_price": [310.0, 320.0, 430.0],
            }
        )
        predictions = build_strategy_predictions(test, validation)

        report = build_focus_subset_report(test, predictions)

        self.assertIn("renewable_high_gap50_low_netload", set(report["scenario"]))
        self.assertIn("segment_3_midday", set(report["scenario"]))
        self.assertIn("segment_5_evening_high_risk", set(report["scenario"]))
        self.assertIn("baseline", set(report["strategy"]))
        self.assertIn("scenario_similarity_blend", set(report["strategy"]))

    def test_detailed_report_includes_overall_date_segment_and_high_threshold_sections(self) -> None:
        from offline_price_experiments import build_detailed_report

        validation = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_5", "segment_6"],
                "actual": [1000.0, 900.0, 320.0],
                "predicted": [600.0, 500.0, 300.0],
            }
        )
        test = pd.DataFrame(
            {
                "forecast_date": ["2026-05-18", "2026-05-18", "2026-05-18"],
                "segment": ["segment_5", "segment_5", "segment_6"],
                "actual": [1000.0, 600.0, 310.0],
                "predicted": [600.0, 420.0, 300.0],
            }
        )

        report = build_detailed_report(test, validation, thresholds=(400, 600))

        self.assertEqual(set(report), {"overall", "by_date", "by_segment", "by_high_threshold"})
        self.assertIn("strategy", report["overall"].columns)
        self.assertIn("forecast_date", report["by_date"].columns)
        self.assertIn("segment", report["by_segment"].columns)
        self.assertIn("threshold", report["by_high_threshold"].columns)
        self.assertIn("recall_rate", report["by_high_threshold"].columns)
        self.assertIn("under_rate", report["by_high_threshold"].columns)

    def test_high_price_classifier_switches_to_high_price_regressor_when_triggered(self) -> None:
        from offline_price_experiments import predict_high_classifier_regressor

        validation = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_5", "segment_1", "segment_1", "segment_6", "segment_6"],
                "period": [76, 80, 1, 2, 90, 92],
                "actual": [900.0, 1000.0, 280.0, 300.0, 320.0, 330.0],
                "predicted": [520.0, 580.0, 270.0, 290.0, 310.0, 315.0],
            }
        )
        forecast = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_1"],
                "period": [82, 3],
                "predicted": [560.0, 285.0],
            }
        )

        result = predict_high_classifier_regressor(validation, forecast, high_threshold=600.0, activation_probability=0.3)

        self.assertIn("prediction", result)
        self.assertIn("probability", result)
        self.assertGreater(float(result["probability"].iloc[0]), float(result["probability"].iloc[1]))
        self.assertGreater(float(result["prediction"].iloc[0]), 600.0)
        self.assertAlmostEqual(float(result["prediction"].iloc[1]), 285.0)

    def test_quantile_predictions_return_p50_p90_p95_columns(self) -> None:
        from offline_price_experiments import predict_quantiles

        validation = pd.DataFrame(
            {
                "segment": ["segment_1", "segment_1", "segment_5", "segment_5", "segment_6", "segment_6"],
                "period": [1, 2, 76, 80, 90, 92],
                "actual": [260.0, 280.0, 900.0, 1000.0, 320.0, 330.0],
                "predicted": [250.0, 270.0, 520.0, 580.0, 310.0, 315.0],
            }
        )
        forecast = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_1"],
                "period": [82, 3],
                "predicted": [560.0, 285.0],
            }
        )

        quantiles = predict_quantiles(validation, forecast)

        self.assertEqual(list(quantiles.columns), ["quantile_p50", "quantile_p90", "quantile_p95"])
        self.assertTrue((quantiles["quantile_p90"] >= quantiles["quantile_p50"]).all())
        self.assertTrue((quantiles["quantile_p95"] >= quantiles["quantile_p90"]).all())

    def test_detailed_report_includes_model_candidate_strategies(self) -> None:
        from offline_price_experiments import build_detailed_report

        validation = pd.DataFrame(
            {
                "segment": ["segment_5", "segment_5", "segment_1", "segment_1", "segment_6", "segment_6"],
                "period": [76, 80, 1, 2, 90, 92],
                "actual": [900.0, 1000.0, 280.0, 300.0, 320.0, 330.0],
                "predicted": [520.0, 580.0, 270.0, 290.0, 310.0, 315.0],
            }
        )
        test = pd.DataFrame(
            {
                "forecast_date": ["2026-05-18", "2026-05-18"],
                "segment": ["segment_5", "segment_1"],
                "period": [82, 3],
                "actual": [1000.0, 300.0],
                "predicted": [560.0, 285.0],
            }
        )

        report = build_detailed_report(test, validation)
        strategies = set(report["overall"]["strategy"])

        self.assertIn("high_classifier_regressor", strategies)
        self.assertIn("quantile_p50", strategies)
        self.assertIn("quantile_p90", strategies)
        self.assertIn("quantile_p95", strategies)


if __name__ == "__main__":
    unittest.main()
