(function (root, factory) {
  const helpers = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = helpers;
  }
  if (root) {
    root.progressStateHelpers = helpers;
  }
})(typeof window !== "undefined" ? window : globalThis, function () {
  const jobModes = ["train", "predict", "optimize", "realtime-optimize", "dual-optimize", "predict-multi-day"];

  function completedOptimizationStatus(windowState = {}, label = "自动寻优") {
    const windowDays = windowState.price_model_config?.training_window_days
      || windowState.best_window_days
      || windowState.best?.window_days;
    const modelRunId = windowState.final_model?.run_id;
    const details = [];
    if (windowDays) details.push(`最优训练窗口 ${windowDays} 天`);
    if (modelRunId) details.push(`默认模型 ${modelRunId}`);
    return details.length ? `${label}已完成：${details.join("，")}` : `${label}已完成`;
  }

  function reconcileCompletedOptimization(appState, mode, jobType, windowState, activeMode, label) {
    if (windowState.last_attempt_status !== "success" || activeMode === jobType) return;
    appState.activeJobIds[mode] = null;
    appState.jobStates[mode] = {
      job_type: jobType,
      progress: 100,
      status: completedOptimizationStatus(windowState, label),
      running: false,
    };
    if (appState.statusFocus === mode) {
      appState.statusFocus = null;
    }
    if (appState.pendingStatus?.job_type === jobType) {
      appState.pendingStatus = null;
    }
  }

  function reconcileJobStatesWithStatus(appState, statusData = {}) {
    if (!appState) return appState;
    appState.activeJobIds = appState.activeJobIds || {};
    appState.jobStates = appState.jobStates || {};

    const activeJob = statusData.current_job || null;
    const activeMode = activeJob?.job_type;
    for (const mode of jobModes) {
      if (activeMode === mode) continue;
      if (appState.activeJobIds[mode] && !appState.jobStates[mode]?.running) {
        appState.activeJobIds[mode] = null;
      }
    }

    reconcileCompletedOptimization(
      appState,
      "optimize",
      "optimize",
      statusData.window_optimization || {},
      activeMode,
      "自动寻优",
    );
    reconcileCompletedOptimization(
      appState,
      "realtime-optimize",
      "realtime_optimize",
      statusData.realtime_window_optimization || {},
      activeMode,
      "实时价格模型寻优",
    );
    return appState;
  }

  function deriveDualOptimizationState(result) {
    if (!result) return { progress: 0, label: "未开始", status: "等待一键训练两套模型", type: "idle" };
    if (result.status === "success") {
      return { progress: 100, label: "已完成", status: "两套模型训练完成", type: "success" };
    }
    if (result.status === "partial_success") {
      return { progress: 100, label: "部分成功", status: "部分成功：一套模型成功，一套模型失败，详情见任务日志", type: "warning" };
    }
    if (result.status === "failed") {
      return { progress: 100, label: "失败", status: "两套模型都失败，详情见任务日志", type: "error" };
    }
    return {
      progress: Number.isFinite(Number(result.progress)) ? Number(result.progress) : 0,
      label: "运行中",
      status: result.status || "一键训练两套模型运行中",
      type: "running",
    };
  }

  return {
    completedOptimizationStatus,
    deriveDualOptimizationState,
    reconcileJobStatesWithStatus,
  };
});
