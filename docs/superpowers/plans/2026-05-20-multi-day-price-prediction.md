# Multi-Day Price Prediction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent multi-day prediction page backed by `预测文件/预测文件-N天.xlsx`.

**Architecture:** Add a thin multi-day adapter around the existing single-day prediction code. The adapter reads dynamic future-day columns, creates one forecast input per day using the baseline actual price and baseline thermal capacity, runs the existing recent-N-days prediction strategy, and exports a single workbook with one sheet per forecast date.

**Tech Stack:** Python standard library, `openpyxl`, existing `dayahead_core.py` prediction helpers, existing HTTP server in `api_server.py`, static HTML/CSS/JavaScript with ECharts.

---

### Task 1: Backend Multi-Day Workbook Parser

**Files:**
- Modify: `dayahead_core.py`
- Test: `test_multi_day_prediction.py`

- [ ] **Step 1: Write parser tests**

Create `test_multi_day_prediction.py` with tests that build a temporary workbook containing one baseline date and two forecast dates. Assert that the parser detects 96 rows, the baseline date, both forecast dates, baseline prices, baseline thermal capacity, and calculated future net load.

- [ ] **Step 2: Implement parser helpers**

Add helpers to `dayahead_core.py`:
- `MULTI_DAY_FORECAST_FILE = FORECAST_FILE.parent / "预测文件-N天.xlsx"`
- `parse_multi_day_header_date(header: str) -> date | None`
- `parse_multi_day_forecast_workbook(path: Path = MULTI_DAY_FORECAST_FILE) -> dict`

The parser should detect baseline columns by headers containing `日前出清价格` and `火电开机容量`, then detect future forecast dates from repeated `风光电力值` and `总加电力值` header pairs after the baseline block.

- [ ] **Step 3: Run parser tests**

Run: `python -m pytest test_multi_day_prediction.py -q`

Expected: parser tests pass.

### Task 2: Backend Prediction Adapter and Export

**Files:**
- Modify: `dayahead_core.py`
- Test: `test_multi_day_prediction.py`

- [ ] **Step 1: Write adapter/export tests**

Extend `test_multi_day_prediction.py` to validate that one generated forecast frame for a future day contains the same 96 periods and carries baseline prices as lag/base values. Add an export test that writes one workbook with one sheet per forecast date and method headers containing each date.

- [ ] **Step 2: Implement adapter functions**

Add:
- `build_multi_day_forecast_frame(parsed, forecast_date_key)`.
- `predict_multi_day_prices(...)`, which calls the existing prediction function per detected date using `reference_strategy="recent_n_days"`.
- `export_multi_day_prediction_workbook(result, output_path)`.

The adapter should preserve current model, net-load similarity, KNN, weighted KNN, and interval fields from existing prediction rows.

- [ ] **Step 3: Run backend tests**

Run: `python -m pytest test_multi_day_prediction.py test_knn_similarity.py test_price_interval.py -q`

Expected: all selected backend tests pass.

### Task 3: API Endpoints

**Files:**
- Modify: `api_server.py`
- Test: `test_api_server_defaults.py` or `test_multi_day_prediction.py`

- [ ] **Step 1: Write API tests**

Add tests for:
- `GET /api/forecast/multi-day-template` returns columns, rows, and detected forecast dates.
- `POST /api/predict-multi-day` starts a job.
- `GET /api/predict-multi-day/export` returns an Excel file after a prediction result exists.

- [ ] **Step 2: Implement API handlers**

Add route handlers matching the existing `/api/forecast/template`, `/api/predict`, and job patterns:
- preview/save multi-day workbook
- run multi-day prediction in a background job
- store last multi-day prediction on shared server state
- export the last successful multi-day prediction workbook

- [ ] **Step 3: Run API tests**

Run: `python -m pytest test_api_server_defaults.py test_multi_day_prediction.py -q`

Expected: all selected API tests pass.

### Task 4: Frontend Page

**Files:**
- Modify: `frontend_app/index.html`
- Modify: `frontend_app/assets/app.js`
- Modify: `frontend_app/assets/app.css`
- Test: `test_suite.py`

- [ ] **Step 1: Add static UI assertions**

Extend frontend-related tests to assert:
- sidebar contains `预测多天价格`
- new panel has `tab-predict-multi-day`
- the new panel does not contain `same-type-reference-days`
- the new panel contains multi-day run and export controls

- [ ] **Step 2: Add HTML panel**

Add the sidebar button and `tab-predict-multi-day` panel. Reuse existing class names where possible: progress card, prediction action rows, similarity config panels, chart cards, and table shells.

- [ ] **Step 3: Add JavaScript behavior**

Add:
- multi-day template load/save
- multi-day predict job start/poll
- chart rendering per forecast date
- export click handler
- tab initialization and refresh integration

- [ ] **Step 4: Add minimal CSS**

Add only layout rules needed for multiple day cards and stable chart heights.

- [ ] **Step 5: Run frontend/static tests**

Run: `python -m pytest test_suite.py -q` if pytest can run it, otherwise `python test_suite.py`.

Expected: frontend assertions pass.

### Task 5: End-to-End Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run focused tests**

Run:
- `python -m pytest test_multi_day_prediction.py test_api_server_defaults.py test_price_interval.py test_knn_similarity.py -q`
- `python test_suite.py`

- [ ] **Step 2: Start the app server**

Run: `python api_server.py --host 127.0.0.1 --port 8000`

Expected: server starts and the new tab is available in the browser.

- [ ] **Step 3: Manual smoke test**

Open the app, switch to `预测多天价格`, reload the multi-day workbook, run prediction, confirm one chart card per detected date, and export the workbook.

## Self-Review

- Spec coverage: input file, independent page, no same-type-day UI, baseline price reuse, baseline capacity reuse, per-day charts, and multi-sheet export are all covered.
- Placeholder scan: no placeholder tasks remain.
- Type consistency: planned function and endpoint names are consistent across backend, API, and frontend tasks.
