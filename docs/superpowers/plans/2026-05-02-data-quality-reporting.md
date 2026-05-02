# Data Quality Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Excel data-quality diagnostics for training and prediction and expose reports in a dedicated frontend page.

**Architecture:** Add a focused `data_quality.py` module for validation and report persistence. Integrate it into `dayahead_core.py` at the Excel loading boundaries, expose report APIs from `api_server.py`, and render reports in the existing single-page frontend.

**Tech Stack:** Python, pandas, JSON files, built-in HTTP server, vanilla HTML/CSS/JavaScript.

---

### Task 1: Data Quality Module

**Files:**
- Create: `data_quality.py`
- Test: `test_data_quality.py`

- [ ] Write tests for history Sheet validation, forecast template blocking validation, and report persistence.
- [ ] Implement `DataQualityIssue`, validation helpers, and JSON report read/write helpers.
- [ ] Run `python -m unittest test_data_quality.py -v`.

### Task 2: Core Integration

**Files:**
- Modify: `dayahead_core.py`

- [ ] Collect validation issues while loading historical Excel collections.
- [ ] Skip invalid training/history Sheets and include skipped details in saved reports.
- [ ] Block prediction when forecast critical-field issues remain.
- [ ] Attach report paths to train and prediction results.

### Task 3: API Integration

**Files:**
- Modify: `api_server.py`

- [ ] Add report summary fields to train and prediction result serialization.
- [ ] Add `GET /api/data-quality/reports`, `GET /api/data-quality/reports/latest`, and `GET /api/data-quality/reports/{report_id}`.

### Task 4: Frontend Page

**Files:**
- Modify: `frontend_app/index.html`
- Modify: `frontend_app/assets/app.js`
- Modify: `frontend_app/assets/app.css`

- [ ] Add a “数据异常” navigation tab and page.
- [ ] Render latest report summary cards and issue detail table.
- [ ] Load reports when the page opens and after train/predict jobs finish.

### Task 5: Verification

**Files:**
- Test: `test_data_quality.py`

- [ ] Run targeted unit tests.
- [ ] Run a lightweight import check for `dayahead_core.py` and `api_server.py`.
- [ ] Review `git diff` for unintended file changes.
