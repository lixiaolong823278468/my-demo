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
    `当前状态：${activeJob?.status || "系统待命"}`,
    `当前模型：${statusData.current_model?.run_id || "-"}`,
    `预测文件：${App.config?.forecast_file || "-"}`,
    `结果文件：${App.config?.output_file || "-"}`,
  ];
  $("#top-status").innerHTML = items
    .map((item) => `<div class="status-chip"><span class="status-chip-dot"></span>${htmlEscape(item)}</div>`)
    .join("");
}

function renderConfigPaths() {
  $("#config-paths").innerHTML = `
    历史数据目录：<code>${htmlEscape(App.config?.history_dir || "-")}</code><br>
    模型目录：<code>${htmlEscape(App.config?.model_root || "-")}</code><br>
    预测文件：<code>${htmlEscape(App.config?.forecast_file || "-")}</code><br>
    前端目录：<code>${htmlEscape(App.config?.frontend_dir || "-")}</code>
  `;
}

function renderModelSummary(versions, metadata) {
  $("#current-model-id").textContent = metadata?.run_id || "-";
  $("#current-model-range").textContent = metadata?.train_start_date ? `${metadata.train_start_date} ~ ${metadata.train_end_date}` : "-";
  const previous = versions.find((item) => item.is_previous);
  $("#previous-model-id").textContent = previous?.version_key || "-";
  $("#previous-model-range").textContent = previous ? `${previous.train_start_date || "-"} ~ ${previous.train_end_date || "-"}` : "-";
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

function renderVersions(versions) {
  App.versions = versions;
  $("#version-select").innerHTML = versions.length
    ? versions.map((item) => `<option value="${htmlEscape(item.version_key)}">${htmlEscape(item.label || item.version_key)}</option>`).join("")
    : `<option value="">暂无历史模型</option>`;

  const tbody = $("#versions-table tbody");
  if (!versions.length) {
    tbody.innerHTML = `<tr><td colspan="6">暂无历史模型版本</td></tr>`;
    return;
  }
  tbody.innerHTML = versions
    .map((item) => {
      const tags = [];
      if (item.is_default) tags.push(`<span class="status-tag default">默认模型</span>`);
      if (item.is_previous) tags.push(`<span class="status-tag previous">上一版</span>`);
      return `
        <tr>
          <td><input type="checkbox" class="version-check" value="${htmlEscape(item.version_key)}"></td>
          <td>${htmlEscape(item.version_key)}</td>
          <td>${htmlEscape(item.created_at || "-")}</td>
          <td>${htmlEscape(item.train_start_date || "-")} ~ ${htmlEscape(item.train_end_date || "-")}</td>
          <td>${htmlEscape(item.sample_rows ?? "-")}</td>
          <td>${tags.join(" ") || "-"}</td>
        </tr>
      `;
    })
    .join("");
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

function renderPredictionTable(prediction) {
  const table = $("#prediction-table");
  if (!prediction || !prediction.rows?.length) {
    table.innerHTML = `<thead><tr><th>提示</th></tr></thead><tbody><tr><td>暂无预测结果</td></tr></tbody>`;
    return;
  }
  const columns = prediction.columns || Object.keys(prediction.rows[0]);
  const head = `<thead><tr>${columns.map((col) => `<th>${htmlEscape(columnTitleMap[col] || col)}</th>`).join("")}</tr></thead>`;
  const body = prediction.rows
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
  if (!prediction || !prediction.rows?.length) {
    target.innerHTML = [
      "预测最低价：-",
      "预测最高价：-",
      "预测均价：-",
      "参考日期：-",
    ].map((text) => `<span class="chart-stat">${text}</span>`).join("");
    return;
  }

  const values = prediction.rows.map((row) => Number(row.predicted_price || 0));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const avgValue = values.reduce((sum, item) => sum + item, 0) / Math.max(1, values.length);
  const refDate = prediction.rows[0]?.date || prediction.forecast_date || "-";
  target.innerHTML = [
    `预测最低价：${minValue.toFixed(2)}`,
    `预测最高价：${maxValue.toFixed(2)}`,
    `预测均价：${avgValue.toFixed(2)}`,
    `预测日期：${refDate}`,
  ].map((text) => `<span class="chart-stat">${text}</span>`).join("");
}

function renderPredictionChart(prediction) {
  renderPredictionStats(prediction);
  const chart = ensureChart();
  if (!chart) return;

  if (!prediction || !prediction.rows?.length) {
    chart.clear();
    $("#prediction-meta").textContent = "尚未执行预测";
    return;
  }

  const rows = prediction.rows;
  const periods = rows.map((row) => row.period);
  const predicted = rows.map((row) => Number(row.predicted_price || 0));
  const similar = rows.map((row) => Number(row.similar_price || 0));
  const lag96 = rows.map((row) => Number(row.lag_96 || 0));
  const residual = rows.map((row) => Number(row.residual_pred || 0));
  const forecastDate = prediction.forecast_date || rows[0]?.date || "-";

  chart.setOption(
    {
      backgroundColor: "transparent",
      animationDuration: 500,
      color: ["#1677ff", "#52c41a", "#722ed1", "#faad14"],
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: "rgba(17,24,39,0.92)",
        borderWidth: 0,
        textStyle: { color: "#ffffff" },
      },
      legend: {
        top: 12,
        textStyle: { color: "#4e5969" },
        data: ["预测价格", "相似法基线", "昨日同点价格", "残差修正"],
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
          name: "价格(元/MWh)",
          min: 0,
          max: 1500,
          axisLabel: { color: "#86909c" },
          splitLine: { lineStyle: { color: "rgba(5,5,5,0.06)" } },
        },
        {
          type: "value",
          gridIndex: 1,
          name: "残差",
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
          name: "预测价格",
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
          name: "昨日同点价格",
          type: "line",
          smooth: true,
          symbol: "none",
          lineStyle: { width: 2 },
          data: lag96,
        },
        {
          name: "残差修正",
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
  requestAnimationFrame(() => {
    chart.resize();
  });

  $("#prediction-meta").textContent = `预测日期：${forecastDate} · 共 ${rows.length} 点 · 价格范围已限制在 0~1500`;
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
  renderProgressSections();
  renderStatusPanel({});
  renderPredictionTable(null);
  renderPredictionChart(null);
}

async function loadConfig() {
  App.config = await request("/api/config");
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
    renderPredictionTable(statusData.last_prediction);
    renderPredictionChart(statusData.last_prediction);
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
}

async function startPredict() {
  App.predictSessionStarted = true;
  setPendingState("predict", "正在保存并提交预测任务...");
  await saveTemplate();
  const data = await request("/api/predict", {
    method: "POST",
    body: JSON.stringify({}),
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
  const current = parseDateText(picker.value) || new Date();
  input.value = picker.value || "";
  input.disabled = !!picker.disabled;
  root.classList.toggle("open", picker.open);
  root.classList.toggle("disabled", !!picker.disabled);
  panel.innerHTML = `
    <div class="calendar-toolbar">
      <button type="button" class="calendar-nav-btn" data-action="prev">‹</button>
      <div class="calendar-title">${picker.viewYear}年 ${picker.viewMonth}月</div>
      <button type="button" class="calendar-nav-btn" data-action="next">›</button>
    </div>
    <div class="calendar-weekdays">
      <div class="calendar-weekday">一</div>
      <div class="calendar-weekday">二</div>
      <div class="calendar-weekday">三</div>
      <div class="calendar-weekday">四</div>
      <div class="calendar-weekday">五</div>
      <div class="calendar-weekday">六</div>
      <div class="calendar-weekday">日</div>
    </div>
    <div class="calendar-grid">${buildCalendarDays(picker.viewYear, picker.viewMonth, formatDateText(current))}</div>
  `;
}

function closeOtherDatePickers(exceptId) {
  Object.keys(App.datePickers).forEach((pickerId) => {
    if (pickerId !== exceptId && App.datePickers[pickerId].open) {
      App.datePickers[pickerId].open = false;
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
    if (action === "prev") {
      picker.viewMonth -= 1;
      if (picker.viewMonth <= 0) {
        picker.viewMonth = 12;
        picker.viewYear -= 1;
      }
      renderDatePicker(pickerId);
      return;
    }
    if (action === "next") {
      picker.viewMonth += 1;
      if (picker.viewMonth >= 13) {
        picker.viewMonth = 1;
        picker.viewYear += 1;
      }
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
      renderDatePicker(pickerId);
      return;
    }

    picker.open = !picker.open;
    if (picker.open) closeOtherDatePickers(pickerId);
    renderDatePicker(pickerId);
  });
}

function setDatePickerDisabled(pickerId, disabled) {
  App.datePickers[pickerId].disabled = disabled;
  if (disabled) App.datePickers[pickerId].open = false;
  renderDatePicker(pickerId);
}

function bindEvents() {
  $$(".tab-btn").forEach((btn) => btn.addEventListener("click", () => setActiveTab(btn.dataset.tab)));
  $("#train-btn").addEventListener("click", () => startTrain().catch((error) => showToast(error.message, "error")));
  $("#refresh-train-metrics-btn").addEventListener("click", () => refreshSummary().then(() => showToast("当前指标已刷新")).catch((error) => showToast(error.message, "error")));
  $("#reload-template-btn").addEventListener("click", () => loadTemplate().then(() => showToast("预测文件已重新加载")).catch((error) => showToast(error.message, "error")));
  $("#save-template-btn").addEventListener("click", () => saveTemplate().catch((error) => showToast(error.message, "error")));
  $("#predict-btn").addEventListener("click", () => startPredict().catch((error) => showToast(error.message, "error")));
  $("#activate-version-btn").addEventListener("click", () => activateVersion().catch((error) => showToast(error.message, "error")));
  $("#rollback-btn").addEventListener("click", () => rollbackVersion().catch((error) => showToast(error.message, "error")));
  $("#delete-versions-btn").addEventListener("click", () => deleteSelectedVersions().catch((error) => showToast(error.message, "error")));
  $("#select-all-versions").addEventListener("change", (event) => {
    $$(".version-check").forEach((item) => {
      item.checked = event.target.checked;
    });
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

function startPolling() {
  if (App.pollTimer) clearInterval(App.pollTimer);
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

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  try {
    await initialLoad();
    startPolling();
  } catch (error) {
    showToast(error.message, "error");
  }
});
