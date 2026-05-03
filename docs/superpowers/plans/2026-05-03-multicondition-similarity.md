# Multi-Condition Similarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-condition similarity for model training and prediction, while retaining net-load-only similarity as a prediction reference.

**Architecture:** Extend `dayahead_core.py` with reusable calendar and similarity helpers, then route training and prediction through the new baseline. Keep old net-load-only similarity output as an extra prediction column without changing model feature columns.

**Tech Stack:** Python, pandas, numpy, XGBoost, unittest, vanilla frontend JavaScript.

---

### Task 1: Tests

**Files:**
- Modify: `test_history_cache.py`

- [ ] Add tests for local holiday calendar overrides.
- [ ] Add tests for same-period weighted multi-condition similarity.
- [ ] Add tests that prediction similarity output includes old net-load-only reference data.

### Task 2: Core Similarity

**Files:**
- Modify: `dayahead_core.py`

- [ ] Add `renewable_power` to prepared history and forecast frames.
- [ ] Add local calendar parsing with `holiday` and `workday`.
- [ ] Add weighted same-period multi-condition similarity helper.
- [ ] Use the new helper for training `similar_price`.
- [ ] Keep old net-load-only similarity as `net_load_only_similar_price` for prediction output.

### Task 3: API/UI

**Files:**
- Modify: `api_server.py`
- Modify: `frontend_app/index.html`
- Modify: `frontend_app/assets/app.js`

- [ ] Default API config should expose reference day max of 100.
- [ ] Prediction input should allow 1 to 100.
- [ ] Prediction table should show the net-load-only baseline.

### Task 4: Verification

**Files:**
- Run: `python -m unittest test_history_cache.py test_data_quality.py`
- Run: `python test_suite.py`

- [ ] Confirm targeted tests pass.
- [ ] Confirm broader suite status and call out unrelated failures if any.
