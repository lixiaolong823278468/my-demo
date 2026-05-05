const App = {
  config: null,
  versions: [],
  templateRows: [],
  pollTimer: null,
  charts: {},
  chartResizeBound: false,
  predictionChartLayout: "stacked",
  pendingStatus: null,
  datePickers: {},
  tickerTimer: null,
  tickerMessages: [],
  tickerIndex: 0,
  tickerLoop: false,
  tickerVisibleMessages: [],
  activeJobIds: {
    train: null,
    predict: null,
    optimize: null,
  },
  jobStates: {
    train: null,
    predict: null,
    optimize: null,
  },
  statusFocus: null,
  predictSessionStarted: false,
  lastPrediction: null,
  predictionChartSignature: null,
  qualityReports: [],
  latestQualityReport: null,
  segmentRows: [],
};

const defaultSegmentRows = [
  { name: "night", start_time: "00:00", end_time: "06:00" },
  { name: "morning_peak", start_time: "06:00", end_time: "10:00" },
  { name: "midday", start_time: "10:00", end_time: "15:00" },
  { name: "evening_peak", start_time: "15:00", end_time: "20:00" },
  { name: "late_night", start_time: "20:00", end_time: "24:00" },
];
const segmentDraftStorageKey = "dayahead_segment_drafts_by_count";

const columnTitleMap = {
  date: "日期",
  period: "时段",
  segment: "分时段",
  hour: "小时",
  net_load: "火电空间",
  thermal_on_capacity: "火电开机容量(MW)",
  similar_price: "多条件相似参考",
  net_load_only_similar_price: "仅火电空间相似参考",
  residual_pred: "模型与相似法差值",
  model_similarity_diff: "模型与相似法差值",
  predicted_price: "模型预测价格",
  recent_n_days_similar_price: "最近 N 天多条件相似参考",
  recent_n_days_net_load_only_similar_price: "最近 N 天仅火电空间参考",
  recent_n_days_residual_pred: "最近 N 天模型与相似法差值",
  recent_n_days_predicted_price: "最近 N 天模型预测价格",
  recent_same_type_days_similar_price: "同类型日多条件相似参考",
  recent_same_type_days_net_load_only_similar_price: "同类型日仅火电空间参考",
  recent_same_type_days_residual_pred: "同类型日模型与相似法差值",
  recent_same_type_days_predicted_price: "同类型日模型预测价格",
  prediction_price_diff: "两策略价差",
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
const referenceStrategyOrder = ["recent_n_days", "recent_same_type_days"];
const predictionSeriesNameMap = {
  recent_n_days: "最近 N 天预测价格",
  recent_same_type_days: "同类型日预测价格",
};
const predictionChartConfigMap = {
  recent_n_days: {
    elementId: "prediction-chart-recent-n-days",
    predictedName: "模型预测价格",
    similarName: "多条件相似参考",
    netLoadOnlyName: "仅火电空间相似参考",
    residualName: "最近 N 天模型与相似法差值",
  },
  recent_same_type_days: {
    elementId: "prediction-chart-same-type-days",
    predictedName: "模型预测价格",
    similarName: "多条件相似参考",
    netLoadOnlyName: "仅火电空间相似参考",
    residualName: "同类型日模型与相似法差值",
  },
};
const predictionChartLayoutStorageKey = "dayahead-prediction-chart-layout";

const helpContentUrl = "/assets/help-content.json";

let helpContentMap = {
  寻优最大历史天数: {
    title: "寻优最大历史天数",
    body: "自动寻找训练窗口时，最多向历史数据回看多少天。范围越大，能测试的训练窗口越多，但计算时间也会变长。",
    tips: ["数据变化快时可适当缩短", "数据规律稳定时可适当放大", "不确定时保持默认值即可"],
  },
  寻优验证集天数: {
    title: "寻优验证集天数",
    body: "自动寻优时预留最近多少天作为验证集，用来判断不同窗口参数的效果。",
    tips: ["天数太少容易偶然", "天数太多会减少训练样本", "常用 7~30 天"],
  },
  "寻优 XGBoost 轮数": {
    title: "寻优 XGBoost 轮数",
    body: "模型在寻优阶段迭代学习的轮数。轮数越大，模型学习更充分，但耗时更久，也可能过拟合。",
    tips: ["数据量较小时不用过大", "训练慢时先降低轮数", "默认值偏稳妥"],
  },
  局部细搜半径: {
    title: "局部细搜半径",
    body: "粗略找到较优训练窗口后，在最优点附近再细查多少天。半径越大，细搜越充分但耗时越长。",
    tips: ["设为 0 表示不做细搜", "窗口效果波动大时可适当增加", "常用 7~30 天"],
  },
  启用高价样本加权: {
    title: "启用高价样本加权",
    body: "让模型在训练时更重视高价时段，减少尖峰价格预测偏差。",
    tips: ["适合重点关注高价风险", "开启后普通时段误差可能略有变化"],
  },
  高价阈值分位: {
    title: "高价阈值分位",
    body: "按历史价格排序后，把超过该分位的样本视为高价样本。例如 0.8 表示价格最高的约 20% 样本。",
    tips: ["数值越高，高价样本越少", "想更广泛关注高价可降低到 0.7~0.8"],
  },
  高价权重倍数: {
    title: "高价权重倍数",
    body: "高价样本在训练中的权重倍数。数值越大，模型越优先拟合高价样本。",
    tips: ["过大可能牺牲普通价格段", "常用 1.5~3"],
  },
  时段模式: {
    title: "时段模式",
    body: "决定模型是否按固定时段或自定义时段分别学习价格规律。",
    tips: ["默认 5 段适合大多数情况", "有明确业务时段差异时再自定义"],
  },
  切分段数: {
    title: "切分段数",
    body: "自定义时段时把一天切成几段。分段越多，模型越细，但每段样本也会变少。",
    tips: ["样本少时不要切太细", "一般 4~6 段更稳"],
  },
  时段名称: {
    title: "时段名称",
    body: "当前时段的业务名称，仅用于区分不同时段的模型表现和配置。",
    tips: ["建议使用能看懂的名称", "名称不要重复"],
  },
  开始时间: {
    title: "开始时间",
    body: "当前时段的起点，由上一段结束时间自动衔接。",
    tips: ["需要连续覆盖全天", "时间以 15 分钟为粒度"],
  },
  结束时间: {
    title: "结束时间",
    body: "当前时段的终点。修改后下一段开始时间会自动衔接。",
    tips: ["最后一段固定结束于 24:00", "每段建议至少 1 小时"],
  },
  训练模式: {
    title: "训练模式",
    body: "选择手动训练使用最近 N 天滚动窗口，还是指定起止日期范围。",
    tips: ["滚动窗口更适合日常更新", "指定日期适合复盘某段历史"],
  },
  训练窗口天数: {
    title: "训练窗口天数",
    body: "手动训练时使用最近多少天作为训练样本。",
    tips: ["太短可能不稳定", "太长可能混入过旧规律", "常用 30~180 天"],
  },
  训练起始日期: {
    title: "训练起始日期",
    body: "手动日期范围训练时的开始日期。",
    tips: ["只在手动起止日期模式下生效", "建议覆盖完整业务周期"],
  },
  训练结束日期: {
    title: "训练结束日期",
    body: "手动日期范围训练时的结束日期。",
    tips: ["通常选择预测日前最近的可用日期", "不要晚于数据实际范围"],
  },
  启用训练起始日期: {
    title: "启用训练起始日期",
    body: "控制手动日期范围训练时是否使用起始日期限制。",
    tips: ["滚动窗口模式下通常不需要手动控制", "关闭后由系统按当前模式自动处理"],
  },
  启用训练结束日期: {
    title: "启用训练结束日期",
    body: "控制手动日期范围训练时是否使用结束日期限制。",
    tips: ["一般建议开启，避免训练数据范围不明确", "滚动窗口模式下由系统自动处理"],
  },
  手动验证集天数: {
    title: "手动验证集天数",
    body: "手动训练时从训练数据末尾预留多少天做验证，用于评估模型效果。",
    tips: ["常用 7~30 天", "样本少时不要设置过大"],
  },
  "手动 XGBoost 轮数": {
    title: "手动 XGBoost 轮数",
    body: "手动训练时模型迭代学习的轮数。轮数越多耗时越长。",
    tips: ["训练变慢可降低", "效果不稳定可配合验证集观察"],
  },
  参考天数: {
    title: "参考天数",
    body: "预测时相似法参考曲线使用最近多少天或多少个同类型日。",
    tips: ["数值小更贴近近期", "数值大更平滑稳定"],
  },
  火电空间权重: {
    title: "火电空间权重",
    body: "相似日匹配时，火电空间相似程度占多大权重。",
    tips: ["越大越强调供需剩余空间", "只影响参考曲线展示"],
  },
  新能源权重: {
    title: "新能源权重",
    body: "相似日匹配时，新能源出力相似程度占多大权重。",
    tips: ["新能源波动明显时可提高", "只影响参考曲线展示"],
  },
  火电容量权重: {
    title: "火电容量权重",
    body: "相似日匹配时，火电开机容量相似程度占多大权重。",
    tips: ["机组开停变化大时可提高", "只影响参考曲线展示"],
  },
  日期类型权重: {
    title: "日期类型权重",
    body: "相似日匹配时，工作日、周末、节假日等日期类型占多大权重。",
    tips: ["节假日影响明显时可提高", "只影响参考曲线展示"],
  },
  供需比权重: {
    title: "供需比权重",
    body: "相似日匹配时，供需比例相似程度占多大权重。",
    tips: ["供需紧张度影响价格时可提高", "只影响参考曲线展示"],
  },
  历史模型下拉列表: {
    title: "历史模型下拉列表",
    body: "选择已经训练完成的历史模型版本，用于设为默认、回退或删除。",
    tips: ["默认模型会用于后续预测", "删除前建议确认不是常用版本"],
  },
  排序方式: {
    title: "排序方式",
    body: "控制历史模型列表的排列顺序，便于按时间或误差快速筛选。",
    tips: ["MAE/RMSE 越小通常越好", "也要结合训练日期和样本范围判断"],
  },
  当前默认模型分时段指标: {
    title: "当前默认模型分时段指标",
    body: "按不同时段展示当前默认模型在验证集上的表现，帮助判断模型在哪些时段更准或更弱。",
    tips: ["重点关注晚高峰和高价时段", "和相似法参考对比更直观"],
  },
  模型算法对比: {
    title: "模型算法对比",
    body: "对比不同算法在验证集上的误差，系统会选择综合表现更好的算法作为当前模型。",
    tips: ["MAE/RMSE 越小越好", "是否选中表示最终启用的算法"],
  },
  "最近 14/30 天滚动回测": {
    title: "最近 14/30 天滚动回测",
    body: "模拟最近 14 天或 30 天每天预测一次，用来观察模型在近期连续预测中的稳定性。",
    tips: ["比单次验证更接近日常使用", "重点看误差、方向准确率和最大误差"],
  },
  模型直观诊断: {
    title: "模型直观诊断",
    body: "把复杂指标翻译成更容易理解的观察角度，帮助快速判断模型是否可靠。",
    tips: ["状态提示用于快速筛查", "发现异常时再看详细表格"],
  },
  误差最大日期: {
    title: "误差最大日期",
    body: "列出近期回测中误差较大的日期，便于复盘极端价格或数据异常。",
    tips: ["优先检查最大误差日期", "可结合训练日志和数据异常页面排查"],
  },
  分时段: {
    title: "分时段",
    body: "把一天按价格或业务规律拆成多个时段，分别统计模型表现。",
    tips: ["不同时段误差差异可能很大"],
  },
  "相似法参考 MAE": {
    title: "相似法参考 MAE",
    body: "相似法参考价格的平均绝对误差，用作模型效果的基准线。",
    tips: ["模型 MAE 小于它，说明模型优于相似法"],
  },
  "相似法参考 RMSE": {
    title: "相似法参考 RMSE",
    body: "相似法参考价格的均方根误差，对大误差更敏感。",
    tips: ["RMSE 越大，说明存在更明显的大偏差"],
  },
  "模型 MAE": {
    title: "模型 MAE",
    body: "模型预测价格与真实价格的平均绝对误差。越小表示平均偏差越小。",
    tips: ["适合看整体平均表现", "单位与电价一致"],
  },
  "模型 RMSE": {
    title: "模型 RMSE",
    body: "模型预测误差的均方根。相比 MAE，它会更重视大误差。",
    tips: ["RMSE 明显高于 MAE 时，说明可能有尖峰误差"],
  },
  训练样本数: {
    title: "训练样本数",
    body: "参与模型学习的数据量。样本越多通常越稳定，但过旧样本可能影响近期规律。",
    tips: ["样本太少时指标可信度下降"],
  },
  验证样本数: {
    title: "验证样本数",
    body: "用于验证模型效果的数据量，不直接参与训练。",
    tips: ["验证样本越充足，评估越稳定"],
  },
  算法: {
    title: "算法",
    body: "用于训练预测模型的方法名称，例如 XGBoost 或其他候选算法。",
    tips: ["不同算法适合不同数据形态"],
  },
  是否选中: {
    title: "是否选中",
    body: "表示该算法是否被系统选为最终使用的默认算法。",
    tips: ["通常选择验证误差更优的算法"],
  },
  MAE: {
    title: "MAE",
    body: "平均绝对误差，表示预测价格平均偏离真实价格多少。越小越好。",
    tips: ["看平均水平最直观", "单位与电价一致"],
  },
  RMSE: {
    title: "RMSE",
    body: "均方根误差，对大误差更敏感。越小越好。",
    tips: ["适合发现尖峰预测偏差", "RMSE 远大于 MAE 时要重点复盘"],
  },
  窗口: {
    title: "窗口",
    body: "滚动回测统计的时间范围，例如最近 14 天或 30 天。",
    tips: ["短窗口看近期", "长窗口看稳定性"],
  },
  "多条件相似法 MAE": {
    title: "多条件相似法 MAE",
    body: "综合多个特征寻找相似日后得到的参考价格误差。",
    tips: ["用于和模型预测进行横向比较"],
  },
  较多条件提升: {
    title: "较多条件提升",
    body: "模型相对多条件相似法减少了多少 MAE。正数越大表示模型提升越明显。",
    tips: ["为负数时说明模型不如该参考法"],
  },
  "仅火电空间相似法 MAE": {
    title: "仅火电空间相似法 MAE",
    body: "只按火电空间寻找相似日得到的参考价格误差。",
    tips: ["用于判断火电空间单因素的参考价值"],
  },
  较火电空间提升: {
    title: "较火电空间提升",
    body: "模型相对仅火电空间相似法减少了多少 MAE。正数表示模型更好。",
    tips: ["可判断模型是否超过简单基线"],
  },
  方向准确率: {
    title: "方向准确率",
    body: "预测价格变化方向与真实变化方向一致的比例。",
    tips: ["越高越好", "适合判断涨跌趋势是否靠谱"],
  },
  "高价尖峰 MAE": {
    title: "高价尖峰 MAE",
    body: "只统计高价尖峰样本上的平均绝对误差。",
    tips: ["关注价格风险时优先看这个指标"],
  },
  "晚高峰 MAE": {
    title: "晚高峰 MAE",
    body: "只统计晚高峰时段上的平均绝对误差。",
    tips: ["晚高峰价格波动大，通常需要重点关注"],
  },
  最大误差: {
    title: "最大误差",
    body: "单个点位出现过的最大绝对预测偏差。",
    tips: ["用于发现极端偏差", "越小越安全"],
  },
  样本数: {
    title: "样本数",
    body: "本项指标参与统计的数据点数量。",
    tips: ["样本少时结论要谨慎"],
  },
  观察角度: {
    title: "观察角度",
    body: "把模型表现拆成容易理解的检查维度。",
    tips: ["用于快速定位模型问题"],
  },
  数值: {
    title: "数值",
    body: "当前观察维度对应的具体指标值。",
    tips: ["结合右侧解释和状态一起看"],
  },
  怎么理解: {
    title: "怎么理解",
    body: "对当前指标含义的业务化解释，帮助快速判断是否需要处理。",
    tips: ["优先看异常或偏弱项"],
  },
  状态: {
    title: "状态",
    body: "系统根据指标给出的快速判断。",
    tips: ["正常表示无需特别处理", "异常建议继续查看日志或数据异常"],
  },
  日期: {
    title: "日期",
    body: "该行指标对应的预测或回测日期。",
    tips: ["误差大时可按日期回查数据和曲线"],
  },
};

helpContentMap = {};

const pageMetaMap = {
  train: {
    title: "模型训练中心",
    subtitle: "设置训练范围、执行重训，并查看当前模型的核心指标。",
  },
  predict: {
    title: "日前电价预测",
    subtitle: "输入参考天数后执行预测，同时对比最近天和同类型日两条 96 点价格曲线。",
  },
  versions: {
    title: "模型版本管理",
    subtitle: "管理历史模型版本，支持默认切换与快速回退。",
  },
  logs: {
    title: "训练日志复盘",
    subtitle: "按正式训练记录查看历史时间范围与样本表现。",
  },
  "data-quality": {
    title: "数据异常记录",
    subtitle: "汇总 Excel 导入时发现的缺失、非数字、字段不匹配和时点不足等问题。",
  },
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

function normalizeHelpContentItem(key, item) {
  if (!item || typeof item !== "object") return null;
  const title = normalizeHelpLabel(item.title || key);
  const body = String(item.body || item.description || "").trim();
  if (!title || !body) return null;
  const tips = Array.isArray(item.tips)
    ? item.tips.map((tip) => String(tip || "").trim()).filter(Boolean)
    : [];
  return { title, body, tips };
}

function normalizeHelpContentMap(rawContent) {
  const source = rawContent?.items && typeof rawContent.items === "object" ? rawContent.items : rawContent;
  if (!source || typeof source !== "object") return {};
  return Object.fromEntries(
    Object.entries(source)
      .map(([key, item]) => [normalizeHelpLabel(key), normalizeHelpContentItem(key, item)])
      .filter(([, item]) => item),
  );
}

async function loadHelpContent() {
  try {
    const response = await fetch(`${helpContentUrl}?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`说明文档加载失败：${response.status}`);
    const data = await response.json();
    const externalMap = normalizeHelpContentMap(data);
    if (Object.keys(externalMap).length) {
      helpContentMap = externalMap;
    }
  } catch (error) {
    helpContentMap = {};
    console.warn("参数说明文档加载失败，暂不显示问号说明：", error);
  }
}

function normalizeHelpLabel(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function getElementLabelText(element) {
  const clone = element.cloneNode(true);
  clone.querySelectorAll(".help-trigger").forEach((node) => node.remove());
  return normalizeHelpLabel(clone.textContent);
}

function getHelpPopover() {
  let popover = $("#help-popover");
  if (popover) return popover;
  popover = document.createElement("div");
  popover.id = "help-popover";
  popover.className = "help-popover hidden";
  popover.setAttribute("role", "dialog");
  popover.setAttribute("aria-live", "polite");
  document.body.appendChild(popover);
  return popover;
}

function hideHelpPopover() {
  const popover = $("#help-popover");
  if (!popover) return;
  popover.classList.add("hidden");
  $$(".help-trigger.active").forEach((button) => {
    button.classList.remove("active");
    button.setAttribute("aria-expanded", "false");
  });
}

function positionHelpPopover(trigger, popover) {
  const rect = trigger.getBoundingClientRect();
  const gap = 12;
  const width = Math.min(340, window.innerWidth - 28);
  popover.style.width = `${width}px`;
  popover.classList.remove("hidden");
  const popoverRect = popover.getBoundingClientRect();
  let left = rect.left + rect.width / 2 - width / 2;
  left = Math.max(14, Math.min(left, window.innerWidth - width - 14));
  let top = rect.bottom + gap;
  if (top + popoverRect.height > window.innerHeight - 14) {
    top = Math.max(14, rect.top - popoverRect.height - gap);
  }
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}

function showHelpPopover(trigger) {
  const config = helpContentMap[trigger.dataset.helpKey];
  if (!config) return;
  const popover = getHelpPopover();
  const isSameTrigger = trigger.classList.contains("active") && !popover.classList.contains("hidden");
  hideHelpPopover();
  if (isSameTrigger) return;
  const tips = (config.tips || [])
    .map((item) => `<li>${htmlEscape(item)}</li>`)
    .join("");
  popover.innerHTML = `
    <div class="help-popover-kicker">参数 / 指标说明</div>
    <div class="help-popover-title">${htmlEscape(config.title)}</div>
    <div class="help-popover-body">${htmlEscape(config.body)}</div>
    ${tips ? `<ul class="help-popover-tips">${tips}</ul>` : ""}
  `;
  trigger.classList.add("active");
  trigger.setAttribute("aria-expanded", "true");
  positionHelpPopover(trigger, popover);
}

function createHelpTrigger(key) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "help-trigger";
  button.dataset.helpKey = key;
  button.textContent = "?";
  button.setAttribute("aria-label", `${helpContentMap[key].title}说明`);
  button.setAttribute("aria-expanded", "false");
  return button;
}

function attachHelpTrigger(element) {
  if (!element || element.querySelector(".help-trigger")) return;
  const key = getElementLabelText(element);
  if (!helpContentMap[key]) return;
  element.classList.add("help-enabled");
  element.appendChild(createHelpTrigger(key));
}

function injectHelpAffordances(root = document) {
  root.querySelectorAll(".field > span, .switch-item > span, .data-table th, .subsection-title").forEach(attachHelpTrigger);
}

function bindHelpPopoverEvents() {
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest(".help-trigger");
    if (trigger) {
      event.preventDefault();
      event.stopPropagation();
      showHelpPopover(trigger);
      return;
    }
    if (!event.target.closest(".help-popover")) hideHelpPopover();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideHelpPopover();
  });
  window.addEventListener("resize", hideHelpPopover);
  window.addEventListener("scroll", hideHelpPopover, true);
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
  const pageMeta = pageMetaMap[name];
  if (pageMeta) {
    const title = document.querySelector(".hero-title");
    const subtitle = document.querySelector(".hero-subtitle");
    if (title) title.textContent = pageMeta.title;
    if (subtitle) subtitle.textContent = pageMeta.subtitle;
  }
  if (name === "predict") {
    requestAnimationFrame(() => {
      resizePredictionCharts();
    });
  }
  if (name === "logs") {
    loadLogs().catch((error) => {
      console.error(error);
      showToast(error.message, "error");
    });
  }
  if (name === "data-quality") {
    loadDataQuality().catch((error) => {
      console.error(error);
      showToast(error.message, "error");
    });
  }
}

function renderTopStatus(statusData) {
  const activeJob = getFocusedJobState() || statusData.current_job;
  const windowState = statusData.window_optimization || {};
  const windowLabel = windowState.best_window_days
    ? `最优训练窗口：最近 ${windowState.best_window_days} 天`
    : "最优训练窗口：待寻优";
  const items = [
    `当前模型：${statusData.current_model?.run_id || "-"}`,
    `运行状态：${activeJob?.status || "系统待命"}`,
  ];
  items.push(windowLabel);
  items.push(
    windowState.max_search_history_days
      ? `寻优上限：最近 ${windowState.max_search_history_days} 天`
      : `寻优上限：最近 ${currentWindowOptimizationMaxHistoryDays()} 天`,
  );
  items.push(windowState.final_model?.run_id ? `默认模型已更新：${windowState.final_model.run_id}` : "默认模型更新：待执行");
  $("#top-status").innerHTML = items
    .map((item) => `<div class="status-chip"><span class="status-chip-dot"></span>${htmlEscape(item)}</div>`)
    .join("");
}

function renderConfigPaths() {
}

function formatModelTrainingConfig(metadata = {}) {
  const segments = Array.isArray(metadata.segment_config)
    ? metadata.segment_config
    : (Array.isArray(metadata.segments) ? metadata.segments : []);
  const segmentText = segments.length ? `${segments.length} 段` : "-";
  const highConfig = metadata.high_price_weighting || {};
  const highText = highConfig.enabled
    ? `高价加权开：P${Math.round(Number(highConfig.quantile || 0.8) * 100)} ×${highConfig.multiplier ?? 2}`
    : "高价加权关";
  const backend = metadata.selected_model_backend_label || metadata.selected_model_backend || "-";
  return `${segmentText} / ${highText} / ${backend}`;
}

function renderModelSummary(versions, metadata) {
  $("#current-model-id").textContent = metadata?.run_id || "-";
  $("#current-model-range").textContent = metadata?.train_start_date ? `${metadata.train_start_date} ~ ${metadata.train_end_date}` : "-";
  const configEl = $("#current-model-config");
  if (configEl) configEl.textContent = formatModelTrainingConfig(metadata || {});
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


function renderModelComparison(metadata = {}) {
  const tbody = $("#model-compare-table tbody");
  if (!tbody) return;
  const quality = metadata.variant_quality_metrics || {};
  const variants = metadata.model_variants || {};
  const selectedKey = metadata.selected_model_key;
  const rows = Object.entries(quality);
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="4">暂无模型算法对比数据</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(([key, row]) => {
      const variant = variants[key] || {};
      const label = variant.model_backend_label || variant.model_backend || key;
      return `
        <tr>
          <td>${htmlEscape(label)}</td>
          <td>${key === selectedKey ? "当前最优" : "-"}</td>
          <td>${row.final_mae ?? "-"}</td>
          <td>${row.final_rmse ?? "-"}</td>
        </tr>
      `;
    })
    .join("");
}

function renderRollingBacktest(metadata = {}) {
  const tbody = $("#rolling-backtest-table tbody");
  if (!tbody) return;
  const backtests = metadata.rolling_backtest_metrics || {};
  const rows = Object.entries(backtests);
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="12">暂无滚动回测数据</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(([days, row]) => {
      const overall = row.overall || {};
      const baseline = row.baseline || {};
      const netLoadOnlyBaseline = row.net_load_only_baseline || {};
      const high = row.spike_errors?.high || {};
      const evening = row.segments?.evening_peak || {};
      const compare = row.model_vs_similarity || {};
      const netLoadOnlyCompare = row.model_vs_net_load_only_similarity || {};
      return `
        <tr>
          <td>最近 ${htmlEscape(days)} 天</td>
          <td>${formatMetricCell(overall.mae)}</td>
          <td>${formatMetricCell(overall.rmse)}</td>
          <td>${formatMetricCell(baseline.mae)}</td>
          <td>${formatMetricCell(compare.mae_improvement)}</td>
          <td>${formatMetricCell(netLoadOnlyBaseline.mae)}</td>
          <td>${formatMetricCell(netLoadOnlyCompare.mae_improvement)}</td>
          <td>${formatPercentCell(overall.direction_accuracy)}</td>
          <td>${formatMetricCell(high.mae)}</td>
          <td>${formatMetricCell(evening.mae)}</td>
          <td>${formatMetricCell(overall.max_abs_error)}</td>
          <td>${row.rows ?? "-"}</td>
        </tr>
      `;
    })
    .join("");
}

function healthText(value, goodLimit, warnLimit, lowerIsBetter = true) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "暂无数据";
  if (lowerIsBetter) {
    if (numericValue <= goodLimit) return "较好";
    if (numericValue <= warnLimit) return "一般";
    return "需关注";
  }
  if (numericValue >= goodLimit) return "较好";
  if (numericValue >= warnLimit) return "一般";
  return "需关注";
}

function renderModelHealth(metadata = {}) {
  const tbody = $("#model-health-table tbody");
  if (!tbody) return;
  const rolling = metadata.rolling_backtest_metrics || {};
  const backtest14 = rolling["14"] || {};
  const backtest30 = rolling["30"] || {};
  const overall14 = backtest14.overall || {};
  const overall30 = backtest30.overall || {};
  const high30 = backtest30.spike_errors?.high || backtest14.spike_errors?.high || {};
  const evening30 = backtest30.segments?.evening_peak || backtest14.segments?.evening_peak || {};
  const compare30 = backtest30.model_vs_similarity || backtest14.model_vs_similarity || {};
  const netLoadOnlyCompare30 = backtest30.model_vs_net_load_only_similarity || backtest14.model_vs_net_load_only_similarity || {};
  const similarityImprovement = Number(compare30.mae_improvement);
  const netLoadOnlyImprovement = Number(netLoadOnlyCompare30.mae_improvement);
  const rows = [
    ["最近14天整体", overall14.mae, "平均每个点差多少钱", healthText(overall14.mae, 35, 55)],
    ["最近30天整体", overall30.mae, "更接近真实长期使用", healthText(overall30.mae, 45, 70)],
    ["高价尖峰", high30.mae, "价格冲高时能不能跟上", healthText(high30.mae, 80, 150)],
    ["晚高峰", evening30.mae, "最容易影响交易判断的时段", healthText(evening30.mae, 50, 80)],
    ["方向判断", overall30.direction_accuracy ?? overall14.direction_accuracy, "上涨/下跌方向是否判断对", healthText(overall30.direction_accuracy ?? overall14.direction_accuracy, 65, 55, false)],
    ["相似法对比", compare30.mae_improvement, "正数表示模型比相似法平均误差更小", Number.isFinite(similarityImprovement) ? (similarityImprovement > 0 ? "模型更好" : "相似法更好或持平") : "暂无数据"],
    ["仅火电空间相似法对比", netLoadOnlyCompare30.mae_improvement, "正数表示模型比仅火电空间相似法平均误差更小", Number.isFinite(netLoadOnlyImprovement) ? (netLoadOnlyImprovement > 0 ? "模型更好" : "仅火电空间相似法更好或持平") : "暂无数据"],
  ];
  tbody.innerHTML = rows
    .map(
      ([name, value, meaning, status]) => `
        <tr>
          <td>${htmlEscape(name)}</td>
          <td>${formatMetricCell(value)}</td>
          <td>${htmlEscape(meaning)}</td>
          <td>${htmlEscape(status)}</td>
        </tr>
      `,
    )
    .join("");
}

function renderDailyErrorRank(metadata = {}) {
  const tbody = $("#daily-error-table tbody");
  if (!tbody) return;
  const rolling = metadata.rolling_backtest_metrics || {};
  const rank = rolling["30"]?.daily_error_rank || rolling["14"]?.daily_error_rank || {};
  const worst = rank.worst || [];
  if (!worst.length) {
    tbody.innerHTML = `<tr><td colspan="5">暂无每日误差排行</td></tr>`;
    return;
  }
  tbody.innerHTML = worst
    .slice(0, 5)
    .map(
      (row) => `
        <tr>
          <td>${htmlEscape(row.date || "-")}</td>
          <td>${formatMetricCell(row.mae)}</td>
          <td>${formatMetricCell(row.rmse)}</td>
          <td>${formatMetricCell(row.max_abs_error)}</td>
          <td>${formatPercentCell(row.direction_accuracy)}</td>
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

function currentVersionSort() {
  return $("#version-sort")?.value || "created_at_desc";
}

function setVersionSort(sortKey) {
  const select = $("#version-sort");
  if (select) {
    select.value = sortKey;
  }
}

function formatMetricCell(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "-";
  return numericValue.toFixed(2);
}

function formatPercentCell(value) {
  const formatted = formatMetricCell(value);
  return formatted === "-" ? "-" : `${formatted}%`;
}

function formatChartTooltipValue(value) {
  const rawValue = Array.isArray(value) ? value[value.length - 1] : value;
  const numericValue = Number(rawValue);
  if (!Number.isFinite(numericValue)) return rawValue ?? "-";
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 2,
  }).format(numericValue);
}

function sortVersionsForDisplay(versions) {
  const sortKey = currentVersionSort();
  const list = [...versions];
  const metricKeyMap = {
    baseline_mae_asc: "baseline_mae",
    baseline_rmse_asc: "baseline_rmse",
    final_mae_asc: "final_mae",
    final_rmse_asc: "final_rmse",
  };

  if (sortKey === "created_at_desc") {
    return list.sort((left, right) => String(right.created_at || "").localeCompare(String(left.created_at || "")));
  }

  const metricKey = metricKeyMap[sortKey];
  if (!metricKey) return list;
  return list.sort((left, right) => {
    const leftValue = Number(left?.[metricKey]);
    const rightValue = Number(right?.[metricKey]);
    const leftRank = Number.isFinite(leftValue) ? leftValue : Number.POSITIVE_INFINITY;
    const rightRank = Number.isFinite(rightValue) ? rightValue : Number.POSITIVE_INFINITY;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return String(right.created_at || "").localeCompare(String(left.created_at || ""));
  });
}

function updateVersionSortHeaders() {
  const activeSort = currentVersionSort();
  $$("#versions-table th[data-version-sort]").forEach((cell) => {
    const isActive = cell.dataset.versionSort === activeSort;
    cell.classList.add("sortable-head");
    cell.classList.toggle("active-sort", isActive);
    cell.dataset.sortState = isActive ? (activeSort === "created_at_desc" ? "desc" : "asc") : "";
    cell.title = isActive ? "当前排序列" : "点击按此列排序";
  });
}

function renderVersions(versions) {
  const selectedKeys = new Set(selectedVersionKeys());
  const currentVersionKey = $("#version-select")?.value || "";
  const displayVersions = sortVersionsForDisplay(versions);
  App.versions = displayVersions;
  setVersionSort(currentVersionSort());
  $("#version-select").innerHTML = displayVersions.length
    ? displayVersions.map((item) => `<option value="${htmlEscape(item.version_key)}">${htmlEscape(item.label || item.version_key)}</option>`).join("")
    : `<option value="">暂无历史模型</option>`;
  if (displayVersions.some((item) => String(item.version_key) === currentVersionKey)) {
    $("#version-select").value = currentVersionKey;
  }

  const tbody = $("#versions-table tbody");
  if (!displayVersions.length) {
    tbody.innerHTML = `<tr><td colspan="10">暂无历史模型版本</td></tr>`;
    syncSelectAllVersionsState();
    return;
  }
  tbody.innerHTML = displayVersions
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
          <td>${formatMetricCell(item.baseline_mae)}</td>
          <td>${formatMetricCell(item.baseline_rmse)}</td>
          <td>${formatMetricCell(item.final_mae)}</td>
          <td>${formatMetricCell(item.final_rmse)}</td>
          <td>${tags.join(" ") || "-"}</td>
        </tr>
      `;
    })
    .join("");
  syncSelectAllVersionsState();
  updateVersionSortHeaders();
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

function qualityStatusLabel(status) {
  return {
    clean: "无异常",
    completed_with_issues: "有异常",
    blocked: "已拦截",
  }[status] || status || "-";
}

function qualityActionLabel(action) {
  return {
    skipped: "已跳过",
    blocked: "已拦截",
    recorded: "已记录",
  }[action] || action || "-";
}

function renderQualitySummary(report) {
  const summary = report?.summary || {};
  const items = [
    ["报告状态", qualityStatusLabel(report?.status), "最近一次导入检查结果"],
    ["问题总数", summary.total_issues ?? 0, "缺失、非数字、字段不匹配等"],
    ["跳过 Sheet", summary.skipped_sheets ?? 0, "训练中未参与建模的异常天"],
    ["拦截问题", summary.blocked_issues ?? 0, "预测中导致停止的关键异常"],
  ];
  $("#quality-summary").innerHTML = items
    .map(
      ([title, value, desc]) => `
        <article class="info-card metric-card tone-blue">
          <div class="card-title">${htmlEscape(title)}</div>
          <div class="card-value">${htmlEscape(value)}</div>
          <div class="card-desc">${htmlEscape(desc)}</div>
        </article>
      `,
    )
    .join("");
}

function renderQualityReports(reports) {
  App.qualityReports = reports || [];
  const tbody = $("#quality-reports-table tbody");
  $("#quality-reports-meta").textContent = App.qualityReports.length ? `共 ${App.qualityReports.length} 份报告` : "暂无数据异常报告";
  if (!App.qualityReports.length) {
    tbody.innerHTML = `<tr><td colspan="6">暂无数据异常报告</td></tr>`;
    return;
  }
  tbody.innerHTML = App.qualityReports
    .map((report) => {
      const summary = report.summary || {};
      return `
        <tr class="clickable-row" data-report-id="${htmlEscape(report.report_id || "")}">
          <td>${htmlEscape(report.report_id || "-")}</td>
          <td>${htmlEscape(report.task_type || "-")}</td>
          <td><span class="quality-badge ${htmlEscape(report.status || "")}">${htmlEscape(qualityStatusLabel(report.status))}</span></td>
          <td>${htmlEscape(report.created_at || "-")}</td>
          <td>${htmlEscape(summary.total_issues ?? 0)}</td>
          <td>${htmlEscape(summary.skipped_sheets ?? 0)}</td>
        </tr>
      `;
    })
    .join("");
  $$("#quality-reports-table tbody tr").forEach((row) => {
    row.addEventListener("click", () => loadQualityReportDetail(row.dataset.reportId).catch((error) => showToast(error.message, "error")));
  });
}

function qualityIssueLocation(issue) {
  if (issue.location) return issue.location;
  const dateParts = [issue.year, issue.month, issue.day].filter((item) => item !== null && item !== undefined && item !== "-");
  const dateText = issue.date || (dateParts.length === 3 ? `${dateParts[0]}-${String(dateParts[1]).padStart(2, "0")}-${String(dateParts[2]).padStart(2, "0")}` : "");
  return [
    dateText,
    issue.period ? `第 ${issue.period} 点` : "",
    issue.field ? `字段：${issue.field}` : "",
    issue.sheet_name ? `Sheet：${issue.sheet_name}` : "",
    issue.excel_cell ? `单元格：${issue.excel_cell}` : "",
  ].filter(Boolean).join(" / ") || "-";
}

function renderQualityIssues(report) {
  App.latestQualityReport = report || null;
  renderQualitySummary(report);
  const issues = report?.issues || [];
  const tbody = $("#quality-issues-table tbody");
  $("#quality-issues-meta").textContent = report
    ? `${report.report_id || "-"}：共 ${issues.length} 条异常`
    : "暂无报告明细";
  if (!issues.length) {
    tbody.innerHTML = `<tr><td colspan="14">暂无异常明细</td></tr>`;
    return;
  }
  tbody.innerHTML = issues
    .map(
      (issue) => {
        const fileName = String(issue.file_path || "-").split(/[\\/]/).pop();
        const location = qualityIssueLocation(issue);
        return `
        <tr>
          <td class="quality-location" title="${htmlEscape(location)}">${htmlEscape(location)}</td>
          <td>${htmlEscape(issue.year ?? "-")}</td>
          <td>${htmlEscape(issue.month ?? "-")}</td>
          <td>${htmlEscape(issue.day ?? "-")}</td>
          <td>${htmlEscape(issue.time_point || (issue.period ? `第 ${issue.period} 点` : "-"))}</td>
          <td>${htmlEscape(issue.field || "-")}</td>
          <td>${htmlEscape(issue.excel_cell || "-")}</td>
          <td>${htmlEscape(issue.value ?? "-")}</td>
          <td>${htmlEscape(qualityActionLabel(issue.action))}</td>
          <td>${htmlEscape(issue.severity || "-")}</td>
          <td>${htmlEscape(issue.issue_type || "-")}</td>
          <td title="${htmlEscape(issue.file_path || "-")}">${htmlEscape(fileName)}</td>
          <td>${htmlEscape(issue.sheet_name || "-")}</td>
          <td>${htmlEscape(issue.message || "-")}</td>
        </tr>
      `;
      },
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
  const stack = $("#status-fab-text");
  if (!stack) return;
  const text = String(message || "").trim() || "系统待命，点击展开查看详细运行过程";
  const previous = App.tickerVisibleMessages[App.tickerVisibleMessages.length - 1];
  if (previous === text && App.tickerVisibleMessages.length) return;
  App.tickerVisibleMessages = [...App.tickerVisibleMessages, text].slice(-3);
  stack.innerHTML = App.tickerVisibleMessages
    .map((item, index, list) => {
      const newestClass = index === list.length - 1 && animate ? " newest" : "";
      return `<span class="status-ticker-line${newestClass}">${htmlEscape(item)}</span>`;
    })
    .join("");
  if (!animate) return;
  stack.classList.remove("rolling");
  void stack.offsetWidth;
  stack.classList.add("rolling");
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
  App.tickerVisibleMessages = [];
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

function orderedPredictionComparisons(prediction) {
  const comparisons = comparisonPredictions(prediction);
  const orderedKeys = [
    ...referenceStrategyOrder.filter((key) => comparisons[key]),
    ...Object.keys(comparisons).filter((key) => !referenceStrategyOrder.includes(key)),
  ];
  return orderedKeys.map((key) => [key, comparisons[key]]).filter(([, item]) => item?.rows?.length);
}

function currentReferenceDays() {
  const value = Number($("#reference-days")?.value || App.config?.default_reference_days || 1);
  const maxValue = Number(App.config?.max_reference_days || 100);
  return Number.isFinite(value) && value >= 1 ? Math.min(value, maxValue) : 1;
}

function currentTrainingMode() {
  return $("#training-mode")?.value || App.config?.default_training_mode || "rolling_window";
}

function currentTrainingWindowDays() {
  const value = Number($("#training-window-days")?.value || App.config?.default_training_window_days || 60);
  return Number.isFinite(value) && value >= 1 ? Math.round(value) : 60;
}

function currentWindowOptimizationMaxHistoryDays() {
  const value = Number(
    $("#window-optimization-max-history-days")?.value
      || App.config?.default_window_optimization_max_history_days
      || 100,
  );
  return Number.isFinite(value) && value >= 1 ? Math.round(value) : 100;
}

function currentWindowOptimizationValidDays() {
  const value = Number($("#window-optimization-valid-days")?.value || 14);
  return Number.isFinite(value) && value >= 1 ? Math.round(value) : 14;
}

function currentWindowOptimizationNumBoostRound() {
  const value = Number($("#window-optimization-num-boost-round")?.value || 400);
  return Number.isFinite(value) && value >= 1 ? Math.round(value) : 400;
}

function currentWindowOptimizationFineRadius() {
  const value = Number($("#window-optimization-fine-radius")?.value || 15);
  return Number.isFinite(value) && value >= 0 ? Math.round(value) : 15;
}

function timeToMinutes(value) {
  const match = String(value || "").trim().match(/^(\d{1,2}):([0-5]\d)$/);
  if (!match) return NaN;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour === 24 && minute === 0) return 1440;
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59 || minute % 15 !== 0) return NaN;
  return hour * 60 + minute;
}

function normalizeTimeText(value) {
  const minutes = timeToMinutes(value);
  return Number.isFinite(minutes) ? minutesToTime(minutes) : String(value || "").trim();
}

function minutesToTime(minutes) {
  const safeMinutes = Math.max(0, Math.min(1440, Number(minutes) || 0));
  const hour = Math.floor(safeMinutes / 60);
  const minute = safeMinutes % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function buildEvenSegmentRows(count) {
  const rows = [];
  const step = Math.floor(96 / count) * 15;
  let start = 0;
  for (let index = 0; index < count; index += 1) {
    const end = index === count - 1 ? 1440 : Math.max(start + 60, Math.round((index + 1) * 1440 / count / 15) * 15);
    rows.push({
      name: `segment_${index + 1}`,
      start_time: minutesToTime(start),
      end_time: minutesToTime(end),
    });
    start = end;
  }
  return rows;
}

function cloneSegmentRows(rows) {
  return (rows || []).map((row) => ({
    name: String(row.name || ""),
    start_time: normalizeTimeText(row.start_time || "00:00"),
    end_time: normalizeTimeText(row.end_time || "24:00"),
  }));
}

function loadSegmentDrafts() {
  try {
    const data = JSON.parse(localStorage.getItem(segmentDraftStorageKey) || "{}");
    return data && typeof data === "object" ? data : {};
  } catch {
    return {};
  }
}

function saveSegmentDraftForCount(count, rows) {
  if (!count || !Array.isArray(rows) || !rows.length) return;
  const drafts = loadSegmentDrafts();
  drafts[String(count)] = cloneSegmentRows(rows);
  localStorage.setItem(segmentDraftStorageKey, JSON.stringify(drafts));
}

function segmentRowsForCount(count) {
  const drafts = loadSegmentDrafts();
  const savedRows = drafts[String(count)];
  if (Array.isArray(savedRows) && savedRows.length === Number(count)) {
    return cloneSegmentRows(savedRows);
  }
  return buildEvenSegmentRows(Number(count || 5));
}

function segmentMode() {
  return $("#segment-mode")?.value || "default";
}

function validateSegmentRows(rows) {
  if (segmentMode() !== "custom") return { ok: true, message: "使用系统默认 5 段" };
  if (!rows.length) return { ok: false, message: "请至少配置 1 个时段" };
  let expectedStart = 0;
  const names = new Set();
  for (const row of rows) {
    const name = String(row.name || "").trim();
    const start = timeToMinutes(row.start_time);
    const end = timeToMinutes(row.end_time);
    if (!name) return { ok: false, message: "时段名称不能为空" };
    if (names.has(name)) return { ok: false, message: `时段名称重复：${name}` };
    names.add(name);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return { ok: false, message: "时间必须是 15 分钟粒度，例如 06:00、18:15" };
    if (start !== expectedStart) return { ok: false, message: "时段必须连续覆盖，不能空缺或重叠" };
    if (end <= start) return { ok: false, message: `${name} 的结束时间必须晚于开始时间` };
    if (end - start < 60) return { ok: false, message: `${name} 至少需要 1 小时` };
    expectedStart = end;
  }
  if (expectedStart !== 1440) return { ok: false, message: "最后一个时段必须结束于 24:00" };
  return { ok: true, message: "时段配置合法" };
}

function renderSegmentConfigTable() {
  const tbody = $("#segment-config-table tbody");
  if (!tbody) return;
  const isCustom = segmentMode() === "custom";
  const rows = isCustom ? App.segmentRows : defaultSegmentRows;
  tbody.innerHTML = rows
    .map((row, index) => `
      <tr>
        <td><input class="mini-input segment-name-input" data-index="${index}" value="${htmlEscape(row.name)}" ${isCustom ? "" : "disabled"} /></td>
        <td><input class="mini-input segment-start-input" data-index="${index}" value="${htmlEscape(row.start_time)}" disabled /></td>
        <td><input class="mini-input segment-end-input" data-index="${index}" value="${htmlEscape(row.end_time)}" ${isCustom && index < rows.length - 1 ? "" : "disabled"} /></td>
        <td>${index === rows.length - 1 ? "最后一段固定到 24:00" : "修改结束时间后，下一段自动衔接"}</td>
      </tr>
    `)
    .join("");
  const validation = validateSegmentRows(rows);
  const status = $("#segment-validation-text");
  if (status) {
    status.textContent = validation.message;
    status.classList.toggle("error-text", !validation.ok);
  }
}

function collectSegmentConfig() {
  if (segmentMode() !== "custom") return { segment_mode: "default", segment_config: null };
  const validation = validateSegmentRows(App.segmentRows);
  if (!validation.ok) {
    throw new Error(validation.message);
  }
  saveSegmentDraftForCount(App.segmentRows.length, App.segmentRows);
  return {
    segment_mode: "custom",
    segment_config: App.segmentRows.map((row) => ({
      name: row.name,
      start_time: normalizeTimeText(row.start_time),
      end_time: normalizeTimeText(row.end_time),
    })),
  };
}

function collectHighPriceWeighting() {
  return {
    enabled: Boolean($("#high-price-weight-enabled")?.checked),
    quantile: Number($("#high-price-quantile")?.value || 0.8),
    multiplier: Number($("#high-price-multiplier")?.value || 2),
  };
}

function collectTrainingAdvancedConfig() {
  return {
    ...collectSegmentConfig(),
    high_price_weighting: collectHighPriceWeighting(),
  };
}

function initializeAdvancedTrainingControls() {
  const preferences = App.config?.training_preferences || {};
  const segmentConfig = Array.isArray(preferences.segment_config) ? preferences.segment_config : defaultSegmentRows;
  App.segmentRows = segmentConfig.map((row) => ({
    name: row.name,
    start_time: row.start_time || "00:00",
    end_time: row.end_time || "24:00",
  }));
  const modeSelect = $("#segment-mode");
  if (modeSelect) modeSelect.value = preferences.segment_mode || "default";
  const countSelect = $("#segment-count");
  if (countSelect) countSelect.value = String(App.segmentRows.length || 5);
  saveSegmentDraftForCount(App.segmentRows.length || 5, App.segmentRows);
  const highConfig = preferences.high_price_weighting || {};
  if ($("#high-price-weight-enabled")) $("#high-price-weight-enabled").checked = Boolean(highConfig.enabled);
  if ($("#high-price-quantile")) $("#high-price-quantile").value = highConfig.quantile ?? 0.8;
  if ($("#high-price-multiplier")) $("#high-price-multiplier").value = highConfig.multiplier ?? 2;
  renderSegmentConfigTable();
}

function syncTrainingModeControls() {
  const isRolling = currentTrainingMode() === "rolling_window";
  const windowInput = $("#training-window-days");
  if (windowInput) windowInput.disabled = !isRolling;
  const enableStart = $("#enable-start");
  const enableEnd = $("#enable-end");
  if (enableStart) enableStart.disabled = isRolling;
  if (enableEnd) enableEnd.disabled = isRolling;
  setDatePickerDisabled("train-start-picker", isRolling || !enableStart?.checked);
  setDatePickerDisabled("train-end-picker", isRolling || !enableEnd?.checked);
}

function formatReferenceStrategyLabel(strategyKey, label, referenceDays = currentReferenceDays()) {
  const baseLabel = label || referenceStrategyLabelMap[strategyKey] || strategyKey || "-";
  return String(baseLabel).replace(/\s*N\s*/g, ` ${referenceDays} `).replace(/\s+/g, " ").trim();
}

function modelSimilarityDiff(row) {
  const value = Number(row?.model_similarity_diff);
  if (Number.isFinite(value)) return value;
  const legacyValue = Number(row?.residual_pred);
  return Number.isFinite(legacyValue) ? legacyValue : 0;
}

function syncPredictionStrategySelectors(prediction) {
  if (!prediction) return;
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
      const activeClass = prediction.selected_strategy_key === key ? " active-strategy-card" : "";
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
  const variants = orderedPredictionComparisons(prediction);
  if (!variants.length) {
    table.innerHTML = `<thead><tr><th>字段</th></tr></thead><tbody><tr><td>暂无预测数据</td></tr></tbody>`;
    return;
  }
  const primaryRows = variants[0][1].rows;
  const variantRowMaps = Object.fromEntries(
    variants.map(([key, variant]) => [
      key,
      new Map(variant.rows.map((row) => [String(row.period), row])),
    ]),
  );
  const columns = [
    "date",
    "period",
    "recent_n_days_similar_price",
    "recent_n_days_net_load_only_similar_price",
    "recent_n_days_residual_pred",
    "recent_n_days_predicted_price",
    "recent_same_type_days_similar_price",
    "recent_same_type_days_net_load_only_similar_price",
    "recent_same_type_days_residual_pred",
    "recent_same_type_days_predicted_price",
    "prediction_price_diff",
    "net_load",
  ];
  const rows = primaryRows.map((row) => {
    const periodKey = String(row.period);
    const recentRow = variantRowMaps.recent_n_days?.get(periodKey);
    const sameTypeRow = variantRowMaps.recent_same_type_days?.get(periodKey);
    const recentPrice = recentRow ? Number(recentRow.predicted_price || 0) : null;
    const sameTypePrice = sameTypeRow ? Number(sameTypeRow.predicted_price || 0) : null;
    return {
      date: row.date,
      period: row.period,
      recent_n_days_similar_price: recentRow ? Number(recentRow.similar_price || 0).toFixed(2) : "",
      recent_n_days_net_load_only_similar_price: recentRow ? Number(recentRow.net_load_only_similar_price || 0).toFixed(2) : "",
      recent_n_days_residual_pred: recentRow ? modelSimilarityDiff(recentRow).toFixed(2) : "",
      recent_n_days_predicted_price: recentPrice === null ? "" : recentPrice.toFixed(2),
      recent_same_type_days_similar_price: sameTypeRow ? Number(sameTypeRow.similar_price || 0).toFixed(2) : "",
      recent_same_type_days_net_load_only_similar_price: sameTypeRow ? Number(sameTypeRow.net_load_only_similar_price || 0).toFixed(2) : "",
      recent_same_type_days_residual_pred: sameTypeRow ? modelSimilarityDiff(sameTypeRow).toFixed(2) : "",
      recent_same_type_days_predicted_price: sameTypePrice === null ? "" : sameTypePrice.toFixed(2),
      prediction_price_diff: recentPrice === null || sameTypePrice === null ? "" : (sameTypePrice - recentPrice).toFixed(2),
      net_load: row.net_load,
    };
  });
  const head = `<thead><tr>${columns.map((col) => `<th>${htmlEscape(columnTitleMap[col] || col)}</th>`).join("")}</tr></thead>`;
  const body = rows
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

function resizePredictionCharts() {
  Object.values(App.charts || {}).forEach((chart) => {
    if (chart) chart.resize();
  });
}

function ensureChart(strategyKey) {
  if (!window.echarts) return null;
  const config = predictionChartConfigMap[strategyKey];
  const target = config ? $(`#${config.elementId}`) : null;
  if (!target) return null;
  if (!App.charts[strategyKey]) {
    App.charts[strategyKey] = window.echarts.init(target);
    if (!App.chartResizeBound) {
      window.addEventListener("resize", () => resizePredictionCharts());
      App.chartResizeBound = true;
    }
  }
  return App.charts[strategyKey];
}

function renderPredictionStats(prediction) {
  const target = $("#prediction-stats");
  const variants = orderedPredictionComparisons(prediction);
  if (!variants.length) {
    target.innerHTML = "";
    return;
  }

  target.innerHTML = variants
    .flatMap(([key, variant]) => {
      const values = variant.rows.map((row) => Number(row.predicted_price || 0));
      const minValue = Math.min(...values);
      const maxValue = Math.max(...values);
      const avgValue = values.reduce((sum, item) => sum + item, 0) / Math.max(1, values.length);
      const referenceDays = variant.reference_days_requested || (variant.reference_dates || []).length || currentReferenceDays();
      const strategyLabel = formatReferenceStrategyLabel(key, variant.reference_strategy_label, referenceDays);
      const referenceLabel = (variant.reference_dates || []).join(" / ") || "-";
      return [
        `${strategyLabel}均价：${avgValue.toFixed(2)}`,
        `${strategyLabel}范围：${minValue.toFixed(2)} ~ ${maxValue.toFixed(2)}`,
        `${strategyLabel}参考日：${referenceLabel}`,
      ];
    })
    .map((text) => `<span class="chart-stat">${text}</span>`)
    .join("");
}

function renderPredictionChart(prediction) {
  renderPredictionStats(prediction);
  const variants = orderedPredictionComparisons(prediction);
  const variantMap = Object.fromEntries(variants);
  if (!variants.length) {
    if (App.predictionChartSignature !== "") {
      Object.values(App.charts).forEach((chart) => chart?.clear());
      App.predictionChartSignature = "";
    }
    $("#prediction-meta").textContent = "暂无预测数据";
    return;
  }

  const primaryVariant = variantMap.recent_n_days || variants[0][1];
  const forecastDate = primaryVariant.forecast_date || primaryVariant.rows?.[0]?.date || "-";
  const referenceDays = primaryVariant.reference_days_requested || (primaryVariant.reference_dates || []).length || currentReferenceDays();
  const chartSignature = JSON.stringify(variants.map(([key, variant]) => [key, predictionVariantSignature(variant)]));

  if (App.predictionChartSignature !== chartSignature) {
    referenceStrategyOrder.forEach((strategyKey) => {
      renderStrategyChart(strategyKey, variantMap[strategyKey], referenceDays);
    });
    App.predictionChartSignature = chartSignature;
    requestAnimationFrame(() => resizePredictionCharts());
  }

  $("#prediction-meta").textContent = `预测日期：${forecastDate} | 参考天数：${referenceDays} 天 | 已同时展示最近天与同类型日两种预测`;
}

function renderStrategyChart(strategyKey, variant, referenceDays) {
  const chart = ensureChart(strategyKey);
  if (!chart) return;
  if (!variant?.rows?.length) {
    chart.clear();
    return;
  }

  const config = predictionChartConfigMap[strategyKey];
  const rows = variant.rows;
  const periods = rows.map((row) => row.period);
  const predicted = rows.map((row) => Number(row.predicted_price || 0));
  const similar = rows.map((row) => Number(row.similar_price || 0));
  const netLoadOnlySimilar = rows.map((row) => {
    const value = Number(row.net_load_only_similar_price);
    return Number.isFinite(value) ? value : null;
  });
  const diff = rows.map((row) => modelSimilarityDiff(row));
  const predictedName = formatReferenceStrategyLabel(strategyKey, config.predictedName, referenceDays);
  const similarName = formatReferenceStrategyLabel(strategyKey, config.similarName, referenceDays);
  const netLoadOnlyName = formatReferenceStrategyLabel(strategyKey, config.netLoadOnlyName, referenceDays);
  const diffName = formatReferenceStrategyLabel(strategyKey, config.residualName, referenceDays);

  chart.setOption(
    {
      backgroundColor: "transparent",
      animationDuration: 500,
      color: ["#1677ff", "#52c41a", "#722ed1", "#fa8c16"],
      tooltip: {
        trigger: "axis",
        triggerOn: "mousemove|click",
        axisPointer: { type: "cross" },
        backgroundColor: "rgba(17,24,39,0.92)",
        borderWidth: 0,
        confine: true,
        hideDelay: 120,
        textStyle: { color: "#ffffff" },
        formatter(params) {
          const items = Array.isArray(params) ? params : [params];
          const title = items[0]?.axisValueLabel ?? items[0]?.name ?? "";
          const lines = items
            .filter((item) => item?.value !== null && item?.value !== undefined && item?.value !== "")
            .map(
              (item) =>
                `${item.marker || ""}<span style="margin-right:12px;">${item.seriesName}</span><strong>${formatChartTooltipValue(item.value)}</strong>`,
            )
            .join("<br/>");
          return `<div style="font-weight:800;margin-bottom:6px;">${title}</div>${lines}`;
        },
      },
      legend: {
        top: 8,
        textStyle: { color: "#4e5969" },
        data: [predictedName, similarName, netLoadOnlyName, diffName],
      },
      grid: [
        { left: 54, right: 38, top: 52, height: 210 },
        { left: 54, right: 38, top: 292, height: 74 },
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
          name: "差值",
          axisLabel: { color: "#86909c" },
          splitLine: { show: false },
        },
      ],
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1], start: 0, end: 100, zoomOnMouseWheel: false, moveOnMouseWheel: false },
        { type: "slider", xAxisIndex: [0, 1], bottom: 0, height: 18, borderColor: "transparent" },
      ],
      series: [
        {
          name: predictedName,
          type: "line",
          smooth: false,
          symbol: "circle",
          symbolSize: 5,
          lineStyle: { width: 3 },
          areaStyle: { color: "rgba(22,119,255,0.08)" },
          data: predicted,
        },
        {
          name: similarName,
          type: "line",
          smooth: false,
          symbol: "none",
          lineStyle: { width: 2, type: "dashed" },
          data: similar,
        },
        {
          name: netLoadOnlyName,
          type: "line",
          smooth: false,
          symbol: "none",
          lineStyle: { width: 2, type: "dotted" },
          data: netLoadOnlySimilar,
        },
        {
          name: diffName,
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          barMaxWidth: 10,
          data: diff,
        },
      ],
    },
    true,
  );
}

function applyProgressCard(key, state) {
  const card = $(`#${key}-progress-card`);
  const text = $(`#${key}-progress-text`);
  const status = $(`#${key}-progress-status`);
  const fill = $(`#${key}-progress-fill`);
  if (!card || !text || !status || !fill) return;
  const progress = Math.max(0, Math.min(100, Number(state.progress || 0)));
  fill.style.width = `${progress}%`;
  text.textContent = state.label || `${progress}%`;
  status.textContent = state.status || "\u7b49\u5f85\u4e2d";
  card.classList.remove("running", "success", "error");
  if (state.type) card.classList.add(state.type);
}

function deriveJobState(job, mode) {
  const idleTextMap = {
    train: "\u7b49\u5f85\u624b\u52a8\u91cd\u8bad",
    optimize: "\u7b49\u5f85\u81ea\u52a8\u5bfb\u4f18",
    predict: "\u7b49\u5f85\u6267\u884c\u9884\u6d4b",
  };
  const idleText = idleTextMap[mode] || "\u7b49\u5f85\u4e2d";
  if (!job) {
    return { progress: 0, label: "\u672a\u5f00\u59cb", status: idleText, type: "" };
  }
  if (job.cancelled) {
    return { progress: Number(job.progress || 0), label: "\u5df2\u505c\u6b62", status: job.status || "\u4efb\u52a1\u5df2\u505c\u6b62", type: "error" };
  }
  if (job.error) {
    return { progress: Math.max(1, Number(job.progress || 0)), label: "\u6267\u884c\u5931\u8d25", status: job.error.split("\n")[0], type: "error" };
  }
  if (job.running) {
    return { progress: Number(job.progress || 0), label: `${job.progress || 0}%`, status: job.status || "\u6267\u884c\u4e2d", type: "running" };
  }
  return { progress: 100, label: "\u5df2\u5b8c\u6210", status: job.status || "\u6267\u884c\u5b8c\u6210", type: "success" };
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
  applyProgressCard("optimize", deriveJobState(App.jobStates.optimize, "optimize"));
  applyProgressCard("train", deriveJobState(App.jobStates.train, "train"));
  applyProgressCard("predict", deriveJobState(App.jobStates.predict, "predict"));
  syncStopButtons();
}

function syncStopButtons() {
  const states = {
    optimize: Boolean(App.activeJobIds.optimize && App.jobStates.optimize?.running),
    train: Boolean(App.activeJobIds.train && App.jobStates.train?.running),
    predict: Boolean(App.activeJobIds.predict && App.jobStates.predict?.running),
  };
  $("#stop-optimize-btn")?.classList.toggle("hidden", !states.optimize);
  $("#stop-train-btn")?.classList.toggle("hidden", !states.train);
  $("#stop-predict-btn")?.classList.toggle("hidden", !states.predict);
}

function setPendingState(mode, title) {
  const key = mode || "train";
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
  const currentJob = getFocusedJobState() || statusData?.current_job || null;
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

async function pollJobUntilDone(jobId) {
  let job = null;
  for (let i = 0; i < 600; i++) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    try {
      job = await request(`/api/jobs/${jobId}`);
    } catch {
      continue;
    }
    if (!job || !job.running) break;
  }
  return job;
}

async function refreshTrackedJobs() {
  const modes = ["train", "predict", "optimize"];
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
  App.activeJobIds = { train: null, predict: null, optimize: null };
  App.jobStates = { train: null, predict: null, optimize: null };
  App.statusFocus = null;
  App.predictSessionStarted = false;
  renderProgressSections();
  renderStatusPanel({});
  renderPredictionBundle(null);
}

async function loadConfig() {
  App.config = await request("/api/config");
  if ($("#training-mode") && App.config?.default_training_mode) {
    $("#training-mode").value = App.config.default_training_mode;
  }
  if ($("#training-window-days") && App.config?.default_training_window_days) {
    $("#training-window-days").value = App.config.default_training_window_days;
  }
  if ($("#window-optimization-max-history-days") && App.config?.default_window_optimization_max_history_days) {
    $("#window-optimization-max-history-days").value = App.config.default_window_optimization_max_history_days;
  }
  if ($("#reference-days") && App.config?.default_reference_days && !$("#reference-days").value) {
    $("#reference-days").value = App.config.default_reference_days;
  }
  const weights = App.config?.default_similarity_weights || {};
  [
    ["#similarity-weight-net-load", "thermal_space"],
    ["#similarity-weight-renewable-power", "renewable_power"],
    ["#similarity-weight-thermal-on-capacity", "thermal_on_capacity"],
    ["#similarity-weight-day-type", "day_type"],
    ["#similarity-weight-ratio", "thermal_space_load_ratio"],
  ].forEach(([selector, key]) => {
    if ($(selector) && weights[key] !== undefined) {
      $(selector).value = weights[key];
    }
  });
  syncTrainingModeControls();
  renderConfigPaths();
}

function collectSimilarityWeights() {
  return {
    thermal_space: Number($("#similarity-weight-net-load")?.value || 0),
    renewable_power: Number($("#similarity-weight-renewable-power")?.value || 0),
    thermal_on_capacity: Number($("#similarity-weight-thermal-on-capacity")?.value || 0),
    day_type: Number($("#similarity-weight-day-type")?.value || 0),
    thermal_space_load_ratio: Number($("#similarity-weight-ratio")?.value || 0),
  };
}

async function savePredictionPreferences() {
  await request("/api/prediction/preferences", {
    method: "POST",
    body: JSON.stringify({ similarity_weights: collectSimilarityWeights() }),
  });
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
  renderModelComparison(currentModel.metadata || {});
  renderRollingBacktest(currentModel.metadata || {});
  renderModelHealth(currentModel.metadata || {});
  renderDailyErrorRank(currentModel.metadata || {});
  if (App.predictSessionStarted && statusData.last_prediction?.rows?.length) {
    renderPredictionBundle(statusData.last_prediction);
  }
}

async function loadLogs() {
  const data = await request("/api/training/logs");
  renderTrainingLogs(data.logs || []);
}

async function loadQualityReportDetail(reportId) {
  if (!reportId) return;
  const data = await request(`/api/data-quality/reports/${encodeURIComponent(reportId)}`);
  renderQualityIssues(data.report || null);
}

async function loadDataQuality() {
  const [reportsData, latestData] = await Promise.all([
    request("/api/data-quality/reports"),
    request("/api/data-quality/reports/latest"),
  ]);
  renderQualityReports(reportsData.reports || []);
  renderQualityIssues(latestData.report || null);
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
  const originalText = btn?.textContent || "手动重训模型";
  try {
    setButtonLoading(btn, true, originalText);
    setPendingState("train", "正在提交训练任务...");
    const data = await request("/api/train", {
      method: "POST",
      body: JSON.stringify({
        training_mode: currentTrainingMode(),
        training_window_days: currentTrainingWindowDays(),
        start_date: $("#train-start-date").value || null,
        end_date: $("#train-end-date").value || null,
        enable_start: $("#enable-start").checked,
        enable_end: $("#enable-end").checked,
        valid_days: Number($("#valid-days").value || 14),
        num_boost_round: Number($("#num-boost-round").value || 400),
        ...collectTrainingAdvancedConfig(),
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
    syncStopButtons();
    applyProgressCard("train", { progress: 5, label: "训练中", status: `训练任务已启动：${data.job_id}`, type: "running" });
    showToast(`已启动训练任务：${data.job_id}，等待完成...`);
    const job = await pollJobUntilDone(data.job_id);
    if (!job) {
      App.activeJobIds.train = null;
      syncStopButtons();
      applyProgressCard("train", { progress: 0, label: "超时", status: "训练超时（等待超过 15 分钟）", type: "error" });
      showToast("训练超时，请检查服务器状态", "error");
      return;
    }
    App.jobStates.train = job;
    App.activeJobIds.train = null;
    syncStopButtons();
    if (job.error) {
      applyProgressCard("train", { progress: job.progress || 0, label: "失败", status: job.error, type: "error" });
      showToast(`训练失败：${job.error.split("\n")[0]}`, "error");
    } else if (job.cancelled) {
      applyProgressCard("train", { progress: job.progress || 0, label: "已停止", status: "训练已停止", type: "error" });
      showToast("训练已停止");
    } else {
      applyProgressCard("train", { progress: 100, label: "已完成", status: "训练完成", type: "success" });
      showToast("训练已完成");
    }
    await refreshSummary();
    await loadDataQuality();
  } catch (error) {
    showToast(error.message, "error");
    applyProgressCard("train", { progress: 0, label: "错误", status: error.message, type: "error" });
  } finally {
    const el = $("#train-btn");
    if (el) setButtonLoading(el, false, originalText);
    syncStopButtons();
  }
}

async function startWindowOptimization() {
  const btn = $("#optimize-window-btn");
  const originalText = btn?.textContent || "自动寻优训练窗口";
  try {
    setButtonLoading(btn, true, originalText);
    App.statusFocus = "optimize";
    App.pendingStatus = {
      job_type: "optimize",
      progress: 3,
      status: "正在提交训练窗口自动寻优任务...",
      logs: ["[本地] 正在提交训练窗口自动寻优任务..."],
      running: true,
    };
    applyProgressCard("optimize", { progress: 3, label: "\u63d0\u4ea4\u4e2d", status: "\u6b63\u5728\u63d0\u4ea4\u8bad\u7ec3\u7a97\u53e3\u81ea\u52a8\u5bfb\u4f18\u4efb\u52a1...", type: "running" });
    renderStatusPanel({ current_job: App.pendingStatus, recent_jobs: [] });
    const data = await request("/api/window-optimization/run", {
      method: "POST",
      body: JSON.stringify({
        force: true,
        max_history_days: currentWindowOptimizationMaxHistoryDays(),
        valid_days: currentWindowOptimizationValidDays(),
        num_boost_round: currentWindowOptimizationNumBoostRound(),
        fine_radius: currentWindowOptimizationFineRadius(),
        ...collectTrainingAdvancedConfig(),
      }),
    });
    if (data.started && data.job?.job_id) {
      App.activeJobIds.optimize = data.job.job_id;
      App.jobStates.optimize = {
        job_id: data.job.job_id,
        job_type: "optimize",
        progress: 5,
        status: `训练窗口自动寻优已启动：${data.job.job_id}`,
        logs: [`[本地] 训练窗口自动寻优已启动：${data.job.job_id}`],
        running: true,
      };
      App.pendingStatus = null;
      syncStopButtons();
      applyProgressCard("optimize", { progress: 5, label: "\u5bfb\u4f18\u4e2d", status: `\u8bad\u7ec3\u7a97\u53e3\u81ea\u52a8\u5bfb\u4f18\u5df2\u542f\u52a8\uff1a${data.job.job_id}`, type: "running" });
      showToast("训练窗口自动寻优已启动");
    } else {
      App.pendingStatus = null;
      applyProgressCard("optimize", deriveJobState(App.jobStates.optimize, "optimize"));
      showToast(data.reason === "job_running" ? "当前已有任务运行，稍后再试" : "历史数据未变化，无需重新寻优");
    }
    await refreshSummary();
  } catch (error) {
    App.pendingStatus = null;
    showToast(error.message, "error");
  } finally {
    setButtonLoading(btn, false, originalText);
    syncStopButtons();
  }
}

async function startPredict() {
  const btn = $("#predict-btn");
  const originalText = btn?.textContent || "执行预测";
  try {
    setButtonLoading(btn, true, originalText);
    App.predictSessionStarted = true;
    setPendingState("predict", "正在保存并提交预测任务...");
    await saveTemplate();
    const similarityWeights = collectSimilarityWeights();
    await savePredictionPreferences();
    const data = await request("/api/predict", {
      method: "POST",
      body: JSON.stringify({
        reference_days: currentReferenceDays(),
        similarity_weights: similarityWeights,
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
    syncStopButtons();
    applyProgressCard("predict", { progress: 5, label: "预测中", status: `预测任务已启动：${data.job_id}`, type: "running" });
    showToast(`已启动预测任务：${data.job_id}，等待完成...`);
    const job = await pollJobUntilDone(data.job_id);
    if (!job) {
      App.activeJobIds.predict = null;
      syncStopButtons();
      applyProgressCard("predict", { progress: 0, label: "超时", status: "预测超时（等待超过 15 分钟）", type: "error" });
      showToast("预测超时，请检查服务器状态", "error");
      return;
    }
    App.jobStates.predict = job;
    App.activeJobIds.predict = null;
    syncStopButtons();
    if (job.error) {
      applyProgressCard("predict", { progress: job.progress || 0, label: "失败", status: job.error, type: "error" });
      showToast(`预测失败：${job.error.split("\n")[0]}`, "error");
    } else if (job.cancelled) {
      applyProgressCard("predict", { progress: job.progress || 0, label: "已停止", status: "预测已停止", type: "error" });
      showToast("预测已停止");
    } else {
      applyProgressCard("predict", { progress: 100, label: "已完成", status: "预测完成", type: "success" });
      showToast("预测已完成");
    }
    await refreshSummary();
    await loadDataQuality();
  } catch (error) {
    showToast(error.message, "error");
    applyProgressCard("predict", { progress: 0, label: "错误", status: error.message, type: "error" });
  } finally {
    const el = $("#predict-btn");
    if (el) setButtonLoading(el, false, originalText);
    syncStopButtons();
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

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size >= 10 || unitIndex === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unitIndex]}`;
}

async function cleanupOutputJunk() {
  const confirmed = window.confirm("将清理 output 寻优中间结果、旧异常报告和临时缓存；不会删除模型、历史数据和最新预测结果。确认清理吗？");
  if (!confirmed) return;
  const btn = $("#cleanup-output-btn");
  setButtonLoading(btn, true);
  try {
    const data = await request("/api/cleanup/output", { method: "POST", body: JSON.stringify({}) });
    const summary = `已清理 ${formatBytes(data.total_bytes)} / ${data.total_files || 0} 个文件，保留最新预测结果、模型和最新异常报告。`;
    const target = $("#cleanup-output-summary");
    if (target) target.textContent = summary;
    showToast(summary);
    await Promise.allSettled([refreshSummary(), loadDataQuality()]);
  } finally {
    setButtonLoading(btn, false, "一键清理垃圾");
  }
}

function toggleStatusPanel(hidden) {
  const wrapper = $("#sidebar-status");
  if (wrapper) {
    wrapper.classList.toggle("collapsed", hidden);
    wrapper.classList.toggle("expanded", !hidden);
  }
  $("#status-panel")?.classList.toggle("hidden-panel", hidden);
  $("#status-fab")?.classList.toggle("hidden", false);
}

async function cancelJob(mode) {
  const jobId = App.activeJobIds[mode];
  if (!jobId) {
    showToast("当前没有正在执行的任务", "error");
    return;
  }
  const stopButtonMap = {
    optimize: $("#stop-optimize-btn"),
    train: $("#stop-train-btn"),
    predict: $("#stop-predict-btn"),
  };
  const stopButton = stopButtonMap[mode] || $("#stop-train-btn");
  const originalText = stopButton?.textContent || "停止任务";
  try {
    if (stopButton) {
      stopButton.disabled = true;
      stopButton.textContent = "停止中...";
    }
    let job;
    try {
      job = await request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: JSON.stringify({}) });
    } catch (error) {
      if (!String(error.message || "").includes("未找到接口")) {
        throw error;
      }
      job = await request("/api/jobs/cancel", { method: "POST", body: JSON.stringify({ job_id: jobId }) });
    }
    App.jobStates[mode] = job;
    App.statusFocus = mode;
    renderProgressSections();
    renderStatusPanel({ current_job: job, recent_jobs: [] });
    updateStatusTicker(["已发送停止请求，等待任务安全中断"], false);
    showToast("已发送停止请求");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    if (stopButton) {
      stopButton.disabled = false;
      stopButton.textContent = originalText;
    }
  }
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
  if (!App.datePickers[pickerId]) return;
  App.datePickers[pickerId].disabled = disabled;
  if (disabled) {
    App.datePickers[pickerId].open = false;
    App.datePickers[pickerId].panelMode = "day";
  }
  renderDatePicker(pickerId);
}

function applyPredictionChartLayout(layout) {
  const grid = $("#prediction-chart-grid");
  if (!grid) return;
  App.predictionChartLayout = layout === "side-by-side" ? "side-by-side" : "stacked";
  grid.classList.toggle("prediction-chart-grid-side-by-side", App.predictionChartLayout === "side-by-side");
  $$("[data-chart-layout]").forEach((button) => {
    button.classList.toggle("active", button.dataset.chartLayout === App.predictionChartLayout);
  });
  window.setTimeout(() => resizePredictionCharts(), 260);
}

function setPredictionChartLayout(layout) {
  applyPredictionChartLayout(layout);
  localStorage.setItem(predictionChartLayoutStorageKey, App.predictionChartLayout);
}

function initPredictionChartLayout() {
  const savedLayout = localStorage.getItem(predictionChartLayoutStorageKey);
  applyPredictionChartLayout(savedLayout || App.predictionChartLayout);
}

function bindEvents() {
  $$(".tab-btn").forEach((btn) => btn.addEventListener("click", () => setActiveTab(btn.dataset.tab)));
  $("#cleanup-output-btn")?.addEventListener("click", () => cleanupOutputJunk().catch((error) => showToast(error.message, "error")));
  $("#train-btn").addEventListener("click", () => startTrain().catch((error) => showToast(error.message, "error")));
  $("#optimize-window-btn")?.addEventListener("click", () => startWindowOptimization().catch((error) => showToast(error.message, "error")));
  $("#stop-optimize-btn")?.addEventListener("click", () => cancelJob("optimize"));
  $("#stop-train-btn").addEventListener("click", () => cancelJob("train"));
  $("#refresh-train-metrics-btn").addEventListener("click", () => refreshSummary().then(() => showToast("当前指标已刷新")).catch((error) => showToast(error.message, "error")));
  $("#reload-template-btn").addEventListener("click", () => loadTemplate().then(() => showToast("预测文件已重新加载")).catch((error) => showToast(error.message, "error")));
  $("#save-template-btn").addEventListener("click", () => saveTemplate().catch((error) => showToast(error.message, "error")));
  $("#predict-btn").addEventListener("click", () => startPredict().catch((error) => showToast(error.message, "error")));
  $("#stop-predict-btn").addEventListener("click", () => cancelJob("predict"));
  $("#refresh-quality-btn")?.addEventListener("click", () => loadDataQuality().then(() => showToast("数据异常报告已刷新")).catch((error) => showToast(error.message, "error")));
  $$("#prediction-chart-layout-control [data-chart-layout]").forEach((button) => {
    button.addEventListener("click", () => setPredictionChartLayout(button.dataset.chartLayout));
  });
  $("#activate-version-btn").addEventListener("click", () => activateVersion().catch((error) => showToast(error.message, "error")));
  $("#rollback-btn").addEventListener("click", () => rollbackVersion().catch((error) => showToast(error.message, "error")));
  $("#delete-versions-btn").addEventListener("click", () => deleteSelectedVersions().catch((error) => showToast(error.message, "error")));
  $("#version-sort").addEventListener("change", () => renderVersions(App.versions || []));
  $("#versions-table").addEventListener("click", (event) => {
    const header = event.target.closest("th[data-version-sort]");
    if (!header) return;
    setVersionSort(header.dataset.versionSort);
    renderVersions(App.versions || []);
  });
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
  $("#training-mode")?.addEventListener("change", () => syncTrainingModeControls());
  $("#segment-mode")?.addEventListener("change", () => renderSegmentConfigTable());
  $("#segment-count")?.addEventListener("change", (event) => {
    saveSegmentDraftForCount(App.segmentRows.length, App.segmentRows);
    App.segmentRows = segmentRowsForCount(Number(event.target.value || 5));
    renderSegmentConfigTable();
  });
  $("#segment-config-table")?.addEventListener("change", (event) => {
    const index = Number(event.target.dataset.index);
    if (!Number.isInteger(index) || !App.segmentRows[index]) return;
    if (event.target.matches(".segment-name-input")) {
      App.segmentRows[index].name = event.target.value.trim();
    }
    if (event.target.matches(".segment-end-input")) {
      App.segmentRows[index].end_time = normalizeTimeText(event.target.value);
      if (App.segmentRows[index + 1]) {
        App.segmentRows[index + 1].start_time = App.segmentRows[index].end_time;
      }
    }
    saveSegmentDraftForCount(App.segmentRows.length, App.segmentRows);
    renderSegmentConfigTable();
  });
  $("#enable-start").addEventListener("change", (event) => {
    if (currentTrainingMode() === "rolling_window") {
      syncTrainingModeControls();
      return;
    }
    setDatePickerDisabled("train-start-picker", !event.target.checked);
  });
  $("#enable-end").addEventListener("change", (event) => {
    if (currentTrainingMode() === "rolling_window") {
      syncTrainingModeControls();
      return;
    }
    setDatePickerDisabled("train-end-picker", !event.target.checked);
  });
  [
    "#similarity-weight-net-load",
    "#similarity-weight-renewable-power",
    "#similarity-weight-thermal-on-capacity",
    "#similarity-weight-day-type",
    "#similarity-weight-ratio",
  ].forEach((selector) => {
    $(selector)?.addEventListener("change", () => {
      savePredictionPreferences().catch((error) => showToast(error.message, "error"));
    });
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
  initializeAdvancedTrainingControls();
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
  if (!btn) return;
  if (loading) {
    btn.dataset.originalText = btn.textContent;
    btn.dataset.originalWidth = `${btn.offsetWidth}`;
    btn.style.width = `${btn.offsetWidth}px`;
    btn.style.minWidth = `${btn.offsetWidth}px`;
    btn.setAttribute("aria-busy", "true");
    btn.classList.add("loading");
    btn.textContent = "执行中...";
    btn.disabled = true;
  } else {
    btn.classList.remove("loading");
    btn.textContent = btn.dataset.originalText || originalText || btn.textContent;
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
    btn.style.width = "";
    btn.style.minWidth = "";
    delete btn.dataset.originalText;
    delete btn.dataset.originalWidth;
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
  $$(".strategy-chart-stage").forEach((stage) => {
    stage.innerHTML = `
    <div class="chart-loading">
      <div class="chart-spinner"></div>
      <span style="color: var(--text-3); font-size: 13px;">正在加载图表...</span>
    </div>`;
  });
}

function showChartEmpty(message = "尚未执行预测") {
  $$(".strategy-chart-stage").forEach((stage) => {
    stage.innerHTML = `
    <div class="chart-empty">
      <div class="chart-empty-icon">📊</div>
      <span>${htmlEscape(message)}</span>
    </div>`;
  });
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
  const btn = document.querySelector(".mode-pill") || document.createElement("button");
  if (!btn.classList.contains("mode-pill")) {
    btn.className = "ghost-btn mini-btn";
    btn.style.cssText = "position:fixed;top:18px;right:18px;z-index:1100;";
    document.body.appendChild(btn);
  }
  btn.textContent = root.classList.contains("dark-enabled") ? "浅色模式" : "暗色模式";
  btn.title = "切换暗色模式";
  btn.setAttribute("role", "button");
  btn.tabIndex = 0;
  btn.style.cursor = "pointer";
  btn.addEventListener("click", () => {
    const isDark = root.classList.toggle("dark-enabled");
    localStorage.setItem("dayahead-dark-mode", String(isDark));
    btn.textContent = isDark ? "浅色模式" : "暗色模式";
    if (Object.keys(App.charts).length) {
      Object.values(App.charts).forEach((chart) => chart?.dispose());
      App.charts = {};
      App.predictionChartSignature = null;
      if (App.lastPrediction) {
        renderPredictionChart(App.lastPrediction);
      }
    }
  });
  btn.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      btn.click();
    }
  });
}

function updateUiClock() {
  const target = $("#ui-clock");
  if (!target) return;
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  target.textContent = formatter.format(new Date());
}

function initUiClock() {
  updateUiClock();
  setInterval(updateUiClock, 1000);
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
  initUiClock();
  initDarkModeToggle();
  initPredictionChartLayout();
  bindHelpPopoverEvents();
  await loadHelpContent();
  injectHelpAffordances();

  try {
    await initialLoad();
    injectHelpAffordances();
    startPolling();
    initAutoRefresh();
    injectTableToolbarActions();
  } catch (error) {
    showToast(error.message, "error");
  }
});
