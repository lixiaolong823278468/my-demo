# Direct Multi-Model Training Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the legacy single-XGBoost residual training path so training uses direct multi-model price prediction, with similarity curves kept only as reference outputs.

**Architecture:** Keep historical data loading, feature generation, segmentation, and multi-backend model selection. Remove model-training dependence on `residual_target`, make prediction fail fast on legacy residual-only metadata, and keep `similar_price` / `net_load_only_similar_price` as chart/table reference baselines only.

**Tech Stack:** Python, pandas, numpy, XGBoost/LightGBM/CatBoost loaders, unittest, vanilla frontend JavaScript.

---

### Task 1: Lock Desired Behavior With Tests

**Files:**
- Modify: `test_history_cache.py`

- [ ] Add a test that `build_training_frame` output no longer contains `residual_target`.
- [ ] Add a test that prediction rejects legacy residual metadata instead of falling back to `similar_price + residual`.

### Task 2: Remove Residual Training Coupling

**Files:**
- Modify: `dayahead_core.py`

- [ ] Stop creating `residual_target` in training similarity features.
- [ ] Ensure required training columns only require actual target price and direct feature columns.
- [ ] Keep similarity columns available only for backtest/reference summaries.

### Task 3: Remove Legacy Residual Prediction Fallback

**Files:**
- Modify: `dayahead_core.py`

- [ ] Require direct model variants in prediction metadata.
- [ ] Raise a clear error if a residual-only legacy model is loaded.
- [ ] Keep `model_similarity_diff` as display-only `predicted_price - similar_price`, not as a model residual.

### Task 4: Verify

**Files:**
- Run: `python -m unittest test_history_cache.py test_data_quality.py`
- Run: `python -m py_compile dayahead_core.py api_server.py dayahead_timeseg_model.py`

- [ ] Confirm targeted tests pass.
- [ ] Report any broader suite blockers separately.
