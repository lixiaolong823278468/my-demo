# Price Interval Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent price-interval classification model alongside the existing price regression model, then merge both outputs for display and export.

**Architecture:** Create `price_interval.py` as the interval-only module for configuration, labels, classifier training, metrics, loading, and prediction. Keep `dayahead_core.py` as the orchestrator: build existing features, call interval training after regression training, load interval models during prediction, and append interval result columns. The frontend keeps price-model and interval-model training configuration visually separate while sharing common task status and logs.

**Tech Stack:** Python, pandas, numpy, XGBoost/LightGBM/CatBoost when installed, unittest, vanilla HTML/CSS/JS, ECharts.

---

### Task 1: Interval Configuration and Metrics Core

**Files:**
- Create: `price_interval.py`
- Test: `test_price_interval.py`

- [ ] **Step 1: Write failing tests**

```python
from __future__ import annotations

import unittest

import numpy as np


class PriceIntervalCoreTests(unittest.TestCase):
    def test_default_intervals_label_prices(self) -> None:
        from price_interval import interval_label_for_price, normalize_price_intervals

        intervals = normalize_price_intervals(None)

        self.assertEqual([item["label"] for item in intervals], ["<250", "250-300", "300-400", "400-600", "600-1000", ">1000"])
        self.assertEqual(interval_label_for_price(249.99, intervals), "<250")
        self.assertEqual(interval_label_for_price(250.0, intervals), "250-300")
        self.assertEqual(interval_label_for_price(1000.0, intervals), ">1000")

    def test_interval_metrics_include_accuracy_top2_and_high_recall(self) -> None:
        from price_interval import compute_interval_metrics, normalize_price_intervals

        intervals = normalize_price_intervals(None)
        probabilities = np.zeros((3, len(intervals)))
        probabilities[0, 2] = 0.8
        probabilities[0, 3] = 0.2
        probabilities[1, 4] = 0.6
        probabilities[1, 5] = 0.4
        probabilities[2, 1] = 0.7
        probabilities[2, 2] = 0.3

        metrics = compute_interval_metrics(["300-400", ">1000", "300-400"], probabilities, intervals)

        self.assertAlmostEqual(metrics["interval_accuracy"], 1 / 3)
        self.assertAlmostEqual(metrics["top2_accuracy"], 2 / 3)
        self.assertIn("high_price_recall", metrics)
        self.assertIn("score", metrics)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_price_interval.PriceIntervalCoreTests`
Expected: FAIL with `ModuleNotFoundError: No module named 'price_interval'`.

- [ ] **Step 3: Implement core helpers**

Add `DEFAULT_PRICE_INTERVALS`, `normalize_price_intervals()`, `interval_label_for_price()`, `label_prices()`, `compute_interval_metrics()`, `score_interval_metrics()`, and `append_interval_prediction_columns()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_price_interval.PriceIntervalCoreTests`
Expected: OK.

### Task 2: Interval Model Training and Loading

**Files:**
- Modify: `price_interval.py`
- Test: `test_price_interval.py`

- [ ] **Step 1: Write failing tests**

```python
    def test_train_interval_models_selects_backend_and_predicts_probabilities(self) -> None:
        import pandas as pd
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from price_interval import load_interval_model_bundle, normalize_price_intervals, predict_interval_probabilities, train_interval_models

        rows = []
        for day in range(1, 13):
            for period in [1, 2]:
                price = 180.0 if day <= 4 else 350.0 if day <= 8 else 1100.0
                rows.append({
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
                })
        frame = pd.DataFrame(rows)
        intervals = normalize_price_intervals(None)

        with TemporaryDirectory() as temp_dir:
            metadata = train_interval_models(
                frame,
                target_column="price",
                feature_columns=["total_load", "net_load", "renewable_power", "thermal_space_load_ratio", "thermal_on_capacity", "hour", "period", "weekday", "month", "is_weekend", "is_holiday"],
                segment_config=[{"name": "all", "start_period": 1, "end_period": 96}],
                output_dir=Path(temp_dir),
                intervals=intervals,
                valid_days=2,
                num_boost_round=20,
            )
            bundle = load_interval_model_bundle(Path(temp_dir), metadata)
            result = predict_interval_probabilities(frame.head(2), bundle)

        self.assertEqual(result.probabilities.shape[0], 2)
        self.assertEqual(len(result.labels), 2)
        self.assertTrue(metadata["selected_model_key"].startswith("interval_"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_price_interval.PriceIntervalCoreTests.test_train_interval_models_selects_backend_and_predicts_probabilities`
Expected: FAIL with missing training functions.

- [ ] **Step 3: Implement training and loading**

Implement a lightweight classifier matrix that uses available backends from xgboost/lightgbm/catboost, trains per segment, scores validation metrics, writes model files under `interval_<backend>/`, records `price_interval_model` metadata, loads the selected bundle, and predicts probability rows.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test_price_interval.PriceIntervalCoreTests`
Expected: OK.

### Task 3: Core Orchestration Integration

**Files:**
- Modify: `dayahead_core.py`
- Test: `test_price_interval.py`

- [ ] **Step 1: Write failing integration tests**

```python
    def test_training_preferences_persist_price_intervals(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from dayahead_core import load_training_preferences, save_training_preferences

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prefs = save_training_preferences(root, {"price_intervals": [{"label": "cheap", "min": None, "max": 300}, {"label": "expensive", "min": 300, "max": None}]})

            self.assertEqual(prefs["price_intervals"][0]["label"], "cheap")
            self.assertEqual(load_training_preferences(root)["price_intervals"][1]["label"], "expensive")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_price_interval.PriceIntervalCoreTests.test_training_preferences_persist_price_intervals`
Expected: FAIL because preferences do not include interval defaults/normalization.

- [ ] **Step 3: Integrate preferences, training, prediction, export**

Modify `load_training_preferences()` to include `price_intervals`. Modify `train_and_register()` to call interval training after selected regression model training and save interval metadata inside `metadata.json`. Modify `load_models()` and prediction execution to load interval bundle when present. Append interval columns to `result_df`. Extend `export_prediction()` to export interval columns when present.

- [ ] **Step 4: Run tests**

Run: `python -m unittest test_price_interval.PriceIntervalCoreTests test_history_cache.HistoryCacheTests`
Expected: OK.

### Task 4: API and Frontend Integration

**Files:**
- Modify: `api_server.py`
- Modify: `frontend_app/index.html`
- Modify: `frontend_app/assets/app.js`
- Modify: `frontend_app/assets/app.css`
- Modify: `frontend_app/assets/help-content.json`

- [ ] **Step 1: Add UI controls**

Add a separate “价格区间模型训练” card in the train tab with interval boundary inputs, save button, and help icons.

- [ ] **Step 2: Wire API payloads**

Send `price_intervals` with `/api/training/preferences` and `/api/train`. Include interval fields in prediction summaries returned by `serialize_prediction_variant()`.

- [ ] **Step 3: Render prediction cards, color strip, and table columns**

Add summary cards for main interval, high-risk count, and interval backtest accuracy. Add a compact interval color strip under the price chart. Add table columns for interval, interval probability, high-price probability, backtest accuracy, and consistency.

- [ ] **Step 4: Validate frontend assets**

Run: `python -c "import json; json.load(open('frontend_app/assets/help-content.json', encoding='utf-8')); print('ok')"`
Expected: `ok`.

### Task 5: Documentation and Verification

**Files:**
- Modify: `README_timeseg_model.md`
- Modify: `docs/training_model_flow.md`

- [ ] **Step 1: Document interval model**

Describe independent interval training, configurable intervals, prediction fields, and the need to retrain after interval edits.

- [ ] **Step 2: Run final verification**

Run:

```powershell
python -m unittest test_price_interval.PriceIntervalCoreTests test_history_cache.HistoryCacheTests
python -m py_compile price_interval.py dayahead_core.py api_server.py
python -c "import json; json.load(open('frontend_app/assets/help-content.json', encoding='utf-8')); print('json ok')"
git diff --check -- price_interval.py test_price_interval.py dayahead_core.py api_server.py frontend_app/index.html frontend_app/assets/app.js frontend_app/assets/app.css frontend_app/assets/help-content.json README_timeseg_model.md docs/training_model_flow.md
```

Expected: all commands exit 0.

---

## Self-Review

- Spec coverage: interval defaults/config, independent model training, metrics, prediction fields, UI split, help text, and docs are mapped to tasks.
- Placeholder scan: no `TBD` or `TODO` placeholders are present.
- Type consistency: interval metadata key is `price_interval_model`; prediction columns use the spec names.
