from __future__ import annotations

import unittest
from pathlib import Path
from time import time_ns

import numpy as np
import pandas as pd


TEST_TMP_ROOT = Path(__file__).resolve().parent / ".test_tmp"


def workspace_tempdir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / f"price_interval_{time_ns()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class PriceIntervalCoreTests(unittest.TestCase):
    def test_default_intervals_label_prices(self) -> None:
        from price_interval import interval_label_for_price, normalize_price_intervals

        intervals = normalize_price_intervals(None)

        self.assertEqual(
            [item["label"] for item in intervals],
            ["0-250", "250-300", "300-400", "400-600", "600-1000", "1000-1500"],
        )
        self.assertEqual(interval_label_for_price(0.0, intervals), "0-250")
        self.assertEqual(interval_label_for_price(249.99, intervals), "0-250")
        self.assertEqual(interval_label_for_price(250.0, intervals), "250-300")
        self.assertEqual(interval_label_for_price(1000.0, intervals), "1000-1500")
        self.assertEqual(interval_label_for_price(1499.99, intervals), "1000-1500")

    def test_price_intervals_require_closed_zero_to_1500_range(self) -> None:
        from price_interval import normalize_price_intervals

        intervals = normalize_price_intervals(
            [
                {"label": "low", "min": 0, "max": 500},
                {"label": "high", "min": 500, "max": 1500},
            ]
        )

        self.assertEqual(intervals[0]["min"], 0.0)
        self.assertEqual(intervals[-1]["max"], 1500.0)

        with self.assertRaisesRegex(ValueError, "第一个价格区间下限必须为 0"):
            normalize_price_intervals(
                [
                    {"label": "low", "min": None, "max": 500},
                    {"label": "high", "min": 500, "max": 1500},
                ]
            )

        with self.assertRaisesRegex(ValueError, "最后一个价格区间上限必须为 1500"):
            normalize_price_intervals(
                [
                    {"label": "low", "min": 0, "max": 500},
                    {"label": "high", "min": 500, "max": None},
                ]
            )

    def test_interval_metrics_include_accuracy_top2_and_high_recall(self) -> None:
        from price_interval import compute_interval_metrics, normalize_price_intervals

        intervals = normalize_price_intervals(None)
        probabilities = np.zeros((3, len(intervals)))
        probabilities[0, 2] = 0.8
        probabilities[0, 3] = 0.2
        probabilities[1, 4] = 0.6
        probabilities[1, 5] = 0.4
        probabilities[2, 1] = 0.7
        probabilities[2, 3] = 0.3

        metrics = compute_interval_metrics(["300-400", "1000-1500", "300-400"], probabilities, intervals)

        self.assertAlmostEqual(metrics["interval_accuracy"], 1 / 3)
        self.assertAlmostEqual(metrics["top2_accuracy"], 2 / 3)
        self.assertIn("high_price_recall", metrics)
        self.assertIn("score", metrics)

    def test_train_interval_models_selects_backend_and_predicts_probabilities(self) -> None:
        from price_interval import (
            load_interval_model_bundle,
            normalize_price_intervals,
            predict_interval_probabilities,
            train_interval_models,
        )

        rows = []
        for day in range(1, 13):
            for period in [1, 2]:
                price = 180.0 if day <= 4 else 350.0 if day <= 8 else 1100.0
                rows.append(
                    {
                        "date": pd.Timestamp(f"2026-05-{day:02d}"),
                        "period": period,
                        "segment": "all",
                        "total_load": 100 + day,
                        "net_load": 80 + day,
                        "renewable_power": 20,
                        "thermal_space_load_ratio": 0.8,
                        "thermal_on_capacity": 30000,
                        "hour": period / 4,
                        "weekday": day % 7,
                        "month": 5,
                        "is_weekend": 0,
                        "is_holiday": 0,
                        "price": price,
                    }
                )
        frame = pd.DataFrame(rows)
        intervals = normalize_price_intervals(None)
        feature_columns = [
            "total_load",
            "net_load",
            "renewable_power",
            "thermal_space_load_ratio",
            "thermal_on_capacity",
            "hour",
            "period",
            "weekday",
            "month",
            "is_weekend",
            "is_holiday",
        ]

        temp_dir = workspace_tempdir()
        if True:
            metadata = train_interval_models(
                frame,
                target_column="price",
                feature_columns=feature_columns,
                segment_config=[{"name": "all", "start_period": 1, "end_period": 96}],
                output_dir=temp_dir,
                intervals=intervals,
                valid_days=2,
                num_boost_round=20,
            )
            bundle = load_interval_model_bundle(temp_dir, metadata)
            result = predict_interval_probabilities(frame.head(2), bundle)

        self.assertEqual(result.probabilities.shape[0], 2)
        self.assertEqual(len(result.labels), 2)
        self.assertTrue(metadata["selected_model_key"].startswith("interval_"))

    def test_training_preferences_persist_price_intervals(self) -> None:
        from dayahead_core import load_training_preferences, save_training_preferences

        root = workspace_tempdir()
        if True:
            prefs = save_training_preferences(
                root,
                {
                    "price_intervals": [
                        {"label": "cheap", "min": 0, "max": 300},
                        {"label": "expensive", "min": 300, "max": 1500},
                    ]
                },
            )

            self.assertEqual(prefs["price_intervals"][0]["label"], "0-300")
            self.assertEqual(load_training_preferences(root)["price_intervals"][1]["label"], "300-1500")


if __name__ == "__main__":
    unittest.main()
