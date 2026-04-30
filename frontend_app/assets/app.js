const App = {
  config: null,
  versions: [],
  templateRows: [],
  pollTimer: null,
  chart: null,
  pendingStatus: null,
  datePickers: {},
  tickerTimer: null,
  tickerMessages: [],
  tickerIndex: 0,
  tickerLoop: false,
  activeJobIds: {
    train: null,
    predict: null,
  },
  jobStates: {
    train: null,
    predict: null,
  },
  statusFocus: null,
  predictSessionStarted: false,
  lastPrediction: null,
  predictionViewDirty: false,
  predictionChartSignature: null,
};

const columnTitleMap = {
  date: "日期",
  period: "时段",
  segment: "分时段",
  hour: "小时",
  net_load: "净负荷",
  thermal_on_capacity: "火电开机容量(MW)",
  lag_96: "昨日同点日前价格",
  similar_price: "相似法基线价格",
  residual_pred: "模型残差修正值",
  predicted_price: "预测价格",
};

const segmentNameMap = {
  night: "夜间",
  morning_peak: "早高峰",
  midday: "午间",
  evening_peak: "晚高峰",
  late_night: "深夜",
};

const referenceStrategyLabelMap = {
  recent_n_days: "最近 N 天",
  recent_same_type_days: "最近 N 个同类型日",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `请求失败：${response.status}`);
  }
  return data;
}

function htmlEscape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showToast(message, type = "success") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  $("#toast-stack").appendChild(node);
  setTimeout(() => {
    node.style.opacity = "0";
    node.style.transform = "translateY(-8px)";
  }, 2400);
  setTimeout(() => node.remove(), 3000);
}

function setActiveTab(name) {
  $$(".tab-btn").forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === name));
  $$(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${name}`));
  if (name === "predict") {
    requestAnimationFrame(() => {
      if (App.chart) {
        App.chart.resize();
      }
    });
  }
  if (name === "logs") {
    loadLogs().catch((error) => {
      console.error(error);
      showToast(error.message, "error");
    });
  }
}

function renderTopStatus(statusData) {
  const activeJob = getFocusedJobState();
  const items = [
    `当前模型：${statusData.current_model?.run_id || "-"}`,
    `运行状态：${activeJob?.status || "系统待命"}`,
  ];
  $("#top-status").innerHTML = items
    .map((item) => `<div class="status-chip"><span class="status-chip-dot"></span>${htmlEscape(item)}</div>`)
    .join("");
}

function renderConfigPaths() {
}

function renderModelSummary(versions, metadata) {
  $("#current-model-id").textContent = metadata?.run_id || "-";
  $("#current-model-range").textContent = metadata?.train_start_date ? `${metadata.train_start_date} ~ ${metadata.train_end_date}` : "-";
}

function renderMetrics(metrics = {}) {
  const tbody = $("#metrics-table tbody");
  const rows = Object.entries(metrics);
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="7">暂无指标数据</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(
      ([key, row]) => `
        <tr>
          <td>${htmlEscape(segmentNameMap[key] || key)}</td>
          <td>${row.baseline_mae ?? "-"}</td>
          <td>${row.baseline_rmse ?? "-"}</td>
          <td>${row.final_mae ?? "-"}</td>
          <td>${row.final_rmse ?? "-"}</td>
          <td>${row.train_rows ?? "-"}</td>
          <td>${row.valid_rows ?? "-"}</td>
        </tr>
      `,
    )
    .join("");
}

function syncSelectAllVersionsState() {
  const selectAll = $("#select-all-versions");
  if (!selectAll) return;
  const checks = $$(".version-check");
  const checkedCount = checks.filter((item) => item.checked).length;
  selectAll.checked = checks.length > 0 && checkedCount === checks.length;
  selectAll.indeterminate = checkedCount > 0 && checkedCount < checks.length;
}

function renderVersions(versions) {
  const selectedKeys = new Set(selectedVersionKeys());
  const currentVersionKey = $("#version-select")?.value || "";
  App.versions = versions;
  $("#version-select").innerHTML = versions.length
    ? versions.map((item) => `<option value="${htmlEscape(item.version_key)}">${htmlEscape(item.label || item.version_key)}</option>`).join("")
    : `<option value="">暂无历史模型</option>`;
  if (versions.some((item) => String(item.version_key) === currentVersionKey)) {
    $("#version-select").value = currentVersionKey;
  }

  const tbody = $("#versions-table tbody");
  if (!versions.length) {
    tbody.innerHTML = `<tr><td colspan="6">暂无历史模型版本</td></tr>`;
    syncSelectAllVersionsState();
    return;
  }
  tbody.innerHTML = versions
    .map((item) => {
      const tags = [];
      if (item.is_default) tags.push(`<span class="status-tag default">默认模型</span>`);
      if (item.is_previous) tags.push(`<span class="status-tag previous">上一版</span>`);
      const checked = selectedKeys.has(String(item.version_key)) ? " checked" : "";
      return `
        <tr>
          <td><input type="checkbox" class="version-check" value="${htmlEscape(item.version_key)}"${checked}></td>
          <td>${htmlEscape(item.version_key)}</td>
          <td>${htmlEscape(item.created_at || "-")}</td>
          <td>${htmlEscape(item.train_start_date || "-")} ~ ${htmlEscape(item.train_end_date || "-")}</td>
          <td>${htmlEscape(item.sample_rows ?? "-")}</td>
          <td>${tags.join(" ") || "-"}</td>
        </tr>
      `;
    })
    .join("");
  syncSelectAllVersionsState();
}

function renderTrainingLogs(logs) {
  const tbody = $("#training-logs-table tbody");
  $("#training-logs-meta").textContent = `共 ${logs.length} 条正式训练记录`;
  if (!logs.length) {
    tbody.innerHTML = `<tr><td colspan="5">暂无训练日志</td></tr>`;
    $("#training-logs-meta").textContent = "暂无训练日志";
    return;
  }
  tbody.innerHTML = logs
    .map(
      (item) => `
        <tr>
          <td>${htmlEscape(item.run_id || "-")}</td>
          <td>${htmlEscape(item.created_at || "-")}</td>
          <td>${htmlEscape(item.train_start_date || "-")}</td>
          <td>${htmlEscape(item.train_end_date || "-")}</td>
          <td>${htmlEscape(item.sample_rows ?? "-")}</td>
        </tr>
      `,
    )
    .join("");
}

function stopTickerLoop() {
  if (App.tickerTimer) {
    clearInterval(App.tickerTimer);
    App.tickerTimer = null;
  }
}

function setStatusTickerText(message, animate = false) {
  const textNode = $("#status-fab-text");
  textNode.textContent = message;
  textNode.classList.remove("animate");
  if (!animate) return;
  void textNode.offsetWidth;
  textNode.classList.add("animate");
}

function isSameTickerMessages(messages) {
  return messages.length === App.tickerMessages.length && messages.every((item, index) => item === App.tickerMessages[index]);
}

function updateStatusTicker(messages, loop = false) {
  const safeMessages = messages?.filter(Boolean) || ["系统待命，点击展开查看详细运行过程"];
  const sameMessages = isSameTickerMessages(safeMessages);
  const sameLoop = App.tickerLoop === loop;
  if (sameMessages && sameLoop) {
    if (loop && safeMessages.length > 1) {
      if (!App.tickerTimer) ensureTickerLoop();
    } else {
      stopTickerLoop();
      setStatusTickerText(safeMessages[0], false);
    }
    return;
  }
  stopTickerLoop();
  App.tickerMessages = safeMessages;
  App.tickerLoop = loop;
  App.tickerIndex = 0;
  setStatusTickerText(safeMessages[0], loop && safeMessages.length > 1);
  if (loop && safeMessages.length > 1) {
    ensureTickerLoop();
  }
}

function ensureTickerLoop() {
  stopTickerLoop();
  App.tickerTimer = setInterval(() => {
    if (!App.tickerMessages.length) return;
    App.tickerIndex = (App.tickerIndex + 1) % App.tickerMessages.length;
    setStatusTickerText(App.tickerMessages[App.tickerIndex], true);
  }, 1800);
}

function renderTemplate(columns, rows, metaText) {
  App.templateRows = rows;
  $("#template-meta").textContent = metaText;
  const head = `<thead><tr>${columns.map((col) => `<th>${htmlEscape(col)}</th>`).join("")}</tr></thead>`;
  const body = rows
    .map(
      (row) => `
        <tr>
          ${columns.map((col) => `<td contenteditable="true" data-col="${htmlEscape(col)}">${htmlEscape(row[col] ?? "")}</td>`).join("")}
        </tr>
      `,
    )
    .join("");
  $("#template-table").innerHTML = `${head}<tbody>${body}</tbody>`;
}

function collectTemplateRows() {
  return $$("#template-table tbody tr").map((tr) => {
    const row = {};
    tr.querySelectorAll("td").forEach((td) => {
      row[td.dataset.col] = td.textContent.trim();
    });
    return row;
  });
}

function comparisonPredictions(prediction) {
  if (!prediction) return {};
  return prediction.comparison_predictions || {
    [prediction.reference_strategy_key || "recent_n_days"]: prediction,
  };
}

function currentReferenceDays() {
  const value = Number($("#reference-days")?.value || App.config?.default_reference_days || 1);
  return Number.isFinite(value) && value >= 1 ? value : 1;
}

function formatReferenceStrategyLabel(strategyKey, label, referenceDays = currentReferenceDays()) {
  const baseLabel = label || referenceStrategyLabelMap[strategyKey] || strategyKey || "-";
  return String(baseLabel).replace(/\s*N\s*/g, ` ${referenceDays} `).replace(/\s+/g, " ").trim();
}

function syncReferenceStrategyLabels(referenceDays = currentReferenceDays()) {
  const options = App.config?.reference_strategy_options || [];
  ["#prediction-output-strategy", "#prediction-view-strategy"].forEach((selector) => {
    const select = $(selector);
    if (!select) return;
    Array.from(select.options).forEach((option) => {
      const configOption = options.find((item) => item.key === option.value);
      option.textContent = formatReferenceStrategyLabel(option.value, configOption?.label || referenceStrategyLabelMap[option.value], referenceDays);
    });
  });
}

function activePredictionVariant(prediction) {
  if (!prediction) return null;
  const comparisons = comparisonPredictions(prediction);
  const viewKey = $("#prediction-view-strategy")?.value || prediction.selected_strategy_key || prediction.reference_strategy_key;
  return comparisons[viewKey] || comparisons[prediction.selected_strategy_key] || Object.values(comparisons)[0] || prediction;
}

function syncPredictionStrategySelectors(prediction) {
  const outputSelect = $("#prediction-output-strategy");
  const viewSelect = $("#prediction-view-strategy");
  if (!outputSelect || !viewSelect || !prediction) return;
  const selectedKey = prediction.selected_strategy_key || prediction.reference_strategy_key || "recent_n_days";
  syncReferenceStrategyLabels();
  if (prediction.selected_strategy_key) {
    outputSelect.value = selectedKey;
  }
  const comparisons = comparisonPredictions(prediction);
  const keys = Object.keys(comparisons);
  if (keys.length && (!App.predictionViewDirty || !keys.includes(viewSelect.value))) {
    viewSelect.value = selectedKey || keys[0];
  }
}

function renderComparisonCards(prediction) {
  const container = $("#comparison-cards");
  if (!container) return;
  const comparisons = comparisonPredictions(prediction);
  const keys = Object.keys(comparisons);
  if (!keys.length) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = keys
    .map((key) => {
      const item = comparisons[key];
      const values = item.rows.map((row) => Number(row.predicted_price || 0));
      const avgValue = values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length);
      const minValue = Math.min(...values);
      const maxValue = Math.max(...values);
      const activeClass = ($("#prediction-view-strategy")?.value || prediction.selected_strategy_key) === key ? " active-strategy-card" : "";
      const strategyLabel = formatReferenceStrategyLabel(key, item.reference_strategy_label, item.reference_days_requested || prediction.reference_days_requested);
      return `
        <article class="info-card${activeClass}">
          <div class="card-title">${htmlEscape(strategyLabel)}</div>
          <div class="card-value">${avgValue.toFixed(2)}</div>
          <div class="card-desc">最低 ${minValue.toFixed(2)} | 最高 ${maxValue.toFixed(2)}</div>
          <div class="card-desc">参考日期：${htmlEscape((item.reference_dates || []).join(" / ") || "-")}</div>
        </article>
      `;
    })
    .join("");
}

function renderPredictionBundle(prediction) {
  App.lastPrediction = prediction;
  syncPredictionStrategySelectors(prediction);
  renderComparisonCards(prediction);
  renderPredictionTable(prediction);
  renderPredictionChart(prediction);
}

function predictionVariantSignature(variant) {
  if (!variant) return "";
  return JSON.stringify({
    strategy: variant.reference_strategy_key || "",
    forecastDate: variant.forecast_date || "",
    referenceDays: variant.reference_days_requested || "",
    referenceDates: variant.reference_dates || [],
    rows: variant.rows || [],
  });
}

function renderPredictionTable(prediction) {
  const table = $("#prediction-table");
  const variant = activePredictionVariant(prediction);
  if (!variant || !variant.rows?.length) {
    table.innerHTML = `<thead><tr><th>字段</th></tr></thead><tbody><tr><td>暂无预测数据</td></tr></tbody>`;
    return;
  }
  const columns = variant.columns || Object.keys(variant.rows[0]);
  const head = `<thead><tr>${columns.map((col) => `<th>${htmlEscape(columnTitleMap[col] || col)}</th>`).join("")}</tr></thead>`;
  const body = variant.rows
    .map(
      (row) => `
        <tr>
          ${columns.map((col) => `<td>${htmlEscape(row[col] ?? "")}</td>`).join("")}
        </tr>
      `,
    )
    .join("");
  table.innerHTML = `${head}<tbody>${body}</tbody>`;
}

function ensureChart() {
  if (!window.echarts) return null;
  if (!App.chart) {
    App.chart = window.echarts.init($("#prediction-chart"));
    window.addEventListener("resize", () => {
      if (App.chart) App.chart.resize();
    });
  }
  return App.chart;
}

function renderPredictionStats(prediction) {
  const target = $("#prediction-stats");
  const variant = activePredictionVariant(prediction);
  if (!variant || !variant.rows?.length) {
    target.innerHTML = "";
    return;
  }

  const values = variant.rows.map((row) => Number(row.predicted_price || 0));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const avgValue = values.reduce((sum, item) => sum + item, 0) / Math.max(1, values.length);
  const referenceDates = variant.reference_dates || [];
  const referenceLabel = referenceDates.length ? referenceDates.join(" / ") : "-";
  target.innerHTML = [
    `最低价：${minValue.toFixed(2)}`,
    `最高价：${maxValue.toFixed(2)}`,
    `均价：${avgValue.toFixed(2)}`,
    `参考日：${referenceLabel}`,
  ].map((text) => `<span class="chart-stat">${text}</span>`).join("");
}

function renderPredictionChart(prediction) {
  renderPredictionStats(prediction);
  const chart = ensureChart();
  if (!chart) return;

  const variant = activePredictionVariant(prediction);
  if (!variant || !variant.rows?.length) {
    if (App.predictionChartSignature !== "") {
      chart.clear();
      App.predictionChartSignature = "";
    }
    $("#prediction-meta").textContent = "暂无预测数据";
    return;
  }

  const rows = variant.rows;
  const periods = rows.map((row) => row.period);
  const predicted = rows.map((row) => Number(row.predicted_price || 0));
  const similar = rows.map((row) => Number(row.similar_price || 0));
  const lag96 = rows.map((row) => Number(row.lag_96 || 0));
  const residual = rows.map((row) => Number(row.residual_pred || 0));
  const forecastDate = variant.forecast_date || rows[0]?.date || "-";
  const referenceDays = variant.reference_days_requested || (variant.reference_dates || []).length || 1;
  const strategyLabel = formatReferenceStrategyLabel(variant.reference_strategy_key, variant.reference_strategy_label, referenceDays);
  const chartSignature = predictionVariantSignature(variant);

  if (App.predictionChartSignature !== chartSignature) {
    chart.setOption(
      {
        backgroundColor: "transparent",
        animationDuration: 500,
        color: ["#1677ff", "#52c41a", "#722ed1", "#faad14"],
        tooltip: {
          trigger: "axis",
          triggerOn: "mousemove|click",
          axisPointer: { type: "cross" },
          backgroundColor: "rgba(17,24,39,0.92)",
          borderWidth: 0,
          confine: true,
          hideDelay: 120,
          textStyle: { color: "#ffffff" },
        },
        legend: {
          top: 12,
          textStyle: { color: "#4e5969" },
          data: ["最终预测价格", "相似法基线", "lag_96 前日价格", "残差修正值"],
        },
        grid: [
          { left: 54, right: 36, top: 54, height: 230 },
          { left: 54, right: 36, top: 308, height: 72 },
        ],
        xAxis: [
          {
            type: "category",
            boundaryGap: false,
            data: periods,
            axisLabel: { color: "#86909c" },
            axisLine: { lineStyle: { color: "#d9d9d9" } },
          },
          {
            type: "category",
            gridIndex: 1,
            boundaryGap: false,
            data: periods,
            axisLabel: { color: "#86909c" },
            axisLine: { lineStyle: { color: "#d9d9d9" } },
          },
        ],
        yAxis: [
          {
            type: "value",
            name: "Price",
            min: 0,
            max: 1500,
            axisLabel: { color: "#86909c" },
            splitLine: { lineStyle: { color: "rgba(5,5,5,0.06)" } },
          },
          {
            type: "value",
            gridIndex: 1,
            name: "Residual",
            axisLabel: { color: "#86909c" },
            splitLine: { show: false },
          },
        ],
        dataZoom: [
          { type: "inside", xAxisIndex: [0, 1], start: 0, end: 100 },
          { type: "slider", xAxisIndex: [0, 1], bottom: 0, height: 18, borderColor: "transparent" },
        ],
        series: [
          {
            name: "最终预测价格",
            type: "line",
            smooth: true,
            symbol: "circle",
            symbolSize: 6,
            areaStyle: { color: "rgba(22,119,255,0.10)" },
            data: predicted,
          },
          {
            name: "相似法基线",
            type: "line",
            smooth: true,
            symbol: "none",
            lineStyle: { width: 2, type: "dashed" },
            data: similar,
          },
          {
            name: "lag_96 前日价格",
            type: "line",
            smooth: true,
            symbol: "none",
            lineStyle: { width: 2 },
            data: lag96,
          },
          {
            name: "残差修正值",
            type: "bar",
            xAxisIndex: 1,
            yAxisIndex: 1,
            barMaxWidth: 10,
            data: residual,
          },
        ],
      },
      true,
    );
    App.predictionChartSignature = chartSignature;
    requestAnimationFrame(() => {
      chart.resize();
    });
  }

  $("#prediction-meta").textContent = `策略：${strategyLabel} | 预测日期：${forecastDate} | 参考天数：${referenceDays} 天`;
}

function applyProgressCard(key, state) {
  const card = $(`#${key}-progress-card`);
  const text = $(`#${key}-progress-text`);
  const status = $(`#${key}-progress-status`);
  const fill = $(`#${key}-progress-fill`);
  const progress = Math.max(0, Math.min(100, Number(state.progress || 0)));
  fill.style.width = `${progress}%`;
  text.textContent = state.label || `${progress}%`;
  status.textContent = state.status || "等待中";
  card.classList.remove("running", "success", "error");
  if (state.type) card.classList.add(state.type);
}

function deriveJobState(job, mode) {
  const idleText = mode === "train" ? "等待手动重训" : "等待执行预测";
  if (!job) {
    return { progress: 0, label: "未开始", status: idleText, type: "" };
  }
  if (job.error) {
    return { progress: Math.max(1, Number(job.progress || 0)), label: "执行失败", status: job.error.split("\n")[0], type: "error" };
  }
  if (job.running) {
    return { progress: Number(job.progress || 0), label: `${job.progress || 0}%`, status: job.status || "执行中", type: "running" };
  }
  return { progress: 100, label: "已完成", status: job.status || "执行完成", type: "success" };
}

function getFocusedJobState() {
  if (App.statusFocus && App.jobStates[App.statusFocus]) {
    return App.jobStates[App.statusFocus];
  }
  if (App.pendingStatus) {
    return App.pendingStatus;
  }
  return null;
}

function renderProgressSections() {
  applyProgressCard("train", deriveJobState(App.jobStates.train, "train"));
  applyProgressCard("predict", deriveJobState(App.jobStates.predict, "predict"));
}

function setPendingState(mode, title) {
  const key = mode === "train" ? "train" : "predict";
  App.statusFocus = key;
  applyProgressCard(key, {
    progress: 3,
    label: "提交中",
    status: title,
    type: "running",
  });
  App.pendingStatus = {
    job_type: key,
    progress: 3,
    status: title,
    logs: [`[本地] ${title}`],
    running: true,
  };
  renderStatusPanel({ current_job: App.pendingStatus, recent_jobs: [] });
}

function renderStatusPanel(statusData) {
  const currentJob = getFocusedJobState();
  const text = currentJob?.status || "系统待命";
  $("#status-current").textContent = text;
  $("#status-progress-fill").style.width = `${Math.max(0, Math.min(100, Number(currentJob?.progress || 0)))}%`;
  const logs = currentJob?.logs?.length ? currentJob.logs : ["暂无运行日志"];
  $("#log-console").textContent = logs.join("\n");
  if (!currentJob) {
    updateStatusTicker(["系统待命，点击展开查看详细运行过程"], false);
    return;
  }
  if (currentJob.running) {
    updateStatusTicker([...logs].reverse().slice(0, 8), true);
  } else {
    updateStatusTicker([logs[logs.length - 1] || currentJob.status || "执行完成"], false);
  }
}

async function refreshTrackedJobs() {
  const modes = ["train", "predict"];
  const requests = modes.map(async (mode) => {
    const jobId = App.activeJobIds[mode];
    if (!jobId) return;
    try {
      const job = await request(`/api/jobs/${jobId}`);
      App.jobStates[mode] = job;
      if (job && !job.running) {
        App.activeJobIds[mode] = null;
      }
      if (App.pendingStatus && App.statusFocus === mode) {
        App.pendingStatus = null;
      }
    } catch (error) {
      console.error(error);
      App.activeJobIds[mode] = null;
    }
  });
  await Promise.allSettled(requests);
}

function resetSessionProgress() {
  App.pendingStatus = null;
  App.activeJobIds = { train: null, predict: null };
  App.jobStates = { train: null, predict: null };
  App.statusFocus = null;
  App.predictSessionStarted = false;
  App.predictionViewDirty = false;
  renderProgressSections();
  renderStatusPanel({});
  renderPredictionBundle(null);
}

async function loadConfig() {
  App.config = await request("/api/config");
  if ($("#reference-days") && App.config?.default_reference_days && !$("#reference-days").value) {
    $("#reference-days").value = App.config.default_reference_days;
  }
  syncReferenceStrategyLabels();
  renderConfigPaths();
}

async function refreshSummary() {
  const [statusData, currentModel, versionsData] = await Promise.all([
    request("/api/status"),
    request("/api/model/current"),
    request("/api/model/versions"),
  ]);
  await refreshTrackedJobs();
  renderTopStatus(statusData);
  renderStatusPanel(statusData);
  renderProgressSections();
  renderVersions(versionsData.versions || []);
  renderModelSummary(versionsData.versions || [], currentModel.metadata || {});
  renderMetrics(currentModel.metadata?.metrics || {});
  if (App.predictSessionStarted && statusData.last_prediction?.rows?.length) {
    renderPredictionBundle(statusData.last_prediction);
  }
}

async function loadLogs() {
  const data = await request("/api/training/logs");
  renderTrainingLogs(data.logs || []);
}

async function loadTemplate() {
  const data = await request("/api/forecast/template");
  renderTemplate(data.columns || [], data.rows || [], `${data.sheet_name} · 共 ${data.row_count || 0} 行`);
}

async function saveTemplate() {
  await request("/api/forecast/template/save", {
    method: "POST",
    body: JSON.stringify({ rows: collectTemplateRows() }),
  });
  showToast("预测文件已保存");
}

async function startTrain() {
  const btn = $("#train-btn");
  const originalText = btn.textContent;
  try {
    setButtonLoading(btn, true, originalText);
    setPendingState("train", "正在提交训练任务...");
    const data = await request("/api/train", {
      method: "POST",
      body: JSON.stringify({
        start_date: $("#train-start-date").value || null,
        end_date: $("#train-end-date").value || null,
        enable_start: $("#enable-start").checked,
        enable_end: $("#enable-end").checked,
        valid_days: Number($("#valid-days").value || 14),
        num_boost_round: Number($("#num-boost-round").value || 400),
      }),
    });
    App.activeJobIds.train = data.job_id;
    App.jobStates.train = {
      job_id: data.job_id,
      job_type: "train",
      progress: 5,
      status: `训练任务已启动：${data.job_id}`,
      logs: [`[本地] 训练任务已启动：${data.job_id}`],
      running: true,
    };
    applyProgressCard("train", { progress: 5, label: "已启动", status: `训练任务已启动：${data.job_id}`, type: "running" });
    showToast(`已启动训练任务：${data.job_id}`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonLoading(btn, false, originalText);
  }
}

async function startPredict() {
  const btn = $("#predict-btn");
  const originalText = btn.textContent;
  try {
    setButtonLoading(btn, true, originalText);
    App.predictSessionStarted = true;
    App.predictionViewDirty = false;
    setPendingState("predict", "正在保存并提交预测任务...");
    await saveTemplate();
    const data = await request("/api/predict", {
      method: "POST",
      body: JSON.stringify({
        reference_days: Number($("#reference-days").value || App.config?.default_reference_days || 1),
        selected_strategy: $("#prediction-output-strategy").value || App.config?.default_reference_strategy || "recent_n_days",
      }),
    });
    App.activeJobIds.predict = data.job_id;
    App.jobStates.predict = {
      job_id: data.job_id,
      job_type: "predict",
      progress: 5,
      status: `预测任务已启动：${data.job_id}`,
      logs: [`[本地] 预测任务已启动：${data.job_id}`],
      running: true,
    };
    applyProgressCard("predict", { progress: 5, label: "已启动", status: `预测任务已启动：${data.job_id}`, type: "running" });
    showToast(`已启动预测任务：${data.job_id}`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonLoading(btn, false, originalText);
  }
}

async function activateVersion() {
  const versionKey = $("#version-select").value;
  if (!versionKey) {
    showToast("请先选择历史模型", "error");
    return;
  }
  const data = await request("/api/model/activate", {
    method: "POST",
    body: JSON.stringify({ version_key: versionKey }),
  });
  showToast(data.message || "已切换默认模型");
  await refreshSummary();
}

async function rollbackVersion() {
  const data = await request("/api/model/rollback", {
    method: "POST",
    body: JSON.stringify({}),
  });
  showToast(data.message || "已回退到上一版");
  await refreshSummary();
}

function selectedVersionKeys() {
  return $$(".version-check:checked").map((item) => item.value);
}

async function deleteSelectedVersions() {
  const versionKeys = selectedVersionKeys();
  if (!versionKeys.length) {
    showToast("请先勾选要删除的模型版本", "error");
    return;
  }
  const data = await request("/api/model/delete", {
    method: "POST",
    body: JSON.stringify({ version_keys: versionKeys }),
  });
  showToast(`${data.message || "删除完成"}：${(data.deleted || []).join("、")}`);
  await refreshSummary();
}

function toggleStatusPanel(hidden) {
  $("#status-panel").classList.toggle("hidden-panel", hidden);
  $("#status-fab").classList.toggle("hidden", !hidden);
}

function parseDateText(value) {
  if (!value) return null;
  const parts = String(value).split("-").map((item) => Number(item));
  if (parts.length !== 3 || parts.some((item) => Number.isNaN(item))) return null;
  return new Date(parts[0], parts[1] - 1, parts[2]);
}

function formatDateText(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shiftPickerMonth(picker, delta) {
  const nextDate = new Date(picker.viewYear, picker.viewMonth - 1 + delta, 1);
  picker.viewYear = nextDate.getFullYear();
  picker.viewMonth = nextDate.getMonth() + 1;
}

function shiftPickerYear(picker, delta) {
  picker.viewYear += delta;
}

function getYearPanelStart(viewYear) {
  return Math.floor(viewYear / 12) * 12;
}

function buildMonthPanel(viewYear, selectedDate) {
  return Array.from({ length: 12 }, (_, index) => {
    const month = index + 1;
    const label = `${String(month).padStart(2, "0")}月`;
    const classes = ["calendar-cell"];
    if (selectedDate && selectedDate.getFullYear() === viewYear && selectedDate.getMonth() + 1 === month) {
      classes.push("selected");
    }
    return `<button type="button" class="${classes.join(" ")}" data-month="${month}">${label}</button>`;
  }).join("");
}

function buildYearPanel(viewYear, selectedDate) {
  const startYear = getYearPanelStart(viewYear);
  return Array.from({ length: 12 }, (_, index) => {
    const year = startYear + index;
    const classes = ["calendar-cell"];
    if (year === viewYear) classes.push("current");
    if (selectedDate && selectedDate.getFullYear() === year) classes.push("selected");
    return `<button type="button" class="${classes.join(" ")}" data-year="${year}">${year}</button>`;
  }).join("");
}

function buildCalendarDays(viewYear, viewMonth, selectedValue) {
  const firstDay = new Date(viewYear, viewMonth - 1, 1);
  const firstWeekday = firstDay.getDay() || 7;
  const daysInMonth = new Date(viewYear, viewMonth, 0).getDate();
  const prevMonthDays = new Date(viewYear, viewMonth - 1, 0).getDate();
  const cells = [];

  for (let i = firstWeekday - 1; i > 0; i -= 1) {
    const date = new Date(viewYear, viewMonth - 2, prevMonthDays - i + 1);
    cells.push({ text: date.getDate(), date: formatDateText(date), muted: true });
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = new Date(viewYear, viewMonth - 1, day);
    cells.push({ text: day, date: formatDateText(date), muted: false });
  }
  while (cells.length % 7 !== 0) {
    const offset = cells.length - (firstWeekday - 1) - daysInMonth + 1;
    const date = new Date(viewYear, viewMonth, offset);
    cells.push({ text: date.getDate(), date: formatDateText(date), muted: true });
  }

  return cells
    .map((item) => {
      const classes = ["calendar-day"];
      if (item.muted) classes.push("muted");
      if (item.date === selectedValue) classes.push("selected");
      return `<button type="button" class="${classes.join(" ")}" data-date="${item.date}">${item.text}</button>`;
    })
    .join("");
}

function renderDatePicker(pickerId) {
  const picker = App.datePickers[pickerId];
  const root = document.getElementById(pickerId);
  const input = document.getElementById(picker.inputId);
  const panel = root.querySelector(".date-panel");
  const selectedDate = parseDateText(picker.value) || new Date();
  const yearPanelStart = getYearPanelStart(picker.viewYear);
  let bodyHtml = "";
  let headerTitle = "";
  let showWeekdays = false;
  let leftNavHtml = `
    <button type="button" class="calendar-nav-btn" data-action="prev-year">&laquo;</button>
    <button type="button" class="calendar-nav-btn" data-action="prev-month">&lsaquo;</button>
  `;
  let rightNavHtml = `
    <button type="button" class="calendar-nav-btn" data-action="next-month">&rsaquo;</button>
    <button type="button" class="calendar-nav-btn" data-action="next-year">&raquo;</button>
  `;
  input.value = picker.value || "";
  input.disabled = !!picker.disabled;
  root.classList.toggle("open", picker.open);
  root.classList.toggle("disabled", !!picker.disabled);

  if (picker.panelMode === "year") {
    headerTitle = `${yearPanelStart} - ${yearPanelStart + 11}`;
    bodyHtml = `<div class="calendar-panel-grid">${buildYearPanel(picker.viewYear, selectedDate)}</div>`;
    leftNavHtml = `<button type="button" class="calendar-nav-btn" data-action="prev-year">&lsaquo;</button>`;
    rightNavHtml = `<button type="button" class="calendar-nav-btn" data-action="next-year">&rsaquo;</button>`;
  } else if (picker.panelMode === "month") {
    headerTitle = `${picker.viewYear}年`;
    bodyHtml = `<div class="calendar-panel-grid">${buildMonthPanel(picker.viewYear, selectedDate)}</div>`;
    leftNavHtml = `<button type="button" class="calendar-nav-btn" data-action="prev-year">&lsaquo;</button>`;
    rightNavHtml = `<button type="button" class="calendar-nav-btn" data-action="next-year">&rsaquo;</button>`;
  } else {
    showWeekdays = true;
    bodyHtml = `<div class="calendar-grid">${buildCalendarDays(picker.viewYear, picker.viewMonth, formatDateText(selectedDate))}</div>`;
  }

  panel.innerHTML = `
    <div class="calendar-toolbar">
      <div class="calendar-nav-group">
        ${leftNavHtml}
      </div>
      <div class="calendar-title calendar-title-controls">
        <button type="button" class="calendar-mode-btn ${picker.panelMode === "year" ? "active" : ""}" data-action="open-year-panel">
          ${picker.panelMode === "year" ? headerTitle : `${picker.viewYear}年`}
        </button>
        <button type="button" class="calendar-mode-btn ${picker.panelMode === "month" ? "active" : ""}" data-action="open-month-panel">
          ${picker.panelMode === "month" ? "选择月份" : `${String(picker.viewMonth).padStart(2, "0")}月`}
        </button>
      </div>
      <div class="calendar-nav-group">
        ${rightNavHtml}
      </div>
    </div>
    ${showWeekdays ? `
      <div class="calendar-weekdays">
        <div class="calendar-weekday">一</div>
        <div class="calendar-weekday">二</div>
        <div class="calendar-weekday">三</div>
        <div class="calendar-weekday">四</div>
        <div class="calendar-weekday">五</div>
        <div class="calendar-weekday">六</div>
        <div class="calendar-weekday">日</div>
      </div>
    ` : ""}
    ${bodyHtml}
  `;
}

function closeOtherDatePickers(exceptId) {
  Object.keys(App.datePickers).forEach((pickerId) => {
    if (pickerId !== exceptId && App.datePickers[pickerId].open) {
      App.datePickers[pickerId].open = false;
      App.datePickers[pickerId].panelMode = "day";
      renderDatePicker(pickerId);
    }
  });
}

function initDatePicker(pickerId, inputId, defaultValue) {
  const parsed = parseDateText(defaultValue) || new Date();
  App.datePickers[pickerId] = {
    inputId,
    value: defaultValue,
    open: false,
    disabled: false,
    panelMode: "day",
    viewYear: parsed.getFullYear(),
    viewMonth: parsed.getMonth() + 1,
  };
  renderDatePicker(pickerId);

  const root = document.getElementById(pickerId);
  root.addEventListener("click", (event) => {
    event.stopPropagation();
    const picker = App.datePickers[pickerId];
    if (picker.disabled) return;

    const action = event.target.closest("[data-action]")?.dataset.action;
    if (action === "open-year-panel") {
      picker.panelMode = "year";
      renderDatePicker(pickerId);
      return;
    }
    if (action === "open-month-panel") {
      picker.panelMode = "month";
      renderDatePicker(pickerId);
      return;
    }
    if (action === "prev-year") {
      if (picker.panelMode === "year") {
        shiftPickerYear(picker, -12);
      } else {
        shiftPickerYear(picker, -1);
      }
      renderDatePicker(pickerId);
      return;
    }
    if (action === "prev-month") {
      if (picker.panelMode === "month") {
        shiftPickerYear(picker, -1);
      } else if (picker.panelMode === "year") {
        shiftPickerYear(picker, -12);
      } else {
        shiftPickerMonth(picker, -1);
      }
      renderDatePicker(pickerId);
      return;
    }
    if (action === "next-month") {
      if (picker.panelMode === "month") {
        shiftPickerYear(picker, 1);
      } else if (picker.panelMode === "year") {
        shiftPickerYear(picker, 12);
      } else {
        shiftPickerMonth(picker, 1);
      }
      renderDatePicker(pickerId);
      return;
    }
    if (action === "next-year") {
      if (picker.panelMode === "year") {
        shiftPickerYear(picker, 12);
      } else {
        shiftPickerYear(picker, 1);
      }
      renderDatePicker(pickerId);
      return;
    }

    const yearButton = event.target.closest("[data-year]");
    if (yearButton?.dataset.year) {
      picker.viewYear = Number(yearButton.dataset.year) || picker.viewYear;
      picker.panelMode = "month";
      renderDatePicker(pickerId);
      return;
    }

    const monthButton = event.target.closest("[data-month]");
    if (monthButton?.dataset.month) {
      picker.viewMonth = Number(monthButton.dataset.month) || picker.viewMonth;
      picker.panelMode = "day";
      renderDatePicker(pickerId);
      return;
    }

    const dayButton = event.target.closest(".calendar-day");
    if (dayButton?.dataset.date) {
      picker.value = dayButton.dataset.date;
      const selectedDate = parseDateText(picker.value);
      picker.viewYear = selectedDate.getFullYear();
      picker.viewMonth = selectedDate.getMonth() + 1;
      picker.open = false;
      picker.panelMode = "day";
      renderDatePicker(pickerId);
      return;
    }

    picker.open = !picker.open;
    if (picker.open) {
      picker.panelMode = "day";
      closeOtherDatePickers(pickerId);
    } else {
      picker.panelMode = "day";
    }
    renderDatePicker(pickerId);
  });
}

function setDatePickerDisabled(pickerId, disabled) {
  App.datePickers[pickerId].disabled = disabled;
  if (disabled) {
    App.datePickers[pickerId].open = false;
    App.datePickers[pickerId].panelMode = "day";
  }
  renderDatePicker(pickerId);
}

function bindEvents() {
  $$(".tab-btn").forEach((btn) => btn.addEventListener("click", () => setActiveTab(btn.dataset.tab)));
  $("#train-btn").addEventListener("click", () => startTrain().catch((error) => showToast(error.message, "error")));
  $("#refresh-train-metrics-btn").addEventListener("click", () => refreshSummary().then(() => showToast("当前指标已刷新")).catch((error) => showToast(error.message, "error")));
  $("#reload-template-btn").addEventListener("click", () => loadTemplate().then(() => showToast("预测文件已重新加载")).catch((error) => showToast(error.message, "error")));
  $("#save-template-btn").addEventListener("click", () => saveTemplate().catch((error) => showToast(error.message, "error")));
  $("#predict-btn").addEventListener("click", () => startPredict().catch((error) => showToast(error.message, "error")));
  $("#reference-days").addEventListener("input", () => syncReferenceStrategyLabels());
  $("#reference-days").addEventListener("change", () => syncReferenceStrategyLabels());
  $("#prediction-view-strategy").addEventListener("change", () => {
    App.predictionViewDirty = true;
    renderComparisonCards(App.lastPrediction);
    renderPredictionTable(App.lastPrediction);
    renderPredictionChart(App.lastPrediction);
  });
  $("#activate-version-btn").addEventListener("click", () => activateVersion().catch((error) => showToast(error.message, "error")));
  $("#rollback-btn").addEventListener("click", () => rollbackVersion().catch((error) => showToast(error.message, "error")));
  $("#delete-versions-btn").addEventListener("click", () => deleteSelectedVersions().catch((error) => showToast(error.message, "error")));
  $("#select-all-versions").addEventListener("change", (event) => {
    $$(".version-check").forEach((item) => {
      item.checked = event.target.checked;
    });
    syncSelectAllVersionsState();
  });
  $("#versions-table").addEventListener("change", (event) => {
    if (event.target.matches(".version-check")) {
      syncSelectAllVersionsState();
    }
  });
  $("#enable-start").addEventListener("change", (event) => {
    setDatePickerDisabled("train-start-picker", !event.target.checked);
  });
  $("#enable-end").addEventListener("change", (event) => {
    setDatePickerDisabled("train-end-picker", !event.target.checked);
  });
  $("#hide-status-btn").addEventListener("click", () => toggleStatusPanel(true));
  $("#status-fab").addEventListener("click", () => toggleStatusPanel(false));

  document.addEventListener("click", (event) => {
    if (event.target.closest(".date-picker")) return;
    Object.keys(App.datePickers).forEach((pickerId) => {
      if (App.datePickers[pickerId].open) {
        App.datePickers[pickerId].open = false;
        renderDatePicker(pickerId);
      }
    });
  });
}

async function initialLoad() {
  resetSessionProgress();
  initDatePicker("train-start-picker", "train-start-date", "2025-01-01");
  initDatePicker("train-end-picker", "train-end-date", "2026-03-31");
  await loadConfig();
  renderConfigPaths();
  const initResults = await Promise.allSettled([refreshSummary(), loadLogs(), loadTemplate()]);
  initResults.forEach((result) => {
    if (result.status === "rejected") {
      console.error(result.reason);
    }
  });
  toggleStatusPanel(true);
  updateStatusTicker(["系统待命，点击展开查看详细运行过程"], false);
}

/* startPolling moved below — uses stopPolling for clean teardown */

/* ═══════════════════════════════════════════════
   KEYBOARD SHORTCUTS
   ═══════════════════════════════════════════════ */
function bindKeyboardShortcuts() {
  document.addEventListener("keydown", (event) => {
    if (event.target.matches("input, textarea, [contenteditable]")) return;

    const key = event.key.toLowerCase();
    if (event.ctrlKey || event.metaKey) {
      switch (key) {
        case "1": event.preventDefault(); setActiveTab("train"); break;
        case "2": event.preventDefault(); setActiveTab("predict"); break;
        case "3": event.preventDefault(); setActiveTab("versions"); break;
        case "4": event.preventDefault(); setActiveTab("logs"); break;
        case "s": event.preventDefault(); saveTemplate().catch((error) => showToast(error.message, "error")); break;
        case "enter": event.preventDefault(); startPredict().catch((error) => showToast(error.message, "error")); break;
      }
      return;
    }
    if (key === "escape") {
      toggleStatusPanel(true);
      Object.keys(App.datePickers).forEach((pickerId) => {
        if (App.datePickers[pickerId].open) {
          App.datePickers[pickerId].open = false;
          renderDatePicker(pickerId);
        }
      });
      document.activeElement?.blur();
    }
    if (key === "f5") {
      event.preventDefault();
      refreshSummary().then(() => showToast("已刷新")).catch((error) => showToast(error.message, "error"));
    }
  });
}

/* ═══════════════════════════════════════════════
   AUTO-REFRESH TOGGLE
   ═══════════════════════════════════════════════ */
function initAutoRefresh() {
  let running = true;
  const btn = document.createElement("button");
  btn.className = "auto-refresh on";
  btn.innerHTML = `<span class="auto-refresh-dot"></span> 自动刷新`;
  btn.title = "切换自动刷新 (每 1.5 秒)";
  btn.addEventListener("click", () => {
    running = !running;
    btn.classList.toggle("on", running);
    if (running) {
      startPolling();
      showToast("自动刷新已开启");
    } else {
      stopPolling();
      showToast("自动刷新已暂停");
    }
  });
  const topStatus = $("#top-status");
  if (topStatus) topStatus.appendChild(btn);
}

function stopPolling() {
  if (App.pollTimer) {
    clearInterval(App.pollTimer);
    App.pollTimer = null;
  }
}

function startPolling() {
  stopPolling();
  App.pollTimer = setInterval(() => {
    Promise.allSettled([refreshSummary(), loadLogs()]).then((results) => {
      results.forEach((result) => {
        if (result.status === "rejected") {
          console.error(result.reason);
        }
      });
    });
  }, 1500);
}

/* ═══════════════════════════════════════════════
   DATA EXPORT: COPY TABLE TO CLIPBOARD
   ═══════════════════════════════════════════════ */
function tableToCSV(tableId) {
  const table = $(`#${tableId}`);
  if (!table) return "";
  const rows = Array.from(table.querySelectorAll("tr"));
  return rows
    .map((row) =>
      Array.from(row.querySelectorAll("th, td"))
        .map((cell) => {
          let text = (cell.textContent || "").replace(/"/g, '""').trim();
          if (text.includes(",") || text.includes('"') || text.includes("\n")) {
            text = `"${text}"`;
          }
          return text;
        })
        .join(","),
    )
    .join("\n");
}

async function copyTableToClipboard(tableId) {
  const csv = tableToCSV(tableId);
  if (!csv) {
    showToast("暂无数据可复制", "error");
    return;
  }
  try {
    await navigator.clipboard.writeText(csv);
    showToast("已复制表格数据到剪贴板");
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = csv;
    textarea.style.cssText = "position:fixed;left:-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    showToast("已复制表格数据到剪贴板");
  }
}

function downloadCSV(filename, csvContent) {
  const bom = "﻿";
  const blob = new Blob([bom + csvContent], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function exportTableToCSV(tableId, filename) {
  const csv = tableToCSV(tableId);
  if (!csv) {
    showToast("暂无数据可导出", "error");
    return;
  }
  downloadCSV(filename, csv);
  showToast(`已导出 ${filename}`);
}

/* ═══════════════════════════════════════════════
   BUTTON LOADING STATE
   ═══════════════════════════════════════════════ */
function setButtonLoading(btn, loading, originalText) {
  if (loading) {
    btn.dataset.originalText = btn.textContent;
    btn.classList.add("loading");
    btn.textContent = "";
    btn.disabled = true;
  } else {
    btn.classList.remove("loading");
    btn.textContent = btn.dataset.originalText || originalText || btn.textContent;
    btn.disabled = false;
    delete btn.dataset.originalText;
  }
}

function wrapButtonWithLoading(selector, asyncFn) {
  const btn = $(selector);
  if (!btn) return async () => {};
  return async (...args) => {
    const originalText = btn.textContent;
    try {
      setButtonLoading(btn, true, originalText);
      return await asyncFn(...args);
    } finally {
      setButtonLoading(btn, false, originalText);
    }
  };
}

/* ═══════════════════════════════════════════════
   CHART LOADING / EMPTY STATE
   ═══════════════════════════════════════════════ */
function showChartLoading() {
  const stage = $("#prediction-chart");
  if (!stage) return;
  stage.innerHTML = `
    <div class="chart-loading">
      <div class="chart-spinner"></div>
      <span style="color: var(--text-3); font-size: 13px;">正在加载图表...</span>
    </div>`;
}

function showChartEmpty(message = "尚未执行预测") {
  const stage = $("#prediction-chart");
  if (!stage) return;
  stage.innerHTML = `
    <div class="chart-empty">
      <div class="chart-empty-icon">📊</div>
      <span>${htmlEscape(message)}</span>
    </div>`;
}

/* ═══════════════════════════════════════════════
   DARK MODE TOGGLE
   ═══════════════════════════════════════════════ */
function initDarkModeToggle() {
  const root = document.documentElement;
  const saved = localStorage.getItem("dayahead-dark-mode");
  if (saved === "true") {
    root.classList.add("dark-enabled");
  }
  const btn = document.createElement("button");
  btn.className = "ghost-btn mini-btn";
  btn.style.cssText = "position:fixed;top:18px;right:18px;z-index:1100;";
  btn.textContent = root.classList.contains("dark-enabled") ? "☀️" : "🌙";
  btn.title = "切换暗色模式";
  btn.addEventListener("click", () => {
    const isDark = root.classList.toggle("dark-enabled");
    localStorage.setItem("dayahead-dark-mode", String(isDark));
    btn.textContent = isDark ? "☀️" : "🌙";
    if (App.chart) {
      App.chart.dispose();
      App.chart = null;
      App.predictionChartSignature = null;
      if (App.lastPrediction) {
        renderPredictionChart(App.lastPrediction);
      }
    }
  });
  document.body.appendChild(btn);
}

/* ═══════════════════════════════════════════════
   TOOLBAR ACTIONS ROW (copy/export buttons)
   ═══════════════════════════════════════════════ */
function injectTableToolbarActions() {
  const toolbarSelectors = [
    { toolbar: "#tab-versions .table-toolbar", tableId: "versions-table", filename: "模型版本.csv" },
    { toolbar: "#tab-logs .table-toolbar", tableId: "training-logs-table", filename: "训练日志.csv" },
  ];

  toolbarSelectors.forEach(({ toolbar: toolbarSelector, tableId, filename }) => {
    const toolbar = document.querySelector(toolbarSelector);
    if (!toolbar) return;
    if (toolbar.querySelector(".copy-btn")) return;

    const actions = document.createElement("div");
    actions.style.cssText = "display:flex;gap:8px;align-items:center;";
    actions.innerHTML = `
      <button class="copy-btn" data-table="${tableId}" title="复制表格数据">📋 复制</button>
      <button class="csv-btn" data-table="${tableId}" data-filename="${filename}" title="导出为 CSV">⬇ CSV</button>
    `;
    toolbar.appendChild(actions);

    actions.querySelector(".copy-btn").addEventListener("click", (event) => {
      const btn = event.target.closest(".copy-btn");
      const tid = btn.dataset.table;
      copyTableToClipboard(tid);
      btn.classList.add("copied");
      setTimeout(() => btn.classList.remove("copied"), 1200);
    });

    actions.querySelector(".csv-btn").addEventListener("click", (event) => {
      const btn = event.target.closest(".csv-btn");
      exportTableToCSV(btn.dataset.table, btn.dataset.filename);
    });
  });

  const metricsToolbar = document.querySelector("#tab-train .subsection-title");
  if (metricsToolbar && !metricsToolbar.parentElement.querySelector(".copy-btn")) {
    const wrapper = document.createElement("div");
    wrapper.style.cssText = "display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;";
    metricsToolbar.parentElement.insertBefore(wrapper, metricsToolbar);
    wrapper.appendChild(metricsToolbar);

    const actions = document.createElement("div");
    actions.style.cssText = "display:flex;gap:8px;";
    actions.innerHTML = `
      <button class="copy-btn" data-table="metrics-table" title="复制指标数据">📋 复制</button>
      <button class="csv-btn" data-table="metrics-table" data-filename="模型指标.csv" title="导出为 CSV">⬇ CSV</button>
    `;
    wrapper.appendChild(actions);

    actions.querySelector(".copy-btn").addEventListener("click", (event) => {
      const btn = event.target.closest(".copy-btn");
      copyTableToClipboard(btn.dataset.table);
      btn.classList.add("copied");
      setTimeout(() => btn.classList.remove("copied"), 1200);
    });

    actions.querySelector(".csv-btn").addEventListener("click", (event) => {
      const btn = event.target.closest(".csv-btn");
      exportTableToCSV(btn.dataset.table, btn.dataset.filename);
    });
  }

  const predictionToolbar = document.querySelector("#tab-predict .chart-card .table-toolbar");
  if (predictionToolbar && !predictionToolbar.querySelector(".csv-btn")) {
    const predictBtn = document.createElement("button");
    predictBtn.className = "csv-btn";
    predictBtn.innerHTML = "⬇ 导出 CSV";
    predictBtn.title = "导出预测结果";
    predictBtn.addEventListener("click", () => {
      exportTableToCSV("prediction-table", "预测结果.csv");
    });
    predictionToolbar.appendChild(predictBtn);
  }
}

/* ═══════════════════════════════════════════════
   CARD VALUE FLASH ANIMATION
   ═══════════════════════════════════════════════ */
function flashCardValue(el) {
  el.classList.remove("updated");
  void el.offsetWidth;
  el.classList.add("updated");
}

/* ═══════════════════════════════════════════════
   INITIALIZATION (overridden / extended)
   ═══════════════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  bindKeyboardShortcuts();
  initDarkModeToggle();

  try {
    await initialLoad();
    startPolling();
    initAutoRefresh();
    injectTableToolbarActions();
  } catch (error) {
    showToast(error.message, "error");
  }
});
