const assert = require("node:assert/strict");

const {
  reconcileJobStatesWithStatus,
  deriveDualOptimizationState,
} = require("../frontend_app/assets/progress_state.js");

const appState = {
  activeJobIds: {
    optimize: "stale-job-id",
    "realtime-optimize": "stale-realtime-job-id",
    train: null,
    predict: null,
    "predict-multi-day": null,
  },
  jobStates: {
    optimize: {
      job_id: "stale-job-id",
      job_type: "optimize",
      progress: 31,
      status: "6段 rerank 完整复核 4/9：最近 75 天",
      running: true,
    },
    "realtime-optimize": {
      job_id: "stale-realtime-job-id",
      job_type: "realtime_optimize",
      progress: 42,
      status: "实时价格模型寻优中",
      running: true,
    },
    train: null,
    predict: null,
    "predict-multi-day": null,
  },
  statusFocus: "optimize",
  pendingStatus: null,
};

reconcileJobStatesWithStatus(appState, {
  current_job: null,
  window_optimization: {
    last_attempt_status: "success",
    last_attempt_finished_at: "2026-05-22 16:23:28",
    price_model_config: { training_window_days: 71 },
    final_model: { run_id: "run_20260522_162101" },
  },
  realtime_window_optimization: {
    last_attempt_status: "success",
    last_attempt_finished_at: "2026-05-22 16:30:28",
    price_model_config: { training_window_days: 68 },
    final_model: { run_id: "run_20260522_163028" },
  },
});

assert.equal(appState.activeJobIds.optimize, null);
assert.equal(appState.statusFocus, null);
assert.deepEqual(appState.jobStates.optimize, {
  job_type: "optimize",
  progress: 100,
  status: "自动寻优已完成：最优训练窗口 71 天，默认模型 run_20260522_162101",
  running: false,
});
assert.equal(appState.activeJobIds["realtime-optimize"], null);
assert.deepEqual(appState.jobStates["realtime-optimize"], {
  job_type: "realtime_optimize",
  progress: 100,
  status: "实时价格模型寻优已完成：最优训练窗口 68 天，默认模型 run_20260522_163028",
  running: false,
});

const partial = deriveDualOptimizationState({
  status: "partial_success",
  targets: {
    dayahead: { status: "success" },
    realtime: { status: "failed", error: "missing realtime price" },
  },
});
assert.equal(partial.type, "warning");
assert.match(partial.status, /部分成功/);

console.log("frontend progress state helpers passed");
