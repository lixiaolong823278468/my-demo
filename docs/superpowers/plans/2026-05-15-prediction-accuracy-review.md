# Prediction Accuracy Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add prediction archive and date-based accuracy review for saved 96-point prediction curves.

**Architecture:** Save each non-duplicate prediction run as JSON under `output/prediction_archive`, expose listing/detail APIs, and render a compact review panel on the prediction page. Actual prices are matched from historical Excel data only.

**Tech Stack:** Python stdlib JSON files, pandas history parsing helpers, existing API server, vanilla HTML/CSS/JS, ECharts.

---

### Task 1: Core Archive Utilities

**Files:**
- Create: `prediction_archive.py`
- Test: `test_prediction_archive.py`

- [ ] Add `build_prediction_archive_record`, `prediction_fingerprint`, `save_prediction_archive_record`, `list_prediction_archives`, and `load_prediction_archive_detail`.
- [ ] Write unit tests for duplicate detection using prices rounded to 2 decimals.
- [ ] Write unit tests for listing records by forecast date.

### Task 2: Actual Price Matching

**Files:**
- Modify: `prediction_archive.py`
- Test: `test_prediction_archive.py`

- [ ] Add helper to load actual prices for a forecast date from existing historical Excel parsing.
- [ ] Add metric computation for joined prediction/actual rows.
- [ ] Test the “no actual price” response path.

### Task 3: Prediction Worker Integration

**Files:**
- Modify: `api_server.py`
- Test: `test_prediction_archive.py`

- [ ] After `predict_prices_compare` completes, archive each generated comparison strategy result.
- [ ] Preserve duplicate-skipped behavior in API response metadata.

### Task 4: Review API

**Files:**
- Modify: `api_server.py`
- Test: `test_prediction_archive.py`

- [ ] Add `GET /api/prediction-archive?date=YYYY-MM-DD`.
- [ ] Add `GET /api/prediction-archive/{archive_id}`.

### Task 5: Frontend Review Panel

**Files:**
- Modify: `frontend_app/index.html`
- Modify: `frontend_app/assets/app.js`
- Modify: `frontend_app/assets/app.css`

- [ ] Add compact “预测准确率回查” card.
- [ ] Add date search, record selector, metric chips, ECharts review chart, and collapsed detail panel.
- [ ] Default chart series: final prediction, actual price, net-load-only baseline.

### Task 6: Verification

**Files:**
- Test: `test_prediction_archive.py`

- [ ] Run `.\.venv\Scripts\python.exe -m unittest test_prediction_archive.py test_history_cache.py test_data_quality.py test_price_interval.py`.
- [ ] Run `.\.venv\Scripts\python.exe -m py_compile prediction_archive.py api_server.py dayahead_core.py price_interval.py`.
- [ ] Run `node --check frontend_app\assets\app.js`.

