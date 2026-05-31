# Realtime Price Model Formalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the realtime price model a first-class peer of the day-ahead price model, with independent training, optimization, version selection, segment model selection, prediction output, archive review, and cached acceleration.

**Architecture:** Introduce target-aware model operations while preserving the current day-ahead defaults. `dayahead_core.py` remains the shared training and prediction engine; `api_server.py` becomes target-aware at the endpoint layer; frontend pages expose two independent model targets while keeping the single prediction action and single output workbook.

**Tech Stack:** Python standard library HTTP server, pandas/openpyxl, existing XGBoost/LightGBM/CatBoost training helpers, vanilla JavaScript frontend, Node assertion tests, Python `unittest`.

---

## File Structure

- Modify `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_core.py`
  - Keep shared model training and prediction code.
  - Add target-aware helpers for model roots, preferences, status columns, and realtime prediction version selection.
  - Keep `predicted_price` as day-ahead output and `realtime_predicted_price` as realtime output.

- Modify `D:\每日工作\代码示例\预测程序-------\demo1\api_server.py`
  - Add target-aware training, preferences, versions, segment selection, and prediction version handling.
  - Add total-control sequential optimization job: day-ahead first, realtime second, failures isolated.
  - Preserve existing day-ahead endpoints as defaults for compatibility.

- Modify `D:\每日工作\代码示例\预测程序-------\demo1\prediction_archive.py`
  - Extend archive metrics only where needed for formal realtime status fields.
  - Keep the already-added realtime actual-price comparison behavior.

- Modify `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\index.html`
  - Add the training total-control block under space cleanup.
  - Split training center into day-ahead and realtime peer sections.
  - Add realtime version selection on prediction page.
  - Move dense diagnostics from training center into model versions page.

- Modify `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.js`
  - Add target-aware state management.
  - Add total-control job start/poll/render logic.
  - Add separate realtime training preferences, manual train, optimization, version selection, and segment model selection.
  - Keep day-ahead behavior unchanged when no target is specified.

- Modify `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\progress_state.js`
  - Add total-control progress derivation and realtime training reconciliation.

- Modify `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.css`
  - Style total-control and peer training sections.
  - Keep visual density compact and readable for an operational tool.

- Add or modify tests:
  - `D:\每日工作\代码示例\预测程序-------\demo1\test\test_realtime_price_model.py`
  - `D:\每日工作\代码示例\预测程序-------\demo1\test\test_prediction_archive.py`
  - `D:\每日工作\代码示例\预测程序-------\demo1\test\test_api_server_defaults.py`
  - `D:\每日工作\代码示例\预测程序-------\demo1\test\test_model_versions.py`
  - `D:\每日工作\代码示例\预测程序-------\demo1\test\test_window_optimization_segments.py`
  - `D:\每日工作\代码示例\预测程序-------\demo1\test\test_frontend_progress_state.js`
  - `D:\每日工作\代码示例\预测程序-------\demo1\test\test_frontend_realtime_prediction_chart.js`
  - Add `D:\每日工作\代码示例\预测程序-------\demo1\test\test_dual_model_training_control.py`
  - Add `D:\每日工作\代码示例\预测程序-------\demo1\test\test_frontend_dual_model_controls.js`

---

## Task 1: Add Target-Aware Model Helpers

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_core.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_realtime_price_model.py`

- [ ] **Step 1: Write failing tests for model target resolution**

Add tests that prove day-ahead remains default and realtime resolves to `models/realtime_price`.

```python
def test_model_target_context_defaults_to_dayahead() -> None:
    from dayahead_core import model_target_context

    context = model_target_context(None)

    assert context["target"] == "dayahead"
    assert context["data_mode"] == "dayahead"
    assert context["model_root"].name == "models"
    assert context["trains_capacity"] is True


def test_model_target_context_resolves_realtime_root() -> None:
    from dayahead_core import model_target_context

    context = model_target_context("realtime")

    assert context["target"] == "realtime"
    assert context["data_mode"] == "realtime"
    assert context["model_root"].name == "realtime_price"
    assert context["trains_capacity"] is False
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m unittest test.test_realtime_price_model
```

Expected: failure because `model_target_context` is not defined.

- [ ] **Step 3: Implement target helper**

Add near existing constants in `dayahead_core.py`:

```python
MODEL_TARGET_DAYAHEAD = "dayahead"
MODEL_TARGET_REALTIME = "realtime"


def normalize_model_target(target: str | None) -> str:
    normalized = str(target or MODEL_TARGET_DAYAHEAD).strip().lower()
    if normalized in {"", "dayahead", "日前", "day_ahead"}:
        return MODEL_TARGET_DAYAHEAD
    if normalized in {"realtime", "实时", "real_time"}:
        return MODEL_TARGET_REALTIME
    raise ValueError(f"未知模型目标: {target}")


def model_target_context(target: str | None, base_model_root: str | Path = DEFAULT_MODEL_ROOT) -> dict[str, object]:
    normalized = normalize_model_target(target)
    model_root = Path(base_model_root) if normalized == MODEL_TARGET_DAYAHEAD else realtime_model_root(base_model_root)
    return {
        "target": normalized,
        "data_mode": REALTIME_DATA_MODE if normalized == MODEL_TARGET_REALTIME else DAYAHEAD_DATA_MODE,
        "model_root": model_root,
        "target_column": REALTIME_TARGET_SOURCE_COLUMN if normalized == MODEL_TARGET_REALTIME else TARGET_COLUMN,
        "trains_capacity": normalized == MODEL_TARGET_DAYAHEAD,
    }
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
python -m unittest test.test_realtime_price_model
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add dayahead_core.py test/test_realtime_price_model.py
git commit -m "feat: add target-aware model context"
```

---

## Task 2: Make Training Preferences Independent by Target

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_core.py`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\api_server.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_realtime_price_model.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_api_server_defaults.py`

- [ ] **Step 1: Write failing tests for first-copy then independent preferences**

Add:

```python
def test_realtime_preferences_copy_dayahead_once_then_stay_independent(tmp_path) -> None:
    from dayahead_core import load_training_preferences, save_training_preferences
    from api_server import load_target_training_preferences, save_target_training_preferences

    model_root = tmp_path / "models"
    save_training_preferences(model_root, {"segment_mode": "custom", "price_model_config": {"valid_days": 11}})

    realtime_first = load_target_training_preferences("realtime", model_root=model_root)
    assert realtime_first["price_model_config"]["valid_days"] == 11

    save_target_training_preferences("realtime", {"price_model_config": {"valid_days": 7}}, model_root=model_root)
    save_training_preferences(model_root, {"price_model_config": {"valid_days": 21}})

    realtime_second = load_target_training_preferences("realtime", model_root=model_root)
    assert realtime_second["price_model_config"]["valid_days"] == 7
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m unittest test.test_realtime_price_model test.test_api_server_defaults
```

Expected: failure because target preference helpers are not defined.

- [ ] **Step 3: Implement target preference helpers**

Add to `api_server.py` near existing preferences helpers:

```python
def target_model_root(target: str | None, model_root: Path = MODEL_ROOT) -> Path:
    context = model_target_context(target, model_root)
    return Path(context["model_root"])


def load_target_training_preferences(target: str | None, model_root: Path = MODEL_ROOT) -> dict[str, Any]:
    normalized = normalize_model_target(target)
    root = target_model_root(normalized, model_root)
    if normalized == MODEL_TARGET_REALTIME:
        path = root / "training_preferences.json"
        if path.exists():
            return load_training_preferences(root)
        day_ahead_preferences = load_training_preferences(model_root)
        save_training_preferences(root, day_ahead_preferences)
        return load_training_preferences(root)
    return load_training_preferences(root)


def save_target_training_preferences(target: str | None, preferences: dict[str, Any], model_root: Path = MODEL_ROOT) -> dict[str, Any]:
    root = target_model_root(target, model_root)
    return save_training_preferences(root, preferences)
```

- [ ] **Step 4: Wire GET and POST preference endpoints**

Modify `/api/training/preferences` and `/api/prediction/preferences` handling to read optional query/body `target`. Default must remain day-ahead.

```python
target = str((query.get("target") or ["dayahead"])[0] or "dayahead")
return self.send_json({"preferences": load_target_training_preferences(target)})
```

For POST:

```python
target = str(payload.get("target") or "dayahead")
preferences = save_target_training_preferences(target, payload.get("preferences") or payload)
return self.send_json({"preferences": preferences})
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
python -m unittest test.test_realtime_price_model test.test_api_server_defaults
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add dayahead_core.py api_server.py test/test_realtime_price_model.py test/test_api_server_defaults.py
git commit -m "feat: store realtime training preferences independently"
```

---

## Task 3: Add Manual Realtime Training

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\api_server.py`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_core.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_realtime_price_model.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_api_server_defaults.py`

- [ ] **Step 1: Write failing test for realtime manual TrainConfig**

Add:

```python
def test_build_train_worker_uses_realtime_data_mode_and_skips_capacity(monkeypatch, tmp_path) -> None:
    import api_server

    captured = {}

    def fake_train_and_register(config, progress_callback=None):
        captured["data_mode"] = config.data_mode
        captured["model_root"] = config.model_root
        captured["train_capacity_model"] = getattr(config, "train_capacity_model", True)
        return {"metadata": {"run_id": "run_rt"}}

    monkeypatch.setattr(api_server, "train_and_register", fake_train_and_register)

    worker = api_server.build_train_worker({"target": "realtime", "model_root": str(tmp_path / "models")})
    worker("job_rt")

    assert captured["data_mode"] == "realtime"
    assert captured["model_root"].name == "realtime_price"
    assert captured["train_capacity_model"] is False
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m unittest test.test_realtime_price_model
```

Expected: failure because manual training ignores `target`.

- [ ] **Step 3: Extend `TrainConfig` only if needed**

If `TrainConfig` does not already have a capacity toggle, add:

```python
train_capacity_model: bool = True
```

In `train_and_register`, guard capacity-model training with:

```python
if config.train_capacity_model:
    capacity_result = train_capacity_model(...)
else:
    capacity_result = None
```

- [ ] **Step 4: Make `build_train_worker` target-aware**

In `api_server.py`, update `build_train_worker`:

```python
target = normalize_model_target(payload.get("target"))
context = model_target_context(target, payload.get("model_root") or MODEL_ROOT)
model_root = Path(context["model_root"])
data_mode = str(context["data_mode"])
train_capacity_model = bool(context["trains_capacity"])
```

Pass these into `TrainConfig`:

```python
TrainConfig(
    history_dir=Path(payload.get("history_dir") or HISTORY_DIR),
    model_root=model_root,
    data_mode=data_mode,
    train_capacity_model=train_capacity_model,
    ...
)
```

- [ ] **Step 5: Add endpoint compatibility**

Keep existing `/api/train` as day-ahead by default. Accept `target: "realtime"` in the same endpoint body. If frontend prefers explicit endpoint, add `/api/realtime-train/run` that forwards to the same worker with `target="realtime"`.

- [ ] **Step 6: Run tests and verify pass**

Run:

```powershell
python -m unittest test.test_realtime_price_model test.test_api_server_defaults
python -m py_compile dayahead_core.py api_server.py
```

Expected: all tests pass and compile succeeds.

- [ ] **Step 7: Commit**

```powershell
git add dayahead_core.py api_server.py test/test_realtime_price_model.py test/test_api_server_defaults.py
git commit -m "feat: support manual realtime price training"
```

---

## Task 4: Add Sequential Dual-Model Training Control

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\api_server.py`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\progress_state.js`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_dual_model_training_control.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_frontend_progress_state.js`

- [ ] **Step 1: Write failing backend tests for partial success**

Create `test/test_dual_model_training_control.py`:

```python
from __future__ import annotations

import unittest


class DualModelTrainingControlTests(unittest.TestCase):
    def test_dual_control_continues_when_dayahead_fails(self) -> None:
        from api_server import run_dual_window_optimization_sequence

        calls = []

        def runner(target: str) -> dict:
            calls.append(target)
            if target == "dayahead":
                raise RuntimeError("dayahead failed")
            return {"target": target, "run_id": "run_rt"}

        result = run_dual_window_optimization_sequence({}, runner=runner)

        self.assertEqual(calls, ["dayahead", "realtime"])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["targets"]["dayahead"]["status"], "failed")
        self.assertEqual(result["targets"]["realtime"]["status"], "success")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m unittest test.test_dual_model_training_control
```

Expected: failure because `run_dual_window_optimization_sequence` is not defined.

- [ ] **Step 3: Implement sequential control helper**

Add to `api_server.py`:

```python
def run_dual_window_optimization_sequence(payload: dict[str, Any], runner: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    target_runner = runner or (lambda target: check_window_optimization("manual", force=bool(payload.get("force", True)), payload={**payload, "target": target}))
    results: dict[str, Any] = {}
    for target in ("dayahead", "realtime"):
        try:
            outcome = target_runner(target)
            results[target] = {"status": "success", "result": outcome}
        except Exception as exc:  # noqa: BLE001
            results[target] = {"status": "failed", "error": str(exc)}
    success_count = sum(1 for item in results.values() if item["status"] == "success")
    if success_count == 2:
        status = "success"
    elif success_count == 1:
        status = "partial_success"
    else:
        status = "failed"
    return {"status": status, "targets": results}
```

- [ ] **Step 4: Add total-control endpoint**

Add POST route:

```python
if path == "/api/dual-window-optimization/run":
    return self.send_json(
        STATE.start_job("dual_optimize", build_dual_window_optimization_worker(payload)),
        HTTPStatus.ACCEPTED,
    )
```

Worker:

```python
def build_dual_window_optimization_worker(payload: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    def worker(job_id: str) -> dict[str, Any]:
        STATE.append_log(job_id, "开始一键训练两套价格模型", 1)

        def runner(target: str) -> dict[str, Any]:
            STATE.append_log(job_id, f"开始{target}模型自动寻优", 5 if target == "dayahead" else 55)
            if target == "dayahead":
                return run_window_optimization_for_target(payload, MODEL_TARGET_DAYAHEAD, job_id)
            return run_window_optimization_for_target(payload, MODEL_TARGET_REALTIME, job_id)

        result = run_dual_window_optimization_sequence(payload, runner=runner)
        STATE.append_log(job_id, f"一键训练完成：{result['status']}", 100)
        return result

    return worker
```

- [ ] **Step 5: Extract `run_window_optimization_for_target`**

Refactor existing day-ahead and realtime optimization calls so both use one helper:

```python
def run_window_optimization_for_target(payload: dict[str, Any], target: str, job_id: str) -> dict[str, Any]:
    context = model_target_context(target, MODEL_ROOT)
    return run_window_optimization_worker(
        target_model_root=Path(context["model_root"]),
        data_mode=str(context["data_mode"]),
        train_capacity_model=bool(context["trains_capacity"]),
        payload=payload,
        job_id=job_id,
    )
```

Keep existing `/api/window-optimization/run` and `/api/realtime-window-optimization/run` forwarding to this helper.

- [ ] **Step 6: Add frontend progress-state test**

In `test/test_frontend_progress_state.js`, add:

```javascript
const partial = helpers.deriveDualOptimizationState({
  status: "partial_success",
  targets: {
    dayahead: { status: "success" },
    realtime: { status: "failed", error: "missing realtime price" },
  },
});
assert.equal(partial.type, "warning");
assert.match(partial.status, /部分成功/);
```

- [ ] **Step 7: Implement progress helper**

In `progress_state.js`:

```javascript
function deriveDualOptimizationState(result) {
  if (!result) return { progress: 0, label: "未开始", status: "等待一键训练两套模型", type: "idle" };
  if (result.status === "success") return { progress: 100, label: "已完成", status: "两套模型训练完成", type: "success" };
  if (result.status === "partial_success") return { progress: 100, label: "部分成功", status: "一套模型成功，一套模型失败", type: "warning" };
  if (result.status === "failed") return { progress: 100, label: "失败", status: "两套模型都失败", type: "error" };
  return { progress: result.progress || 0, label: "运行中", status: result.status || "一键训练运行中", type: "running" };
}
```

Export it with existing helpers.

- [ ] **Step 8: Run tests and verify pass**

Run:

```powershell
python -m unittest test.test_dual_model_training_control test.test_window_optimization_segments
node test/test_frontend_progress_state.js
python -m py_compile api_server.py
```

Expected: all tests pass and compile succeeds.

- [ ] **Step 9: Commit**

```powershell
git add api_server.py frontend_app/assets/progress_state.js test/test_dual_model_training_control.py test/test_frontend_progress_state.js
git commit -m "feat: add sequential dual-model training control"
```

---

## Task 5: Add Target-Aware Model Versions and Segment Selection

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\api_server.py`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_core.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_model_versions.py`

- [ ] **Step 1: Write failing tests for realtime versions**

Add:

```python
def test_model_versions_endpoint_can_list_realtime_versions(tmp_path) -> None:
    from api_server import list_model_versions_for_target

    root = tmp_path / "models"
    current = root / "realtime_price" / "current"
    current.mkdir(parents=True)
    (current / "metadata.json").write_text('{"run_id":"run_rt","target_market":"realtime"}', encoding="utf-8")

    versions = list_model_versions_for_target("realtime", model_root=root)

    assert versions[0]["run_id"] == "run_rt"
    assert versions[0]["target_market"] == "realtime"


def test_segment_selection_updates_realtime_metadata_only(tmp_path) -> None:
    from api_server import update_segment_price_model_selection_for_target
    import json

    day_current = tmp_path / "models" / "current"
    rt_current = tmp_path / "models" / "realtime_price" / "current"
    day_current.mkdir(parents=True)
    rt_current.mkdir(parents=True)
    (day_current / "metadata.json").write_text('{"run_id":"run_day"}', encoding="utf-8")
    (rt_current / "metadata.json").write_text('{"run_id":"run_rt"}', encoding="utf-8")

    update_segment_price_model_selection_for_target("realtime", {"segment_1": "no_lag_96_xgboost"}, model_root=tmp_path / "models")

    day = json.loads((day_current / "metadata.json").read_text(encoding="utf-8"))
    rt = json.loads((rt_current / "metadata.json").read_text(encoding="utf-8"))
    assert "selected_segment_price_models" not in day
    assert rt["selected_segment_price_models"]["segment_1"] == "no_lag_96_xgboost"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m unittest test.test_model_versions
```

Expected: failure because target-aware helpers are missing.

- [ ] **Step 3: Implement target-aware version helpers**

Add to `api_server.py`:

```python
def list_model_versions_for_target(target: str | None, model_root: Path = MODEL_ROOT) -> list[dict[str, Any]]:
    root = target_model_root(target, model_root)
    return list_model_versions(root)


def update_segment_price_model_selection_for_target(target: str | None, selected: dict[str, str], model_root: Path = MODEL_ROOT) -> dict[str, Any]:
    root = target_model_root(target, model_root)
    return update_segment_price_model_selection(root, selected)
```

- [ ] **Step 4: Wire endpoints**

Update:

```python
if path == "/api/model/versions":
    target = str((query.get("target") or ["dayahead"])[0] or "dayahead")
    return self.send_json({"versions": list_model_versions_for_target(target)})
```

Update POST `/api/model/segment-selection`:

```python
target = str(payload.get("target") or "dayahead")
metadata = update_segment_price_model_selection_for_target(target, payload.get("selected_segment_price_models") or {})
return self.send_json({"metadata": metadata})
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest test.test_model_versions test.test_realtime_price_model
python -m py_compile api_server.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add api_server.py test/test_model_versions.py
git commit -m "feat: manage realtime model versions independently"
```

---

## Task 6: Add Independent Realtime Version Selection During Prediction

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_core.py`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\api_server.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_realtime_price_model.py`

- [ ] **Step 1: Write failing test**

Add:

```python
def test_predict_worker_passes_realtime_version_key(monkeypatch, tmp_path) -> None:
    import api_server

    captured = {}

    def fake_predict_prices_compare(**kwargs):
        captured.update(kwargs)
        return type("Result", (), {
            "forecast_date": "2026-05-26",
            "output_file": tmp_path / "out.xlsx",
            "template_updated": False,
            "selected_strategy_key": "recent_n_days",
            "selected_strategy_label": "最近 N 天",
            "quality_report_path": None,
            "strategy_results": {},
        })()

    monkeypatch.setattr(api_server, "predict_prices_compare", fake_predict_prices_compare)

    worker = api_server.build_predict_worker({
        "model_version_key": "run_day",
        "realtime_model_version_key": "run_rt",
        "model_root": str(tmp_path / "models"),
    })
    try:
        worker("job_predict")
    except Exception:
        pass

    assert captured["realtime_model_version_key"] == "run_rt"
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m unittest test.test_realtime_price_model
```

Expected: failure because prediction does not accept `realtime_model_version_key`.

- [ ] **Step 3: Extend prediction function signatures**

In `dayahead_core.py`, update `predict_prices` and `predict_prices_compare`:

```python
def predict_prices_compare(
    ...,
    realtime_model_version_key: str | None = None,
) -> PredictCompareResult:
```

Pass into:

```python
result_df = append_realtime_prediction_if_available(
    result_df,
    forecast_file=forecast_file,
    history_dir=history_dir,
    model_root=model_root,
    realtime_model_version_key=realtime_model_version_key,
    ...
)
```

- [ ] **Step 4: Resolve realtime selected model root**

Update `append_realtime_prediction_if_available`:

```python
realtime_root = realtime_model_root(model_root)
if realtime_model_version_key:
    selected_realtime_dir = realtime_root / "history" / realtime_model_version_key
    if not selected_realtime_dir.exists():
        raise FileNotFoundError(f"未找到实时模型版本：{realtime_model_version_key}")
    realtime_prediction_root = selected_realtime_dir.parent.parent
    realtime_current_override = selected_realtime_dir
else:
    realtime_prediction_root = realtime_root
    realtime_current_override = None
```

If existing loaders require a `current` directory, copy selected version into a temp root just like `selected_prediction_model_root`.

- [ ] **Step 5: Add status fields**

When realtime succeeds:

```python
merged["realtime_prediction_status"] = "ok"
merged["realtime_prediction_error"] = None
merged["realtime_model_version"] = realtime_metadata.get("run_id")
```

When realtime fails:

```python
fallback["realtime_prediction_status"] = "failed"
fallback["realtime_prediction_error"] = str(exc)
```

- [ ] **Step 6: Pass payload from API**

In `build_predict_worker`:

```python
realtime_model_version_key = str(payload.get("realtime_model_version_key") or "").strip() or None
```

Pass to `predict_prices_compare`.

- [ ] **Step 7: Run tests**

Run:

```powershell
python -m unittest test.test_realtime_price_model test.test_history_cache
python -m py_compile dayahead_core.py api_server.py
```

Expected: all tests pass and compile succeeds.

- [ ] **Step 8: Commit**

```powershell
git add dayahead_core.py api_server.py test/test_realtime_price_model.py
git commit -m "feat: select realtime model version during prediction"
```

---

## Task 7: Update Prediction Export Columns

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_core.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_realtime_price_model.py`

- [ ] **Step 1: Write failing export test**

Add:

```python
def test_export_prediction_includes_dual_model_status_columns(tmp_path) -> None:
    import pandas as pd
    from dayahead_core import export_prediction

    output = tmp_path / "prediction.xlsx"
    frame = pd.DataFrame({
        "date": ["2026-05-26"],
        "period": [1],
        "predicted_price": [300.0],
        "realtime_predicted_price": [310.0],
        "price_spread_realtime_minus_dayahead": [10.0],
        "model_variant": ["day_model"],
        "realtime_model_variant": ["rt_model"],
        "dayahead_model_version": ["run_day"],
        "realtime_model_version": ["run_rt"],
        "realtime_prediction_status": ["ok"],
        "realtime_prediction_error": [None],
    })

    export_prediction(frame, output)
    exported = pd.read_excel(output)

    assert "realtime_prediction_status" in exported.columns
    assert "price_spread_realtime_minus_dayahead" in exported.columns
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m unittest test.test_realtime_price_model
```

Expected: failure because export column allow-list omits new fields.

- [ ] **Step 3: Add spread calculation**

In `merge_realtime_prediction_columns`:

```python
if "predicted_price" in result.columns and "realtime_predicted_price" in result.columns:
    result["price_spread_realtime_minus_dayahead"] = (
        pd.to_numeric(result["realtime_predicted_price"], errors="coerce")
        - pd.to_numeric(result["predicted_price"], errors="coerce")
    )
```

- [ ] **Step 4: Update export column order**

In `export_prediction`, add:

```python
"realtime_predicted_price",
"price_spread_realtime_minus_dayahead",
"dayahead_model_version",
"realtime_model_version",
"realtime_model_variant",
"realtime_prediction_status",
"realtime_prediction_error",
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest test.test_realtime_price_model
python -m py_compile dayahead_core.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add dayahead_core.py test/test_realtime_price_model.py
git commit -m "feat: export dual price model status columns"
```

---

## Task 8: Update Prediction Page With Two Version Selectors

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\index.html`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.js`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.css`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_frontend_dual_model_controls.js`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_frontend_realtime_prediction_chart.js`

- [ ] **Step 1: Write failing frontend test**

Create `test/test_frontend_dual_model_controls.js`:

```javascript
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const html = fs.readFileSync(path.join(__dirname, "../frontend_app/index.html"), "utf8");
const appJs = fs.readFileSync(path.join(__dirname, "../frontend_app/assets/app.js"), "utf8");

assert.match(html, /id="predict-model-version"/);
assert.match(html, /id="predict-realtime-model-version"/);
assert.match(appJs, /realtime_model_version_key/);
assert.match(appJs, /loadRealtimeModelVersions/);

console.log("frontend dual model controls checks passed");
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
node test/test_frontend_dual_model_controls.js
```

Expected: failure because realtime selector is absent.

- [ ] **Step 3: Add realtime selector markup**

In prediction controls near existing `predict-model-version`:

```html
<label class="field">
  <span>日前价格模型版本</span>
  <select id="predict-model-version">
    <option value="">当前默认日前模型</option>
  </select>
</label>
<label class="field">
  <span>实时价格模型版本</span>
  <select id="predict-realtime-model-version">
    <option value="">当前默认实时模型</option>
  </select>
</label>
```

- [ ] **Step 4: Add JS loader**

In `app.js`:

```javascript
async function loadRealtimeModelVersions() {
  const data = await request("/api/model/versions?target=realtime");
  renderModelVersionOptions("#predict-realtime-model-version", data.versions || [], "当前默认实时模型");
}
```

If `renderModelVersionOptions` does not exist, extract the current version select rendering into:

```javascript
function renderModelVersionOptions(selector, versions, defaultLabel) {
  const select = $(selector);
  if (!select) return;
  const options = [`<option value="">${htmlEscape(defaultLabel)}</option>`];
  options.push(...(versions || []).map((item) => {
    const value = htmlEscape(item.version_key || item.run_id || "");
    const label = htmlEscape(`${item.run_id || item.version_key || "-"}${item.is_default ? "（当前默认）" : ""}`);
    return `<option value="${value}">${label}</option>`;
  }));
  select.innerHTML = options.join("");
}
```

- [ ] **Step 5: Include realtime version in prediction payload**

In `startPredict` payload:

```javascript
realtime_model_version_key: $("#predict-realtime-model-version")?.value || "",
```

- [ ] **Step 6: Run frontend tests**

Run:

```powershell
node test/test_frontend_dual_model_controls.js
node test/test_frontend_realtime_prediction_chart.js
node --check frontend_app/assets/app.js
```

Expected: all checks pass.

- [ ] **Step 7: Commit**

```powershell
git add frontend_app/index.html frontend_app/assets/app.js frontend_app/assets/app.css test/test_frontend_dual_model_controls.js
git commit -m "feat: choose day-ahead and realtime model versions for prediction"
```

---

## Task 9: Build Training Center Total-Control and Peer Sections

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\index.html`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.js`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.css`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_frontend_dual_model_controls.js`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_frontend_progress_state.js`

- [ ] **Step 1: Extend failing frontend test**

Add assertions:

```javascript
assert.match(html, /id="dual-optimize-window-btn"/);
assert.match(html, /id="dayahead-training-panel"/);
assert.match(html, /id="realtime-training-panel"/);
assert.match(appJs, /startDualWindowOptimization/);
assert.match(appJs, /\/api\/dual-window-optimization\/run/);
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
node test/test_frontend_dual_model_controls.js
```

Expected: failure because total-control UI is absent.

- [ ] **Step 3: Add total-control markup under space cleanup**

Add in `index.html`:

```html
<section class="train-control-panel" id="dual-training-control">
  <div class="toolbar-row">
    <div>
      <div class="toolbar-title">模型训练总控</div>
      <div class="toolbar-meta">按日前模型 -> 实时模型顺序自动寻优并训练，两套模型失败互不阻断</div>
    </div>
    <button class="primary-btn" id="dual-optimize-window-btn" type="button">一键训练两套价格模型</button>
    <button class="stop-btn hidden" id="stop-dual-optimize-btn" type="button">停止总控任务</button>
  </div>
  <div class="progress-card" id="dual-optimize-progress-card">
    <div class="progress-header">
      <strong>总控任务</strong>
      <span class="progress-state-text" id="dual-optimize-progress-text">未开始</span>
    </div>
    <div class="progress-status-line" id="dual-optimize-progress-status">等待一键训练两套模型</div>
    <div class="progress-bar"><div class="progress-fill" id="dual-optimize-progress-fill"></div></div>
  </div>
</section>
```

- [ ] **Step 4: Mark peer panels**

Wrap day-ahead training controls:

```html
<section class="training-target-panel" id="dayahead-training-panel" data-target="dayahead">
  <div class="toolbar-title">日前价格模型训练</div>
  ...
</section>
```

Wrap realtime training controls:

```html
<section class="training-target-panel" id="realtime-training-panel" data-target="realtime">
  <div class="toolbar-title">实时价格模型训练</div>
  ...
</section>
```

- [ ] **Step 5: Add JS total-control function**

In `app.js`:

```javascript
async function startDualWindowOptimization() {
  const btn = $("#dual-optimize-window-btn");
  const originalText = btn?.textContent || "一键训练两套价格模型";
  try {
    setButtonLoading(btn, true, originalText);
    App.statusFocus = "dual-optimize";
    applyProgressCard("dual-optimize", { progress: 3, label: "提交中", status: "正在提交一键训练任务...", type: "running" });
    const data = await request("/api/dual-window-optimization/run", {
      method: "POST",
      body: JSON.stringify(collectWindowOptimizationPayload()),
    });
    App.activeJobIds["dual-optimize"] = data.job_id || data.job?.job_id;
    syncStopButtons();
    showToast("一键训练两套模型已启动");
  } catch (error) {
    showToast(error.message, "error");
    applyProgressCard("dual-optimize", { progress: 0, label: "错误", status: error.message, type: "error" });
  } finally {
    setButtonLoading(btn, false, originalText);
  }
}
```

- [ ] **Step 6: Bind events and stop button**

Add:

```javascript
$("#dual-optimize-window-btn")?.addEventListener("click", () => startDualWindowOptimization().catch((error) => showToast(error.message, "error")));
$("#stop-dual-optimize-btn")?.addEventListener("click", () => cancelJob("dual-optimize"));
```

Extend active job maps:

```javascript
"dual-optimize": null,
```

- [ ] **Step 7: Add CSS**

```css
.train-control-panel,
.training-target-panel {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  background: var(--panel-bg);
}

.training-target-panel + .training-target-panel {
  margin-top: 16px;
}
```

- [ ] **Step 8: Run tests**

Run:

```powershell
node test/test_frontend_dual_model_controls.js
node test/test_frontend_progress_state.js
node --check frontend_app/assets/app.js
```

Expected: all checks pass.

- [ ] **Step 9: Commit**

```powershell
git add frontend_app/index.html frontend_app/assets/app.js frontend_app/assets/app.css test/test_frontend_dual_model_controls.js
git commit -m "feat: add dual model training controls"
```

---

## Task 10: Move Diagnostics Responsibility to Model Versions Page

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\index.html`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.js`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.css`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_frontend_dual_model_controls.js`

- [ ] **Step 1: Add frontend structure test**

Add:

```javascript
assert.match(html, /id="model-version-target"/);
assert.match(html, /id="version-diagnostics-panel"/);
assert.match(appJs, /renderTargetModelVersions/);
assert.match(appJs, /loadModelVersionsForTarget/);
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
node test/test_frontend_dual_model_controls.js
```

Expected: failure because version target UI is absent.

- [ ] **Step 3: Add version target segmented control**

In model versions tab:

```html
<div class="segmented-control" id="model-version-target">
  <button type="button" class="segment active" data-target="dayahead">日前价格模型</button>
  <button type="button" class="segment" data-target="realtime">实时价格模型</button>
</div>
<section id="version-diagnostics-panel"></section>
```

- [ ] **Step 4: Add target-aware version rendering**

In `app.js`:

```javascript
async function loadModelVersionsForTarget(target = "dayahead") {
  const data = await request(`/api/model/versions?target=${encodeURIComponent(target)}`);
  renderTargetModelVersions(target, data.versions || []);
}

function renderTargetModelVersions(target, versions) {
  App.versionTarget = target;
  App.versions = versions;
  renderVersions(versions);
  renderVersionDiagnostics(target, versions[0] || null);
}
```

- [ ] **Step 5: Move dense diagnostics render calls**

Ensure these render inside model version page only:

```javascript
renderRollingBacktest(metadata);
renderModelCandidateRankings(App.modelCandidateRankings);
renderVersionDiagnostics(target, currentVersion);
```

Training center should only display latest summary:

```javascript
renderTrainingSummaryCard("dayahead", status.current_model);
renderTrainingSummaryCard("realtime", status.current_realtime_model);
```

- [ ] **Step 6: Run checks**

Run:

```powershell
node test/test_frontend_dual_model_controls.js
node --check frontend_app/assets/app.js
```

Expected: checks pass.

- [ ] **Step 7: Commit**

```powershell
git add frontend_app/index.html frontend_app/assets/app.js frontend_app/assets/app.css test/test_frontend_dual_model_controls.js
git commit -m "feat: move model diagnostics to versions page"
```

---

## Task 11: Formalize Archive Review Realtime Metrics

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\prediction_archive.py`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.js`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_prediction_archive.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_frontend_realtime_archive_review.js`

- [ ] **Step 1: Add direction-accuracy test for realtime**

In `test_prediction_archive.py`, add:

```python
def test_archive_detail_reports_realtime_direction_accuracy(tmp_path) -> None:
    from prediction_archive import archive_prediction_metrics
    import pandas as pd

    merged = pd.DataFrame({
        "date": ["2026-05-15"] * 3,
        "period": [1, 2, 3],
        "actual_price": [100.0, 110.0, 105.0],
        "predicted_price": [101.0, 111.0, 106.0],
        "realtime_actual_price": [90.0, 120.0, 100.0],
        "realtime_predicted_price": [91.0, 119.0, 101.0],
    })

    metrics = archive_prediction_metrics(merged, {"forecast_date": "2026-05-15"})

    assert "direction_accuracy" in metrics["realtime_predicted_price"]
```

- [ ] **Step 2: Run tests**

Run:

```powershell
python -m unittest test.test_prediction_archive
```

Expected: pass if current metrics helper already returns direction accuracy; otherwise fail and expose missing metric.

- [ ] **Step 3: Ensure frontend metric chips show realtime direction**

In `renderArchiveMetrics`, add:

```javascript
["实时方向准确率", "archiveMetricDirectionAccuracy", realtimeMetrics ? formatPercentCell(realtimeMetrics.direction_accuracy) : "-"],
```

- [ ] **Step 4: Run frontend archive tests**

Run:

```powershell
node test/test_frontend_realtime_archive_review.js
node --check frontend_app/assets/app.js
```

Expected: checks pass.

- [ ] **Step 5: Commit**

```powershell
git add prediction_archive.py frontend_app/assets/app.js test/test_prediction_archive.py test/test_frontend_realtime_archive_review.js
git commit -m "feat: show realtime archive direction metrics"
```

---

## Task 12: Add Shared Cache and Skip-Unchanged Training Guard

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_core.py`
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\api_server.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_history_cache.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_realtime_price_model.py`

- [ ] **Step 1: Write failing cache sharing test**

In `test_history_cache.py`, add:

```python
def test_realtime_and_dayahead_history_share_excel_file_signature_cache(tmp_path) -> None:
    from dayahead_core import history_cache_signature

    history_dir = tmp_path / "history"
    history_dir.mkdir()
    file_path = history_dir / "2026年5月.xlsx"
    file_path.write_bytes(b"fake")

    day = history_cache_signature(history_dir, data_mode="dayahead")
    realtime = history_cache_signature(history_dir, data_mode="realtime")

    assert day["excel_files"] == realtime["excel_files"]
    assert day["history_data_mode"] == "dayahead"
    assert realtime["history_data_mode"] == "realtime"
```

- [ ] **Step 2: Run test**

Run:

```powershell
python -m unittest test.test_history_cache
```

Expected: fail only if signature helper is not exposed or does not separate shared file signature from data mode.

- [ ] **Step 3: Extract shared Excel file signature**

In `dayahead_core.py`, add:

```python
def excel_file_signature(history_dir: str | Path, start_date: pd.Timestamp | None = None, end_date: pd.Timestamp | None = None) -> list[dict[str, object]]:
    files = list_excel_files_for_date_window(Path(history_dir), start_date, end_date)
    return [
        {"path": str(path), "mtime_ns": path.stat().st_mtime_ns, "size": path.stat().st_size}
        for path in files
    ]
```

Use this inside existing history cache signature so day-ahead and realtime share file scans but keep separate processed cache names.

- [ ] **Step 4: Add config fingerprint helper**

In `dayahead_core.py`:

```python
def training_run_fingerprint(config: TrainConfig, history_signature: dict[str, object]) -> str:
    payload = {
        "history": history_signature,
        "data_mode": config.data_mode,
        "training_window_days": config.training_window_days,
        "valid_days": config.valid_days,
        "num_boost_round": config.num_boost_round,
        "segment_config": config.segment_config,
        "price_intervals": config.price_intervals,
        "train_capacity_model": config.train_capacity_model,
    }
    raw = json.dumps(json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

- [ ] **Step 5: Use skip guard**

Before training a target, compare the new fingerprint to current metadata:

```python
if not force and metadata.get("training_run_fingerprint") == next_fingerprint:
    return {"skipped": True, "reason": "training_input_unchanged", "metadata": metadata}
```

Default `force=True` for manual explicit buttons; use `force=False` only for scheduled or explicit "skip unchanged" paths.

- [ ] **Step 6: Run cache tests**

Run:

```powershell
python -m unittest test.test_history_cache test.test_realtime_price_model
python -m py_compile dayahead_core.py api_server.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add dayahead_core.py api_server.py test/test_history_cache.py test/test_realtime_price_model.py
git commit -m "perf: share history signatures and skip unchanged training"
```

---

## Task 13: Add Rolling Backtest Cache

**Files:**
- Modify: `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_core.py`
- Test: `D:\每日工作\代码示例\预测程序-------\demo1\test\test_window_optimization_segments.py`

- [ ] **Step 1: Write failing cache key test**

Add:

```python
def test_rolling_backtest_cache_key_includes_target_and_horizon() -> None:
    from dayahead_core import rolling_backtest_cache_key

    day = rolling_backtest_cache_key("dayahead", "run_a", 30, {"window": 100})
    realtime = rolling_backtest_cache_key("realtime", "run_a", 30, {"window": 100})
    fourteen = rolling_backtest_cache_key("dayahead", "run_a", 14, {"window": 100})

    assert day != realtime
    assert day != fourteen
```

- [ ] **Step 2: Run test**

Run:

```powershell
python -m unittest test.test_window_optimization_segments
```

Expected: failure because helper is missing.

- [ ] **Step 3: Implement cache key and read/write helpers**

In `dayahead_core.py`:

```python
def rolling_backtest_cache_key(target: str, run_id: str, horizon: int, config_payload: dict[str, object]) -> str:
    payload = {"target": target, "run_id": run_id, "horizon": int(horizon), "config": config_payload}
    raw = json.dumps(json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def rolling_backtest_cache_path(model_root: str | Path, cache_key: str) -> Path:
    return Path(model_root) / "cache" / "rolling_backtest" / f"{cache_key}.json"
```

- [ ] **Step 4: Use cache in rolling backtest calculation**

Before computing a horizon:

```python
cache_key = rolling_backtest_cache_key(target, run_id, horizon, config_payload)
path = rolling_backtest_cache_path(model_root, cache_key)
if path.exists():
    return json.loads(path.read_text(encoding="utf-8"))
```

After computing:

```python
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(json_safe(metrics), ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest test.test_window_optimization_segments test.test_realtime_price_model
python -m py_compile dayahead_core.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add dayahead_core.py test/test_window_optimization_segments.py
git commit -m "perf: cache rolling backtest metrics"
```

---

## Task 14: Final Verification and Manual Smoke Test

**Files:**
- Verify all modified files.
- No new production code unless a verification failure exposes a defect.

- [ ] **Step 1: Run Python regression suite for touched areas**

Run:

```powershell
python -m unittest test.test_realtime_price_model test.test_dual_model_training_control test.test_prediction_archive test.test_window_optimization_segments test.test_model_versions test.test_api_server_defaults test.test_history_cache
```

Expected: `OK`.

- [ ] **Step 2: Run frontend checks**

Run:

```powershell
node test/test_frontend_dual_model_controls.js
node test/test_frontend_archive_review.js
node test/test_frontend_realtime_archive_review.js
node test/test_frontend_realtime_prediction_chart.js
node test/test_frontend_progress_state.js
node --check frontend_app/assets/app.js
```

Expected: all scripts pass and `node --check` exits 0.

- [ ] **Step 3: Compile backend**

Run:

```powershell
python -m py_compile dayahead_core.py api_server.py prediction_archive.py
```

Expected: exit 0.

- [ ] **Step 4: Start local server**

Run:

```powershell
python api_server.py
```

Expected: server starts on `http://127.0.0.1:8000`.

- [ ] **Step 5: Verify static asset contains new controls**

Run:

```powershell
curl.exe -s http://127.0.0.1:8000/assets/app.js | Select-String -Pattern "startDualWindowOptimization|realtime_model_version_key|loadRealtimeModelVersions"
```

Expected: all three tokens are present.

- [ ] **Step 6: Verify API status**

Run:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/status" | ConvertTo-Json -Depth 5
```

Expected: response includes both `current_model` and `current_realtime_model`.

- [ ] **Step 7: Manual browser smoke**

Open `http://127.0.0.1:8000`.

Check:

- Training center shows model training total-control.
- Day-ahead and realtime training sections both exist.
- Prediction page shows day-ahead and realtime version selectors.
- Model versions page can switch between day-ahead and realtime models.
- Archive review displays realtime curve and metrics when archive rows include realtime prediction and realtime actual prices.

- [ ] **Step 8: Commit verification fixes if any**

Only if fixes were needed:

```powershell
git add <fixed-files>
git commit -m "fix: address dual model formalization verification issues"
```

---

## Plan Coverage Self-Review

- Spec: realtime and day-ahead independent maintenance.
  - Covered by Tasks 1, 2, 5, 6, 8, and 10.
- Spec: realtime supports automatic optimization, manual training, parameters, segment selection, interval model, and rolling backtest.
  - Covered by Tasks 2, 3, 4, 5, 9, 12, and 13.
- Spec: realtime does not train capacity model.
  - Covered by Task 1 and Task 3.
- Spec: prediction page uses two independent version selectors.
  - Covered by Task 8.
- Spec: output file keeps day-ahead main column and realtime independent column.
  - Covered by Task 6 and Task 7.
- Spec: archive review uses actual day-ahead price and actual realtime price separately.
  - Covered by Task 11 and the already-existing archive tests.
- Spec: total-control runs day-ahead then realtime, with failure isolation.
  - Covered by Task 4 and Task 9.
- Spec: diagnostics move to model versions page.
  - Covered by Task 10.
- Spec: speed optimization without sacrificing accuracy.
  - Covered by Task 12 and Task 13.
