const App = {
  config: null,
  versions: [],
  templateRows: [],
  multiDayTemplateRows: [],
  pollTimer: null,
  charts: {},
  multiDayCharts: {},
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
    "realtime-optimize": null,
    "dual-optimize": null,
    "predict-multi-day": null,
  },
  jobStates: {
    train: null,
    predict: null,
    optimize: null,
    "realtime-optimize": null,
    "dual-optimize": null,
    "predict-multi-day": null,
  },
  statusFocus: null,
  predictSessionStarted: false,
  multiDaySessionStarted: false,
  lastPrediction: null,
  lastMultiDayPrediction: null,
  thermalCapacityPreview: null,
  predictionChartSignature: null,
  multiDayPredictionSignature: null,
  qualityReports: [],
  latestQualityReport: null,
  segmentRows: [],
  realtimeSegmentRows: [],
  priceIntervals: [],
  realtimePriceIntervals: [],
  modelCandidateRankings: null,
  selectedSegmentPriceModels: {},
  currentModelMetadata: null,
  predictionArchiveRecords: [],
  predictionArchiveDetail: null,
  archiveChart: null,
  openVersionDetailKeys: new Set(),
  versionTarget: "dayahead",
  versionModelMetadata: null,
  modelVersionsByTarget: { dayahead: [], realtime: [] },
  modelMetadataByTarget: { dayahead: {}, realtime: {} },
};
const ProgressState = window.progressStateHelpers || {};

const defaultSegmentCount = 6;
const defaultSegmentRows = buildEvenSegmentRows(defaultSegmentCount);
const segmentDraftStorageKey = "dayahead_segment_drafts_by_count";
const segmentSearchCountsStorageKey = "dayahead_segment_search_counts_v2";
const priceIntervalMin = 0;
const priceIntervalMax = 1500;
const defaultPriceIntervals = [
  { label: "0-250", min: 0, max: 250 },
  { label: "250-300", min: 250, max: 300 },
  { label: "300-400", min: 300, max: 400 },
  { label: "400-600", min: 400, max: 600 },
  { label: "600-1000", min: 600, max: 1000 },
  { label: "1000-1500", min: 1000, max: 1500 },
];

function trainingTargetPrefix(target = "dayahead") {
  return target === "realtime" ? "realtime-" : "";
}

function trainingSegmentRows(target = "dayahead") {
  return target === "realtime" ? App.realtimeSegmentRows : App.segmentRows;
}

function setTrainingSegmentRows(target = "dayahead", rows = []) {
  if (target === "realtime") {
    App.realtimeSegmentRows = rows;
  } else {
    App.segmentRows = rows;
  }
}

function trainingPriceIntervals(target = "dayahead") {
  return target === "realtime" ? App.realtimePriceIntervals : App.priceIntervals;
}

function setTrainingPriceIntervals(target = "dayahead", rows = []) {
  if (target === "realtime") {
    App.realtimePriceIntervals = rows;
  } else {
    App.priceIntervals = rows;
  }
}

const columnTitleMap = {
  scenario_similarity_adjusted_price: "场景相似法修正参考价",
  similarity_blend_weight: "相似法权重",
  similarity_adjustment: "相似法修正值",
  similarity_adjustment_reason: "相似法修正原因",
  recent_n_days_scenario_similarity_adjusted_price: "最近 N 天场景修正参考价",
  recent_n_days_similarity_blend_weight: "最近 N 天相似法权重",
  recent_n_days_similarity_adjustment_reason: "最近 N 天修正原因",
  recent_same_type_days_scenario_similarity_adjusted_price: "同类型日场景修正参考价",
  recent_same_type_days_similarity_blend_weight: "同类型日相似法权重",
  recent_same_type_days_similarity_adjustment_reason: "同类型日修正原因",
  date: "日期",
  period: "时段",
  segment: "分时段",
  hour: "小时",
  net_load: "火电空间",
  thermal_on_capacity: "火电开机容量(MW)",
  net_load_only_similar_price: "净负荷相似法预测价格",
  knn_similar_price: "KNN相似法预测价格",
  weighted_knn_regression_price: "加权KNN回归预测价格",
  residual_pred: "模型差值（模型预测-净负荷相似法）",
  model_similarity_diff: "模型差值（模型预测-净负荷相似法）",
  predicted_price: "模型预测价格",
  realtime_predicted_price: "实时模型预测价格",
  realtime_model_variant: "实时模型变体",
  predicted_interval: "最可能价格区间",
  predicted_interval_probability: "价格区间概率",
  high_price_probability: "高价概率",
  interval_backtest_accuracy: "区间历史命中率",
  price_interval_consistency: "一致性提示",
  recent_n_days_net_load_only_similar_price: "最近 N 天净负荷相似法预测价格",
  recent_n_days_knn_similar_price: "最近 N 天KNN相似法预测价格",
  recent_n_days_weighted_knn_regression_price: "最近 N 天加权KNN回归预测价格",
  recent_n_days_predicted_price: "最近 N 天模型预测价格",
  recent_n_days_realtime_predicted_price: "最近 N 天实时模型预测价格",
  recent_same_type_days_net_load_only_similar_price: "同类型日净负荷相似法预测价格",
  recent_same_type_days_knn_similar_price: "同类型日KNN相似法预测价格",
  recent_same_type_days_weighted_knn_regression_price: "同类型日加权KNN回归预测价格",
  recent_same_type_days_predicted_price: "同类型日模型预测价格",
  recent_same_type_days_realtime_predicted_price: "同类型日实时模型预测价格",
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
    netLoadOnlyName: "净负荷相似法预测价格",
    showDiff: false,
  },
  recent_same_type_days: {
    elementId: "prediction-chart-same-type-days",
    predictedName: "模型预测价格",
    netLoadOnlyName: "净负荷相似法预测价格",
    showDiff: false,
  },
};
const predictionChartLayoutStorageKey = "dayahead-prediction-chart-layout";

const helpContentUrl = "/assets/help-content.json";

const modelRankingHelpContent = {
  最近天数: {
    title: "最近天数",
    body: "最近 N 天参考曲线使用预测日前连续最近多少天的数据。它只影响相似法参考曲线，不改变具体价格模型或价格区间概率模型的预测结果。",
    tips: ["数值小更贴近近期波动", "与同类型日个数独立设置", "用于对照模型预测，不参与模型版本选择"],
  },
  同类型日个数: {
    title: "同类型日个数",
    body: "同类型日参考曲线使用预测日前最近多少个同类型日期，例如工作日、周末或节假日。它和最近天数不是同一个参数。",
    tips: ["节假日或周末差异明显时可适当调大", "只影响同类型日参考曲线", "不会改变模型训练或模型预测"],
  },
  segmentModelSelection: {
    title: "当前版本内分时段算法选择",
    body: "每个时段都可以在当前默认模型版本内部单独指定预测时使用哪个候选算法变体。默认来自训练时验证集表现，也可以在这里按指标重新排序后保存。",
    tips: ["保存后立即影响下一次预测", "只改变当前版本内部的时段算法选择，不会切换历史模型版本"],
  },
  rankMetric: {
    title: "排序指标",
    body: "用于给每个时段下的候选模型排序。误差类指标越小越好，方向准确率越高越好，综合分默认用 MAE + 0.2×RMSE。",
    tips: ["综合分适合默认选择", "关注尖峰时可看 P90误差或最大误差"],
  },
  rangeMae: {
    title: "MAE(价格范围)",
    body: "只统计实际日前价格落在指定区间内的验证样本，再计算 MAE。这样可以暂时排除极低或极高价格对排序的影响。",
    tips: ["区间按实际价格筛选，包含边界", "价格上下限在预测页临时输入，不需要重新训练"],
  },
};

const predictionSimilarityHelpContent = {
  火电开机容量: {
    title: "火电开机容量",
    body: "本次价格预测实际使用的日级火电开机容量。默认读取预测文件中的开机容量；如果你手动修改，且没有勾选模型预测值，价格模型会使用这里填写的值。",
    tips: ["该值会作为价格模型的 thermal_on_capacity 特征", "日级容量会填充到当天 96 个时段", "适合录入省调已知或人工判断后的开机安排"],
  },
  开机容量模型预测值: {
    title: "开机容量模型预测值",
    body: "勾选后，系统会用当前模型版本中的日级开机容量模型预测容量，并用这个预测值替代输入框中的手动值参与价格预测。",
    tips: ["勾选后输入框会变为不可修改", "如果当前模型版本没有容量模型，该选项会不可用", "预测结果会记录本次容量来源和值"],
  },
  开机容量模型预测值展示: {
    title: "模型预测值",
    body: "这里展示开机容量模型根据预测日新能源、用电负荷、净负荷和日期特征算出的参考值。它只有在勾选“开机容量模型预测值”时才会真正用于价格预测。",
    tips: ["不勾选时仅作参考", "可用于和预测文件值、人工修正值对比", "结果文件会同时记录模型参考值和实际使用值"],
  },
  预测模型版本: {
    title: "预测模型版本",
    body: "选择本次执行预测时使用哪个模型版本。留空表示使用当前默认模型版本；选择历史版本只影响本次预测，不会切换默认模型。",
    tips: ["方便对比不同模型版本", "不会改变模型训练结果"],
  },
  净负荷相似法: {
    title: "净负荷相似法",
    body: "只用净负荷/火电空间这个核心条件，在历史数据里找最接近的点，再按距离加权得到参考价格。",
    tips: ["区别：它只看一个核心条件，KNN/加权KNN会同时看多个因素", "逻辑最简单，适合作为基础参考线", "只影响参考曲线，不改变模型预测"],
  },
  KNN相似法: {
    title: "KNN相似法",
    body: "同时参考净负荷、总负荷、新能源、火电开机、供需比例、时段和日期类型等因素，找出整体最相似的历史点，然后对保留下来的价格做普通平均。历史候选范围共用左侧净负荷相似法里的最近天数/同类型日个数。",
    tips: ["最大距离阈值不是 net_load 原始差值，而是多因素标准化后的综合距离", "区别：KNN相似法对保留点普通平均，每个保留点影响一样", "K 越大参考点越多，最大距离阈值越小过滤越严格"],
  },
  加权KNN回归: {
    title: "加权KNN回归",
    body: "和 KNN 相似法使用相同类型的多因素相似度，但最后不是普通平均，而是让越相似的历史点权重越大，离得远的点影响越小。历史候选范围共用左侧净负荷相似法里的最近天数/同类型日个数。",
    tips: ["最大距离阈值不是 net_load 原始差值，而是多因素标准化后的综合距离", "区别：加权KNN更偏向最像的历史点，不太让较远点拉偏结果", "适合相似点质量差异比较明显时参考"],
  },
  "相似点数量 K": {
    title: "相似点数量 K",
    body: "最多先取多少个最相似的历史点作为候选。最终还会经过最大距离阈值过滤，太远的点不会强行参与计算。",
    tips: ["K 小更敏感", "K 大更平滑", "常用 3~10"],
  },
  最大距离阈值: {
    title: "最大距离阈值",
    body: "控制多因素相似点最多允许有多远。它不是 net_load 的原始差距，而是把净负荷、总负荷、新能源、火电开机、供需比例、时段、日期类型等因素综合后算出来的标准化距离。简单说：不是单看火电空间差多少，而是看整体场景像不像。",
    tips: ["太小可能可用点少", "太大可能混入不像的历史场景", "默认 3.0 较稳妥"],
  },
};

const archiveMetricHelpContent = {
  archiveMetricMae: {
    title: "MAE",
    body: "平均绝对误差。把 96 个点每个点的“预测价格和实际日前价格差多少”取绝对值，再求平均。",
    tips: ["越小越好", "单位是元/MWh", "直观看平均偏差有多大"],
  },
  archiveMetricRmse: {
    title: "RMSE",
    body: "均方根误差。会把大误差放大后再统计，所以对尖峰、极端偏差更敏感。",
    tips: ["越小越好", "RMSE 明显大于 MAE 时，说明有少数点误差很大"],
  },
  archiveMetricMaxAbsError: {
    title: "最大误差",
    body: "96 个点里预测价格和实际日前价格相差最大的那个点。",
    tips: ["越小越好", "用于看最坏情况下偏差有多大"],
  },
  archiveMetricP90AbsError: {
    title: "P90误差",
    body: "把 96 个点的绝对误差从小到大排序后，取 90% 位置附近的误差。",
    tips: ["越小越好", "比最大误差更稳，不容易被单个极端点完全带偏"],
  },
  archiveMetricDirectionAccuracy: {
    title: "方向准确率",
    body: "比较相邻时段价格涨跌方向，统计预测方向和实际方向一致的比例。",
    tips: ["越高越好", "主要看趋势判断是否跟实际一致"],
  },
  archiveMetricBias: {
    title: "Bias",
    body: "平均偏差，等于预测价格减实际日前价格后的平均值。",
    tips: ["接近 0 更好", "正数表示整体预测偏高，负数表示整体预测偏低"],
  },
};

const modelVersionHelpContent = {
  版本摘要: {
    title: "版本摘要",
    body: "把模型版本号、核心算法、分段数量和样本规模放在同一列，方便先判断这是哪一版、是否当前正在使用。",
    tips: ["默认模型是当前预测会使用的版本", "上一版用于快速回退", "更多配置在详情中展开"],
  },
  "价格 MAE": {
    title: "价格 MAE",
    body: "当前价格预测模型在验证集上的平均绝对误差，表示预测价格与真实日前出清价格平均相差多少。",
    tips: ["越小越好", "单位与日前出清价格一致", "用于快速比较价格预测模型整体偏差"],
  },
  "价格 RMSE": {
    title: "价格 RMSE",
    body: "当前价格预测模型在验证集上的均方根误差，会放大少数大误差点的影响。",
    tips: ["越小越好", "RMSE 明显大于 MAE 时，说明可能存在尖峰或局部大偏差"],
  },
  "30天 MAE": {
    title: "30天 MAE",
    body: "最近 30 天滚动回测中的价格模型平均绝对误差。没有执行滚动回测或当前版本没有保存该结果时显示“暂无”。",
    tips: ["越小越好", "比单次验证集更接近日常连续使用效果"],
  },
  区间准确率: {
    title: "区间准确率",
    body: "价格区间模型预测的最高概率区间，与真实价格所在区间一致的比例。",
    tips: ["越高越好", "用于判断区间分类模型整体命中能力"],
  },
  高价召回: {
    title: "高价召回",
    body: "真实处于高价区间的样本中，被价格区间模型识别为高价的比例。",
    tips: ["越高越能提前识别高价风险", "如果验证集中高价样本很少，该指标可能波动较大"],
  },
  "容量 MAE": {
    title: "容量 MAE",
    body: "开机容量模型在日级验证集上的平均绝对误差，表示预测火电开机容量与真实开机容量平均相差多少 MW。",
    tips: ["越小越好", "这是日级容量误差，不是 96 点逐点误差"],
  },
  "容量 RMSE": {
    title: "容量 RMSE",
    body: "开机容量模型在日级验证集上的均方根误差，对少数容量大偏差日期更敏感。",
    tips: ["越小越好", "RMSE 明显高于 MAE 时，说明存在个别日期偏差较大"],
  },
  "模型 MAE": {
    title: "模型 MAE",
    body: "价格预测模型在验证集上的平均绝对误差，数值越小表示平均偏差越小。",
    tips: ["用于横向比较不同价格模型版本", "单位与日前价格一致"],
  },
  "模型 RMSE": {
    title: "模型 RMSE",
    body: "价格预测模型在验证集上的均方根误差，对少数大偏差更敏感。",
    tips: ["RMSE 明显大于 MAE 时，要关注尖峰或异常点", "越小越好"],
  },
  "30天模型 MAE": {
    title: "30天模型 MAE",
    body: "最近 30 天滚动回测中的价格模型平均绝对误差，比单次验证集更接近日常使用效果。",
    tips: ["越小越好", "适合做版本排序和稳定性比较"],
  },
  价格区间模型: {
    title: "价格区间模型",
    body: "独立训练的价格区间分类模型，用来判断价格落在哪个区间以及高价概率，不是价格预测模型的输入特征。",
    tips: ["重点看准确率、高价召回和区间数量", "与价格预测模型各自独立寻优"],
  },
  开机容量模型: {
    title: "开机容量模型",
    body: "独立训练的日级火电开机容量模型，用预测日负荷、新能源和日期特征估算开机容量，可在预测时替代手动容量值。",
    tips: ["重点看 MAE、RMSE 和最大误差", "与价格预测模型各自独立寻优"],
  },
  "高价尖峰 MAE": {
    title: "高价尖峰 MAE",
    body: "最近 30 天滚动回测中高价样本的平均绝对误差，用来观察尖峰价格预测能力。",
    tips: ["越小越好", "高价风险敏感场景优先看这个指标"],
  },
  后端: {
    title: "后端",
    body: "当前价格预测模型使用的算法后端，例如 XGBoost、LightGBM 或 CatBoost。",
    tips: ["后端来自训练寻优结果", "同一版本内可能还有其他候选变体"],
  },
  最优变体: {
    title: "最优变体",
    body: "训练完成后被选中的价格预测特征组合与算法变体。",
    tips: ["预测时默认使用该变体", "如果启用了分时段算法选择，不同时段可能使用不同变体"],
  },
  训练窗口: {
    title: "训练窗口",
    body: "该模型训练时使用的历史天数或日期范围。价格模型、价格区间模型和开机容量模型可以各自有不同最优窗口。",
    tips: ["窗口越长样本越多", "窗口越短越贴近近期规律"],
  },
  验证天数: {
    title: "验证天数",
    body: "训练时预留最近多少天作为验证集，用来评估模型效果和选择最优模型。",
    tips: ["验证天数太少容易偶然", "验证天数太多会减少训练样本"],
  },
  "30天 RMSE": {
    title: "30天 RMSE",
    body: "最近 30 天滚动回测中的价格模型均方根误差，对连续回测中的大偏差更敏感。",
    tips: ["越小越好", "没有滚动回测结果时显示“暂无”"],
  },
  "高价 MAE": {
    title: "高价 MAE",
    body: "高价样本上的平均绝对误差，用来单独观察模型对高价时段的预测能力。",
    tips: ["越小越好", "适合关注尖峰风险时优先查看"],
  },
  状态: {
    title: "状态",
    body: "表示该子模型是否在当前模型版本中启用。无数据说明当前版本或当前接口没有提供该子模型信息。",
    tips: ["已启用不代表所有指标都一定存在", "旧模型版本可能没有区间或容量模型"],
  },
  最优模型: {
    title: "最优模型",
    body: "该子模型训练或寻优后被选中的算法模型。",
    tips: ["价格区间模型和价格预测模型独立寻优", "开机容量模型也独立训练和选择"],
  },
  区间数: {
    title: "区间数",
    body: "价格区间模型使用的价格分档数量，例如 0-250、250-300 等区间。",
    tips: ["区间配置来自训练配置", "区间越细，分类难度通常越高"],
  },
  准确率: {
    title: "准确率",
    body: "价格区间模型预测的最高概率区间命中真实价格区间的比例。",
    tips: ["越高越好", "配合 Top2 和高价召回一起看更稳"],
  },
  Top2: {
    title: "Top2",
    body: "真实价格区间是否落在模型概率最高的前两个区间内的比例。",
    tips: ["越高越好", "比准确率更能反映相邻区间判断是否接近"],
  },
  MAE: {
    title: "MAE",
    body: "平均绝对误差。当前卡片中用于开机容量模型时，单位是 MW。",
    tips: ["越小越好", "看平均偏差大小"],
  },
  RMSE: {
    title: "RMSE",
    body: "均方根误差。当前卡片中用于开机容量模型时，单位是 MW，并且会更重视大偏差日期。",
    tips: ["越小越好", "和 MAE 差距大时说明存在少数大误差"],
  },
  最大误差: {
    title: "最大误差",
    body: "验证集中单日开机容量预测偏差的最大绝对值。",
    tips: ["越小越好", "用于查看最坏情况下容量偏差有多大"],
  },
  偏差: {
    title: "偏差",
    body: "预测值减真实值后的平均值。正数表示整体预测偏高，负数表示整体预测偏低。",
    tips: ["越接近 0 越好", "可判断模型是否存在系统性高估或低估"],
  },
  特征数: {
    title: "特征数",
    body: "当前子模型实际使用的输入特征数量。",
    tips: ["特征数只说明输入维度", "模型效果仍要结合 MAE、RMSE、准确率等指标判断"],
  },
  价格预测模型: {
    title: "价格预测模型",
    body: "用于直接预测 96 点日前出清价格的主模型。详情里展示它自己的训练窗口、算法后端、最优变体、分段配置和验证误差。",
    tips: ["它会使用训练期内的真实历史开机容量", "预测时使用页面选择的手动容量或容量模型预测值"],
  },
  模型后端: {
    title: "模型后端",
    body: "该模型最终使用的算法训练后端，例如 XGBoost、LightGBM 或 CatBoost。不同后端会独立训练并按各自指标择优。",
    tips: ["来自寻优或训练时保存的模型元数据", "同一版本内价格模型和区间模型可以使用不同后端"],
  },
  候选变体数: {
    title: "候选变体数",
    body: "本次训练或寻优中参与比较的价格预测候选方案数量，通常由特征组合、算法后端和分段方案共同决定。",
    tips: ["数量越多表示比较范围越大", "最终仍以验证集指标选择最优变体"],
  },
  分段数量: {
    title: "分段数量",
    body: "价格预测模型把一天划分为几个业务时段分别建模或选择算法，用于适配峰谷、白天、夜间等不同价格规律。",
    tips: ["分段越细，局部适配能力越强", "样本少时过多分段可能不稳定"],
  },
  每段模型: {
    title: "每段模型",
    body: "价格预测模型在各个时段最终采用的算法或变体。启用分段选择时，不同时段可能会选到不同模型。",
    tips: ["用于复盘哪些时段由哪个模型负责", "为空时通常表示未保存分段选择细节或使用统一模型"],
  },
  高价加权: {
    title: "高价加权",
    body: "表示价格预测模型训练时是否提高高价样本权重，让模型更重视尖峰和高价时段的拟合效果。",
    tips: ["开启后高价时段可能更敏感", "普通时段误差也要结合 MAE、RMSE 一起看"],
  },
  区间数量: {
    title: "区间数量",
    body: "价格区间模型使用的价格分档数量，例如 0-250、250-300 等区间。它影响区间分类难度和高价识别粒度。",
    tips: ["区间越多，分类越细", "区间过细时准确率可能下降"],
  },
  特征数量: {
    title: "特征数量",
    body: "该子模型实际使用的输入特征个数。价格区间模型、开机容量模型的特征集合彼此独立。",
    tips: ["特征数量不直接代表效果好坏", "仍需结合准确率、召回率、MAE、RMSE 等指标判断"],
  },
  "训练/验证样本": {
    title: "训练/验证样本",
    body: "该子模型训练集和验证集的样本数量。价格区间模型通常按 96 点样本统计，开机容量模型按日级样本统计。",
    tips: ["训练样本决定模型可学习的信息量", "验证样本太少时指标波动会更大"],
  },
  区间配置: {
    title: "区间配置",
    body: "价格区间模型训练时使用的价格分档边界，决定真实价格和预测概率会被归到哪些区间。",
    tips: ["配置来自训练时保存的区间边界", "改变区间配置后需要重新训练区间模型"],
  },
  详情: {
    title: "详情",
    body: "展开后查看价格预测、价格区间、开机容量三类模型的训练窗口、验证天数、模型选择、指标和关键配置。",
    tips: ["摘要用于快速筛选", "详情用于复盘为什么选中这一版"],
  },
};

let helpContentMap = {
  寻优最大历史天数: {
    title: "寻优最大历史天数",
    body: "手动点击“自动寻优并训练最优模型”时，最多向历史数据回看多少天。范围越大，能测试的候选天数越多，但计算时间也会变长。",
    tips: ["数据变化快时可适当缩短", "数据规律稳定时可适当放大", "不确定时保持默认值即可"],
  },
  寻优验证集天数: {
    title: "寻优验证集天数",
    body: "手动寻优时预留最近多少天作为验证集，用来判断不同窗口参数的效果。",
    tips: ["天数太少容易偶然", "天数太多会减少训练样本", "常用 7~30 天"],
  },
  "每个模型最大训练轮数": {
    title: "每个模型最大训练轮数",
    body: "自动寻优或手动训练时，每个时段、每种算法最多训练多少轮。XGBoost、LightGBM、CatBoost 都会使用这个上限；如果验证误差长期不再变好，会提前停止。",
    tips: ["数据量较小时不用过大", "训练慢时先降低轮数", "默认值偏稳妥"],
  },
  局部细搜半径: {
    title: "局部细搜半径",
    body: "粗略找到较优训练使用天数后，在最优点附近再细查多少天。半径越大，细搜越充分但耗时越长。",
    tips: ["设为 0 表示不做细搜", "候选天数效果波动大时可适当增加", "常用 7~30 天"],
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
    tips: ["默认 6 段适合大多数情况", "有明确业务时段差异时再自定义"],
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
  训练使用天数: {
    title: "训练使用天数",
    body: "这版模型训练时，往前取了多少天历史数据。比如 56 表示用最近 56 天数据训练；不是预测天数，也不是回测天数。",
    tips: ["天数太短可能不稳定", "天数太长可能混入过旧规律", "常用 30~180 天"],
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
  "手动每个模型最大训练轮数": {
    title: "每个模型最大训练轮数",
    body: "手动训练时，每个时段、每种算法最多训练多少轮。轮数越多上限越高、耗时可能越长，但模型会根据验证集表现提前停止。",
    tips: ["训练变慢可降低", "效果不稳定可配合验证集观察"],
  },
  相似法参考: {
    title: "相似法参考",
    body: "预测页的最近天数和同类型日个数是两套独立参数，只影响相似法参考曲线，不影响模型预测本身。",
    tips: ["数值小更贴近近期", "数值大更平滑稳定"],
  },
  历史模型版本下拉列表: {
    title: "历史模型版本下拉列表",
    body: "选择已经训练完成的历史模型版本，用于设为默认模型版本、回退或删除。",
    tips: ["默认模型版本会用于后续预测", "删除前建议确认不是常用版本"],
  },
  排序方式: {
    title: "排序方式",
    body: "控制历史模型列表的排列顺序，便于按时间或误差快速筛选。",
    tips: ["MAE/RMSE 越小通常越好", "也要结合训练日期和样本范围判断"],
  },
  当前默认模型版本分时段指标: {
    title: "当前默认模型版本分时段指标",
    body: "按不同时段展示当前默认模型版本在验证集上的表现，帮助判断模型在哪些时段更准或更弱。",
    tips: ["重点关注晚高峰和高价时段", "和净负荷相似法对比更直观"],
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
  "净负荷相似法 MAE": {
    title: "净负荷相似法 MAE",
    body: "只按净负荷寻找历史相似点得到的参考价格 MAE，用作模型效果的基准线。",
    tips: ["模型 MAE 小于它，说明模型优于净负荷相似法"],
  },
  "净负荷相似法 RMSE": {
    title: "净负荷相似法 RMSE",
    body: "只按净负荷寻找历史相似点得到的参考价格 RMSE，对大误差更敏感。",
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
  "净负荷相似法 MAE": {
    title: "净负荷相似法 MAE",
    body: "只按净负荷寻找历史相似点得到的参考价格误差。",
    tips: ["用于判断净负荷单因素的参考价值"],
  },
  较净负荷相似法提升: {
    title: "较净负荷相似法提升",
    body: "模型相对净负荷相似法减少了多少 MAE。正数表示模型更好。",
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
    subtitle: "分别设置最近天数和同类型日个数后执行预测，同时对比两条 96 点相似法参考曲线。",
  },
  "predict-multi-day": {
    title: "预测多天价格",
    subtitle: "上传或编辑“预测文件-N天”，自动识别基准日真实日前价格，一次性输出后续多天预测曲线。",
  },
  versions: {
    title: "模型版本管理",
    subtitle: "管理历史模型版本，支持默认模型版本切换与快速回退。",
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
  helpContentMap = {
    ...helpContentMap,
    ...modelRankingHelpContent,
    ...predictionSimilarityHelpContent,
    ...archiveMetricHelpContent,
    ...modelVersionHelpContent,
  };
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
  root
    .querySelectorAll(".field > span, .switch-item > span, .data-table th, .subsection-title, .version-metric-item > span, .version-module-field > span, .version-detail-field > span")
    .forEach(attachHelpTrigger);
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
      resizeArchiveReviewChart();
      if (App.predictionArchiveDetail) {
        renderPredictionArchiveDetail(App.predictionArchiveDetail);
      }
    });
  }
  if (name === "predict-multi-day") {
    if (!App.multiDayTemplateRows.length) {
      loadMultiDayTemplate().catch((error) => {
        console.error(error);
        showToast(error.message, "error");
      });
    }
    requestAnimationFrame(() => {
      renderMultiDayPrediction(App.lastMultiDayPrediction);
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
    ? `最优训练使用天数：最近 ${windowState.best_window_days} 天`
    : "最优训练使用天数：待寻优";
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
  items.push(windowState.final_model?.run_id ? `默认模型版本已更新：${windowState.final_model.run_id}` : "默认模型版本更新：待执行");
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

function modelVersionDateRange(item = {}) {
  if (!item.train_start_date && !item.train_end_date) return "-";
  return `${item.train_start_date || "-"} ~ ${item.train_end_date || "-"}`;
}

function versionCurrentItem(versions = [], metadata = {}) {
  const runId = metadata?.run_id;
  return versions.find((item) => item.is_default)
    || versions.find((item) => runId && item.run_id === runId)
    || versions[0]
    || null;
}

function versionMetricText(value, formatter = formatMetricCell) {
  const text = formatter(value);
  return text === "-" ? "暂无" : text;
}

function enabledText(value) {
  if (value === true) return "已启用";
  if (value === false) return "未启用";
  return "无数据";
}

function isCurrentVersionItem(item = {}, metadata = {}) {
  const runId = String(metadata?.run_id || "");
  return Boolean(runId && (String(item.run_id || "") === runId || String(item.version_key || "") === runId));
}

function metricsOverall(metrics = {}) {
  if (!metrics || typeof metrics !== "object") return {};
  return metrics.overall && typeof metrics.overall === "object" ? metrics.overall : metrics;
}

function sumSegmentRowsFromVariantMetrics(model = {}) {
  const selectedKey = model.selected_model_key || model.model_key;
  const variants = model.variant_metrics && typeof model.variant_metrics === "object" ? model.variant_metrics : {};
  const selected = variants[selectedKey] && typeof variants[selectedKey] === "object" ? variants[selectedKey] : {};
  const segments = selected.segments && typeof selected.segments === "object" ? selected.segments : {};
  const rows = { train_rows: null, valid_rows: null };
  Object.values(segments).forEach((segment) => {
    if (!segment || typeof segment !== "object") return;
    const trainRows = Number(segment.train_rows);
    const validRows = Number(segment.valid_rows);
    if (Number.isFinite(trainRows)) rows.train_rows = (rows.train_rows || 0) + trainRows;
    if (Number.isFinite(validRows)) rows.valid_rows = (rows.valid_rows || 0) + validRows;
  });
  return rows;
}

function currentMetadataVersionSummary(metadata = {}, item = {}) {
  const intervalModel = metadata.price_interval_model && typeof metadata.price_interval_model === "object" ? metadata.price_interval_model : {};
  const thermalModel = metadata.thermal_capacity_model && typeof metadata.thermal_capacity_model === "object" ? metadata.thermal_capacity_model : {};
  const intervalMetrics = metricsOverall(intervalModel.metrics);
  const thermalMetrics = metricsOverall(thermalModel.metrics);
  const intervalRows = sumSegmentRowsFromVariantMetrics(intervalModel);
  return {
    price_model: {
      backend: item.selected_model_backend || metadata.selected_model_backend,
      backend_label: item.selected_model_backend_label || metadata.selected_model_backend_label || metadata.selected_model_backend,
      selected_model_key: item.selected_model_key || metadata.selected_model_key,
      mae: item.final_mae ?? summarizeQualityMetric(metadata.metrics, "final_mae"),
      rmse: item.final_rmse ?? summarizeQualityMetric(metadata.metrics, "final_rmse"),
      rolling_30_mae: item.rolling_30_mae ?? metadata.rolling_backtest_metrics?.["30"]?.overall?.mae,
      rolling_30_rmse: item.rolling_30_rmse ?? metadata.rolling_backtest_metrics?.["30"]?.overall?.rmse,
      high_price_mae: item.rolling_30_high_price_mae ?? metadata.rolling_backtest_metrics?.["30"]?.spike_errors?.high?.mae,
      training_window_days: item.training_window_days ?? metadata.training_window_days,
      valid_days: item.valid_days ?? metadata.valid_days,
      sample_rows: item.sample_rows ?? metadata.sample_rows,
      segment_count: item.segment_count ?? (Array.isArray(metadata.segment_config || metadata.segments) ? (metadata.segment_config || metadata.segments).length : undefined),
    },
    price_interval_model: {
      enabled: intervalModel.enabled === true,
      selected_model_key: intervalModel.selected_model_key,
      accuracy: intervalMetrics.interval_accuracy,
      top2_accuracy: intervalMetrics.top2_accuracy,
      logloss: intervalMetrics.logloss ?? intervalMetrics.log_loss,
      high_price_recall: intervalMetrics.high_price_recall,
      interval_count: Array.isArray(intervalModel.intervals) ? intervalModel.intervals.length : undefined,
      train_rows: intervalRows.train_rows ?? intervalModel.train_rows,
      valid_rows: intervalRows.valid_rows ?? intervalModel.valid_rows,
      feature_count: Array.isArray(intervalModel.feature_columns) ? intervalModel.feature_columns.length : undefined,
    },
    thermal_capacity_model: {
      enabled: thermalModel.enabled === true,
      selected_model_key: thermalModel.selected_model_key,
      selected_model_backend: thermalModel.selected_model_backend,
      selected_model_backend_label: thermalModel.selected_model_backend_label || thermalModel.selected_model_backend,
      candidate_count: thermalModel.model_variants && typeof thermalModel.model_variants === "object" ? Object.keys(thermalModel.model_variants).length : undefined,
      mae: thermalMetrics.mae,
      rmse: thermalMetrics.rmse,
      max_error: thermalMetrics.max_error,
      bias: thermalMetrics.bias,
      feature_count: Array.isArray(thermalModel.feature_columns) ? thermalModel.feature_columns.length : undefined,
    },
  };
}

function currentMetadataVersionDetail(metadata = {}) {
  const intervalModel = metadata.price_interval_model && typeof metadata.price_interval_model === "object" ? metadata.price_interval_model : {};
  const thermalModel = metadata.thermal_capacity_model && typeof metadata.thermal_capacity_model === "object" ? metadata.thermal_capacity_model : {};
  const intervalMetrics = metricsOverall(intervalModel.metrics);
  const thermalMetrics = metricsOverall(thermalModel.metrics);
  const intervalRows = sumSegmentRowsFromVariantMetrics(intervalModel);
  const priceConfig = metadata.price_model_training_config || {};
  const intervalConfig = metadata.interval_model_training_config || {};
  const thermalConfig = metadata.thermal_capacity_model_training_config || {};
  return {
    training: {
      price: {
        training_mode: priceConfig.training_mode || metadata.training_mode,
        training_window_days: priceConfig.training_window_days ?? metadata.training_window_days,
        valid_days: priceConfig.valid_days ?? metadata.valid_days,
        num_boost_round: priceConfig.num_boost_round ?? metadata.num_boost_round,
        start_date: priceConfig.start_date || metadata.train_start_date,
        end_date: priceConfig.end_date || metadata.train_end_date,
      },
      interval: {
        training_mode: intervalConfig.training_mode || metadata.training_mode,
        training_window_days: intervalConfig.training_window_days,
        valid_days: intervalConfig.valid_days,
        num_boost_round: intervalConfig.num_boost_round,
        start_date: intervalConfig.start_date || metadata.train_start_date,
        end_date: intervalConfig.end_date || metadata.train_end_date,
      },
      thermal_capacity: {
        training_mode: thermalConfig.training_mode || metadata.training_mode,
        training_window_days: thermalConfig.training_window_days,
        valid_days: thermalConfig.valid_days,
        num_boost_round: thermalConfig.num_boost_round,
        start_date: thermalConfig.start_date || metadata.train_start_date,
        end_date: thermalConfig.end_date || metadata.train_end_date,
      },
    },
    price_model: {
      selected_model_key: metadata.selected_model_key,
      selected_model_backend: metadata.selected_model_backend,
      selected_model_backend_label: metadata.selected_model_backend_label || metadata.selected_model_backend,
      algorithm_variants: versionAlgorithmVariants(metadata),
      selected_segment_price_models: metadata.selected_segment_price_models || {},
      segment_count: Array.isArray(metadata.segment_config || metadata.segments) ? (metadata.segment_config || metadata.segments).length : undefined,
      high_price_weighting: metadata.high_price_weighting || {},
    },
    price_interval_model: {
      enabled: intervalModel.enabled === true,
      selected_model_key: intervalModel.selected_model_key,
      selected_model_backend: intervalModel.selected_model_backend,
      selected_model_backend_label: intervalModel.selected_model_backend_label || intervalModel.selected_model_backend,
      metrics: {
        accuracy: intervalMetrics.interval_accuracy,
        top2_accuracy: intervalMetrics.top2_accuracy,
        logloss: intervalMetrics.logloss ?? intervalMetrics.log_loss,
        high_price_recall: intervalMetrics.high_price_recall,
      },
      intervals: intervalModel.intervals || [],
      interval_count: Array.isArray(intervalModel.intervals) ? intervalModel.intervals.length : undefined,
      feature_count: Array.isArray(intervalModel.feature_columns) ? intervalModel.feature_columns.length : undefined,
      train_rows: intervalRows.train_rows ?? intervalModel.train_rows,
      valid_rows: intervalRows.valid_rows ?? intervalModel.valid_rows,
    },
    thermal_capacity_model: {
      enabled: thermalModel.enabled === true,
      selected_model_key: thermalModel.selected_model_key,
      selected_model_backend: thermalModel.selected_model_backend,
      selected_model_backend_label: thermalModel.selected_model_backend_label || thermalModel.selected_model_backend,
      model_variants: thermalModel.model_variants || {},
      variant_metrics: thermalModel.variant_metrics || {},
      metrics: {
        mae: thermalMetrics.mae,
        rmse: thermalMetrics.rmse,
        max_error: thermalMetrics.max_error,
        bias: thermalMetrics.bias,
      },
      feature_count: Array.isArray(thermalModel.feature_columns) ? thermalModel.feature_columns.length : undefined,
      train_rows: thermalModel.train_rows,
      valid_rows: thermalModel.valid_rows,
    },
  };
}

function summarizeQualityMetric(metrics = {}, key) {
  if (!metrics || typeof metrics !== "object") return undefined;
  const values = Object.values(metrics)
    .map((row) => Number(row?.[key]))
    .filter((value) => Number.isFinite(value));
  if (!values.length) return undefined;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function enrichCurrentVersionItem(item = {}, metadata = {}) {
  if (!isCurrentVersionItem(item, metadata)) return item;
  const detail = item.version_detail || currentMetadataVersionDetail(metadata);
  if (!item.version_detail && Array.isArray(item.algorithm_variants) && detail.price_model) {
    detail.price_model.algorithm_variants = item.algorithm_variants;
  }
  return {
    ...item,
    version_summary: item.version_summary || currentMetadataVersionSummary(metadata, item),
    version_detail: detail,
  };
}

function renderVersionMetricItems(items = []) {
  return items
    .map(([label, value, formatter = formatMetricCell]) => `
      <div class="version-metric-item">
        <span>${htmlEscape(label)}</span>
        <strong>${htmlEscape(versionMetricText(value, formatter))}</strong>
      </div>
    `)
    .join("");
}

function renderCurrentVersionOverview(versions = [], metadata = {}) {
  const current = enrichCurrentVersionItem(versionCurrentItem(versions, metadata) || {}, metadata);
  const overview = $("#current-version-overview");
  const moduleGrid = $("#current-model-module-grid");
  if (!overview || !moduleGrid) return;
  if (!current.version_key && !current.run_id) {
    overview.innerHTML = `<div class="empty-state">暂无可展示的模型版本信息</div>`;
    moduleGrid.innerHTML = "";
    return;
  }
  const summary = current.version_summary || {};
  const price = summary.price_model || {};
  const interval = summary.price_interval_model || {};
  const thermal = summary.thermal_capacity_model || {};
  const statusTags = [
    current.is_default ? `<span class="status-tag default">默认模型</span>` : "",
    current.is_previous ? `<span class="status-tag previous">上一版</span>` : "",
  ].filter(Boolean).join("");
  overview.innerHTML = `
    <div class="version-overview-main">
      <div>
        <div class="version-overview-kicker">当前默认模型总览</div>
        <div class="version-overview-title">${htmlEscape(current.version_key || current.run_id || "-")}</div>
        <div class="version-overview-subtitle">
          ${htmlEscape(modelVersionDateRange(current))} · ${htmlEscape(price.backend_label || current.selected_model_backend_label || "-")}
          · ${htmlEscape(current.segment_count ?? "-")} 段 · ${htmlEscape(current.sample_rows ?? "-")} 行样本
        </div>
      </div>
      <div class="version-status-stack">${statusTags || `<span class="status-tag">历史版本</span>`}</div>
    </div>
    <div class="version-overview-metrics">
      ${renderVersionMetricItems([
        ["价格 MAE", price.mae ?? current.final_mae],
        ["价格 RMSE", price.rmse ?? current.final_rmse],
        ["30天 MAE", price.rolling_30_mae ?? current.rolling_30_mae],
        ["区间准确率", interval.accuracy, formatPercent],
        ["高价召回", interval.high_price_recall, formatPercent],
        ["容量 MAE", thermal.mae],
        ["容量 RMSE", thermal.rmse],
      ])}
    </div>
  `;
  moduleGrid.innerHTML = [
    renderCurrentModulePanel("日前价格预测模型", "价格曲线主模型", [
      ["后端", price.backend_label || current.selected_model_backend_label || "-"],
      ["最优变体", price.selected_model_key || current.selected_model_key || "-"],
      ["训练窗口", `${price.training_window_days ?? current.training_window_days ?? "-"} 天`],
      ["验证天数", `${price.valid_days ?? current.valid_days ?? "-"} 天`],
      ["30天 RMSE", versionMetricText(price.rolling_30_rmse ?? current.rolling_30_rmse)],
      ["高价 MAE", versionMetricText(price.high_price_mae ?? current.rolling_30_high_price_mae)],
    ]),
    renderCurrentModulePanel("价格区间模型", "区间概率与高价判断", [
      ["状态", enabledText(interval.enabled)],
      ["最优模型", interval.selected_model_key || "-"],
      ["区间数", interval.interval_count ?? "-"],
      ["准确率", versionMetricText(interval.accuracy, formatPercent)],
      ["Top2", versionMetricText(interval.top2_accuracy, formatPercent)],
      ["高价召回", versionMetricText(interval.high_price_recall, formatPercent)],
    ]),
    renderCurrentModulePanel("开机容量模型", "日级火电开机容量", [
      ["状态", enabledText(thermal.enabled)],
      ["后端", thermal.selected_model_backend_label || thermal.selected_model_backend || "-"],
      ["最优模型", thermal.selected_model_key || "-"],
      ["候选变体数", thermal.candidate_count ?? "-"],
      ["MAE", versionMetricText(thermal.mae)],
      ["RMSE", versionMetricText(thermal.rmse)],
      ["最大误差", versionMetricText(thermal.max_error)],
      ["偏差", versionMetricText(thermal.bias)],
      ["特征数", thermal.feature_count ?? "-"],
    ]),
  ].join("");
  injectHelpAffordances(overview);
  injectHelpAffordances(moduleGrid);
}

function renderCurrentModulePanel(title, subtitle, rows) {
  return `
    <article class="version-module-panel">
      <div class="version-module-head">
        <div>
          <div class="version-module-title">${htmlEscape(title)}</div>
          <div class="version-module-subtitle">${htmlEscape(subtitle)}</div>
        </div>
      </div>
      <div class="version-module-fields">
        ${rows.map(([label, value]) => `
          <div class="version-module-field">
            <span>${htmlEscape(label)}</span>
            <strong>${htmlEscape(value)}</strong>
          </div>
        `).join("")}
      </div>
    </article>
  `;
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

const modelRankMetricLabelMap = {
  default_score: "综合分",
  mae: "MAE",
  rmse: "RMSE",
  mae_range: "MAE(价格范围)",
  p90_abs_error: "P90误差",
  max_abs_error: "最大误差",
  direction_accuracy: "方向准确率",
};

function modelRankPriceValue(selector) {
  const value = Number($(selector)?.value);
  return Number.isFinite(value) ? value : null;
}

function metricDisplayValue(value, metric) {
  if (metric === "direction_accuracy") return formatPercentCell(value);
  return formatMetricCell(value);
}

function modelDisplayName(item = {}) {
  const label = item.model_backend_label || item.model_backend || item.model_key || "-";
  return item.model_key ? `${label}｜${item.model_key}` : label;
}

function modelRankQueryString() {
  const metric = $("#model-rank-metric")?.value || "default_score";
  const params = new URLSearchParams({ metric, target: App.versionTarget || "dayahead" });
  if (metric === "mae_range") {
    const priceMin = modelRankPriceValue("#model-rank-price-min");
    const priceMax = modelRankPriceValue("#model-rank-price-max");
    if (priceMin !== null) params.set("price_min", String(priceMin));
    if (priceMax !== null) params.set("price_max", String(priceMax));
  }
  return params.toString();
}

async function loadModelCandidateRankings() {
  const table = $("#model-rank-table");
  if (table) table.innerHTML = `<tbody><tr><td>正在加载模型排序...</td></tr></tbody>`;
  const data = await request(`/api/model/candidate-rankings?${modelRankQueryString()}`);
  App.modelCandidateRankings = data;
  App.selectedSegmentPriceModels = { ...(data.selected_segment_price_models || {}) };
  (data.segments || []).forEach((segment) => {
    if (!App.selectedSegmentPriceModels[segment.segment]) {
      App.selectedSegmentPriceModels[segment.segment] = segment.current_model_key || segment.rankings?.[0]?.model_key || "";
    }
  });
  renderModelCandidateRankings(data);
  return data;
}

function renderModelCandidateRankings(data = App.modelCandidateRankings || {}) {
  const table = $("#model-rank-table");
  const meta = $("#model-rank-meta");
  if (!table) return;
  const segments = data.segments || [];
  const metric = data.metric || $("#model-rank-metric")?.value || "default_score";
  if (meta) {
    const rangeText = metric === "mae_range" ? `，实际价格 ${data.price_min ?? "-∞"}~${data.price_max ?? "+∞"}` : "";
    meta.textContent = `${modelRankMetricLabelMap[metric] || metric}${rangeText}；每行可选择该时段预测用的算法变体`;
  }
  if (!segments.length) {
    table.innerHTML = `<tbody><tr><td>${htmlEscape(data.message || "暂无候选模型验证明细，请重新训练模型后查看。")}</td></tr></tbody>`;
    return;
  }
  table.innerHTML = `
    <thead>
      <tr>
        <th>时段</th>
        <th>当前使用</th>
        <th>排序前三</th>
        <th>${htmlEscape(modelRankMetricLabelMap[metric] || metric)}</th>
        <th>样本数</th>
        <th>切换算法</th>
      </tr>
    </thead>
    <tbody>
      ${segments
        .map((segment) => {
          const rankings = segment.rankings || [];
          const selectedKey = App.selectedSegmentPriceModels[segment.segment] || segment.current_model_key || rankings[0]?.model_key || "";
          const selected = rankings.find((item) => item.model_key === selectedKey) || rankings[0] || {};
          const topPills = rankings
            .slice(0, 3)
            .map((item, index) => {
              const currentClass = item.model_key === selectedKey ? " is-current" : "";
              return `<span class="rank-pill${currentClass}">#${index + 1} ${htmlEscape(modelDisplayName(item))} ${metricDisplayValue(item.metric_value, metric)}</span>`;
            })
            .join("");
          const options = rankings
            .map((item) => `<option value="${htmlEscape(item.model_key)}"${item.model_key === selectedKey ? " selected" : ""}>${htmlEscape(modelDisplayName(item))}</option>`)
            .join("");
          return `
            <tr>
              <td>${htmlEscape(segmentNameMap[segment.segment] || segment.segment)}</td>
              <td>${htmlEscape(modelDisplayName(selected))}</td>
              <td>${topPills || "-"}</td>
              <td>${metricDisplayValue(selected.metric_value, metric)}</td>
              <td>${selected.rows ?? "-"}</td>
              <td><select class="rank-select" data-segment-model-select="${htmlEscape(segment.segment)}">${options}</select></td>
            </tr>
          `;
        })
        .join("")}
    </tbody>
  `;
}

async function saveSegmentModelSelection() {
  const payload = {
    target: App.versionTarget || "dayahead",
    selected_segment_price_models: App.selectedSegmentPriceModels || {},
  };
  const result = await request("/api/model/segment-selection", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  showToast(result.message || "分时段算法选择已保存");
  await refreshSummary();
  await loadModelCandidateRankings();
}

function archiveReviewDateValue() {
  return $("#archive-review-date")?.value || App.lastPrediction?.forecast_date || new Date().toISOString().slice(0, 10);
}

function setArchiveReviewDate(dateText) {
  const input = $("#archive-review-date");
  if (input && dateText) input.value = String(dateText).slice(0, 10);
}

function formatArchiveRecordLabel(record) {
  const created = record.created_at ? String(record.created_at).replace("T", " ") : "-";
  const segmentText = record.segment_count ? `${record.segment_count}段` : "-";
  return `${created}｜${segmentText}｜${record.model_run_id || "-"}`;
}

async function loadPredictionArchiveRecords(dateText = archiveReviewDateValue()) {
  setArchiveReviewDate(dateText);
  setArchiveReviewLoading("正在查询预测记录...");
  try {
    const data = await request(`/api/prediction-archive?date=${encodeURIComponent(dateText || "")}`);
    App.predictionArchiveRecords = data.records || [];
    renderPredictionArchiveRecordSelect();
    if (App.predictionArchiveRecords.length) {
      await loadPredictionArchiveDetail(App.predictionArchiveRecords[0].archive_id);
    } else {
      App.predictionArchiveDetail = null;
      renderPredictionArchiveDetail(null, "当前日期暂无预测留痕");
    }
  } catch (error) {
    App.predictionArchiveRecords = [];
    App.predictionArchiveDetail = null;
    renderPredictionArchiveRecordSelect();
    renderPredictionArchiveDetail(null, `查询失败：${error.message}`);
    throw error;
  }
}

function renderPredictionArchiveRecordSelect() {
  const select = $("#archive-review-select");
  if (!select) return;
  if (!App.predictionArchiveRecords.length) {
    select.innerHTML = `<option value="">暂无记录</option>`;
    return;
  }
  select.innerHTML = App.predictionArchiveRecords
    .map((record) => `<option value="${htmlEscape(record.archive_id)}">${htmlEscape(formatArchiveRecordLabel(record))}</option>`)
    .join("");
}

async function loadPredictionArchiveDetail(archiveId) {
  if (!archiveId) return;
  setArchiveReviewLoading("正在加载预测详情...");
  const data = await request(`/api/prediction-archive/${encodeURIComponent(archiveId)}`);
  App.predictionArchiveDetail = data;
  renderPredictionArchiveDetail(data);
}

function ensureArchiveReviewChart() {
  const target = $("#archive-review-chart");
  if (!target || !window.echarts) return null;
  if (!target.offsetWidth || !target.offsetHeight) return null;
  if (!App.archiveChart) {
    App.archiveChart = window.echarts.init(target);
    window.addEventListener("resize", () => App.archiveChart?.resize());
  }
  App.archiveChart.resize();
  return App.archiveChart;
}

function resizeArchiveReviewChart() {
  if (App.archiveChart) {
    App.archiveChart.resize();
  }
}

function setArchiveReviewLoading(message) {
  const meta = $("#archive-review-meta");
  if (meta) meta.textContent = message;
  renderArchiveMetrics(null, message);
  const chart = ensureArchiveReviewChart();
  if (chart) {
    chart.setOption({ title: { text: message, left: "center", top: "middle", textStyle: { color: "#667085", fontSize: 14 } } }, true);
  }
}

function archiveSeriesValue(row, key) {
  const value = Number(row?.[key]);
  return Number.isFinite(value) ? Number(value.toFixed(4)) : null;
}

const archiveIntervalTooltipLabels = {
  predicted_interval: "\u6700\u53ef\u80fd\u4ef7\u683c\u533a\u95f4",
  predicted_interval_probability: "\u4ef7\u683c\u533a\u95f4\u6982\u7387",
  high_price_probability: "\u9ad8\u4ef7\u6982\u7387",
  extreme_price_probability: ">1000 \u6982\u7387",
  interval_backtest_accuracy: "\u533a\u95f4\u5386\u53f2\u547d\u4e2d\u7387",
  price_interval_consistency: "\u4e00\u81f4\u6027",
};

function renderArchiveIntervalBlock(row) {
  return window.archiveReviewHelpers?.renderArchiveIntervalTooltipBlock
    ? window.archiveReviewHelpers.renderArchiveIntervalTooltipBlock(row || {}, archiveIntervalTooltipLabels)
    : "";
}

function archiveIntervalInfoText(rows = []) {
  const list = Array.isArray(rows) ? rows : [];
  const hasInfo = window.archiveReviewHelpers?.rowHasIntervalInfo || (() => false);
  const savedCount = list.filter((row) => hasInfo(row)).length;
  if (!savedCount) return "\u672a\u4fdd\u5b58\u4ef7\u683c\u533a\u95f4\u4fe1\u606f";
  return `\u5df2\u4fdd\u5b58 ${savedCount}/${list.length} \u4e2a\u65f6\u6bb5\u7684\u4ef7\u683c\u533a\u95f4\u4fe1\u606f`;
}

function renderArchiveMetrics(metrics, message, predictionMetrics = {}) {
  const target = $("#archive-review-metrics");
  if (!target) return;
  if (!metrics) {
    target.innerHTML = `<div class="archive-metric-chip"><span>状态</span><strong style="font-size:14px;">${htmlEscape(message || "暂无实际价格数据")}</strong></div>`;
    return;
  }
  const scenarioMetrics = predictionMetrics?.scenario_similarity_adjusted_price;
  const realtimeMetrics = predictionMetrics?.realtime_predicted_price;
  const items = [
    ["MAE", "archiveMetricMae", formatMetricCell(metrics.mae)],
    ["RMSE", "archiveMetricRmse", formatMetricCell(metrics.rmse)],
    ["实时模型MAE", "archiveMetricMae", realtimeMetrics ? formatMetricCell(realtimeMetrics.mae) : "-"],
    ["实时模型RMSE", "archiveMetricRmse", realtimeMetrics ? formatMetricCell(realtimeMetrics.rmse) : "-"],
    ["实时方向准确率", "archiveMetricDirectionAccuracy", realtimeMetrics ? formatPercentCell(realtimeMetrics.direction_accuracy) : "-"],
    ["场景修正MAE", "archiveMetricMae", scenarioMetrics ? formatMetricCell(scenarioMetrics.mae) : "-"],
    ["场景修正RMSE", "archiveMetricRmse", scenarioMetrics ? formatMetricCell(scenarioMetrics.rmse) : "-"],
    ["最大误差", "archiveMetricMaxAbsError", formatMetricCell(metrics.max_abs_error)],
    ["P90误差", "archiveMetricP90AbsError", formatMetricCell(metrics.p90_abs_error)],
    ["方向准确率", "archiveMetricDirectionAccuracy", formatPercentCell(metrics.direction_accuracy)],
    ["Bias", "archiveMetricBias", formatMetricCell(metrics.bias)],
  ];
  target.innerHTML = items
    .map(
      ([label, helpKey, value]) => `
        <div class="archive-metric-chip">
          <span class="metric-label">${htmlEscape(label)} <button class="help-trigger static-help" type="button" data-help-key="${helpKey}" aria-expanded="false">?</button></span>
          <strong>${value}</strong>
        </div>
      `,
    )
    .join("");
}

function renderArchiveDetails(record = {}, rows = []) {
  const target = $("#archive-review-details");
  if (!target) return;
  if (!record.archive_id) {
    target.innerHTML = `<div class="archive-detail-item">暂无预测记录</div>`;
    return;
  }
  const segmentModels = record.selected_segment_price_models || {};
  const segmentModelText = Object.entries(segmentModels)
    .map(([segment, model]) => `${segment}: ${model}`)
    .join("<br/>") || "-";
  const referenceDaysByStrategy = record.reference_days_by_strategy || {};
  const recentDays = referenceDaysByStrategy.recent_n_days || record.reference_days_requested || "-";
  const sameTypeDays = referenceDaysByStrategy.recent_same_type_days || "-";
  const referenceText = record.reference_strategy_key === "comparison" || record.comparison_predictions
    ? `最近天数：${recentDays}天<br/>同类型日个数：${sameTypeDays}个`
    : `${record.reference_strategy_label || record.reference_strategy_key || "-"} / ${record.reference_days_requested || "-"}天`;
  const items = [
    ["\u4ef7\u683c\u533a\u95f4\u4fe1\u606f", archiveIntervalInfoText(rows)],
    ["模型版本", record.model_run_id || "-"],
    ["相似法参考", referenceText],
    ["时段结构", `${record.segment_count || "-"} 段`],
    ["每段使用模型", segmentModelText],
    ["预测文件", record.forecast_file || "-"],
    ["输出文件", record.output_file || "-"],
    ["保存时间", record.created_at || "-"],
  ];
  target.innerHTML = items
    .map(([label, value]) => `<div class="archive-detail-item"><strong>${htmlEscape(label)}</strong><br/>${String(value).includes("<br/>") ? value : htmlEscape(value)}</div>`)
    .join("");
}

function renderPredictionArchiveDetail(data, fallbackMessage = "暂无预测留痕") {
  const meta = $("#archive-review-meta");
  const chart = ensureArchiveReviewChart();
  const record = data?.record || {};
  const rows = data?.rows || [];
  renderArchiveMetrics(data?.metrics, data?.message || fallbackMessage, data?.prediction_metrics || {});
  renderArchiveDetails(record, rows);
  if (meta) {
    const archiveReferenceLabel = record.reference_strategy_key === "comparison" || record.comparison_predictions
      ? "双参考口径"
      : record.reference_strategy_label || record.reference_strategy_key || "-";
    meta.textContent = record.archive_id
      ? `${record.forecast_date || "-"}｜${archiveReferenceLabel}｜${data?.message || "已匹配实际价格"}`
      : fallbackMessage;
  }
  if (!chart) return;
  if (!rows.length) {
    chart.setOption({ title: { text: fallbackMessage, left: "center", top: "middle", textStyle: { color: "#667085", fontSize: 14 } } }, true);
    return;
  }
  const comparisonEntries = referenceStrategyOrder
    .map((strategyKey) => [strategyKey, data?.comparison_predictions?.[strategyKey]])
    .filter(([, variant]) => variant?.rows?.length);
  const baseRows = comparisonEntries[0]?.[1]?.rows || rows;
  let intervalTooltipRows = rows;
  const periods = baseRows.map((row) => row.period);
  const actual = baseRows.map((row) => archiveSeriesValue(row, "actual_price"));
  const realtimeActual = baseRows.map((row) => archiveSeriesValue(row, "realtime_actual_price"));
  const legendData = [];
  const series = [];
  const appendArchiveSeries = (name, targetRows, column, lineStyle = {}) => {
    const dataPoints = targetRows.map((row) => archiveSeriesValue(row, column));
    if (!dataPoints.some((value) => value !== null)) return;
    legendData.push(name);
    series.push({
      name,
      type: "line",
      smooth: true,
      showSymbol: false,
      data: dataPoints,
      lineStyle: { width: 2, ...lineStyle },
    });
  };
  if (comparisonEntries.length) {
    comparisonEntries.forEach(([strategyKey, variant]) => {
      const referenceDays = predictionReferenceDaysForStrategy(strategyKey, variant);
      const strategyLabel = formatReferenceStrategyLabel(strategyKey, variant.reference_strategy_label || referenceStrategyLabelMap[strategyKey], referenceDays);
      legendData.push(`${strategyLabel}模型预测`, `${strategyLabel}相似参考`);
      series.push(
        {
          name: `${strategyLabel}模型预测`,
          type: "line",
          smooth: true,
          showSymbol: false,
          data: variant.rows.map((row) => archiveSeriesValue(row, "predicted_price")),
          lineStyle: { width: 3 },
        },
        {
          name: `${strategyLabel}相似参考`,
          type: "line",
          smooth: true,
          showSymbol: false,
          data: variant.rows.map((row) => archiveSeriesValue(row, "net_load_only_similar_price")),
          lineStyle: { width: 2, type: "dashed" },
        },
      );
    });
  } else {
    legendData.push("模型预测价格");
    series.push(
      { name: "模型预测价格", type: "line", smooth: true, showSymbol: false, data: rows.map((row) => archiveSeriesValue(row, "predicted_price")), lineStyle: { width: 3 } },
    );
    appendArchiveSeries("净负荷相似法预测价格", rows, "net_load_only_similar_price", { type: "dashed" });
    appendArchiveSeries("KNN相似法预测价格", rows, "knn_similar_price", { type: "dotted" });
    appendArchiveSeries("加权KNN回归预测价格", rows, "weighted_knn_regression_price", { type: "dashed" });
  }
  if (comparisonEntries.length) {
    const selectedKey = record.selected_strategy_key || "recent_n_days";
    const selectedVariant = data?.comparison_predictions?.[selectedKey]?.rows?.length
      ? data.comparison_predictions[selectedKey]
      : comparisonEntries[0][1];
    intervalTooltipRows = selectedVariant.rows;
    legendData.length = 0;
    series.length = 0;
    legendData.push("模型预测");
    series.push({
      name: "模型预测",
      type: "line",
      smooth: true,
      showSymbol: false,
      data: selectedVariant.rows.map((row) => archiveSeriesValue(row, "predicted_price")),
      lineStyle: { width: 3 },
    });
    comparisonEntries.forEach(([strategyKey, variant]) => {
      const referenceDays = predictionReferenceDaysForStrategy(strategyKey, variant);
      const strategyLabel = formatReferenceStrategyLabel(strategyKey, variant.reference_strategy_label || referenceStrategyLabelMap[strategyKey], referenceDays);
      appendArchiveSeries(`${strategyLabel}净负荷相似法`, variant.rows, "net_load_only_similar_price", { type: "dashed" });
      appendArchiveSeries(`${strategyLabel}KNN相似法`, variant.rows, "knn_similar_price", { type: "dotted" });
      appendArchiveSeries(`${strategyLabel}加权KNN回归`, variant.rows, "weighted_knn_regression_price", { type: "dashed" });
    });
  }
  appendArchiveSeries("实时模型预测价格", intervalTooltipRows || rows, "realtime_predicted_price", { width: 3 });
  appendArchiveSeries("场景修正参考价", intervalTooltipRows || rows, "scenario_similarity_adjusted_price", { type: "dashed" });
  if (actual.some((value) => value !== null)) {
    legendData.splice(1, 0, "实际日前价格");
    series.splice(1, 0, { name: "实际日前价格", type: "line", smooth: true, showSymbol: false, data: actual, lineStyle: { width: 3 } });
  }
  if (realtimeActual.some((value) => value !== null)) {
    legendData.push("实际实时价格");
    series.push({ name: "实际实时价格", type: "line", smooth: true, showSymbol: false, data: realtimeActual, lineStyle: { width: 3, type: "dashed" } });
  }
  const archiveRowByPeriod = new Map((intervalTooltipRows || []).map((row) => [String(row.period), row]));
  chart.setOption(
    {
      backgroundColor: "transparent",
      color: ["#1677ff", "#ff4d4f", "#52c41a", "#13c2c2", "#722ed1", "#fa8c16", "#2f54eb", "#a0d911", "#eb2f96"],
      tooltip: {
        trigger: "axis",
        confine: true,
        formatter(params) {
          const items = Array.isArray(params) ? params : [params];
          const title = items[0]?.axisValueLabel ?? items[0]?.name ?? "";
          const row = archiveRowByPeriod.get(String(title));
          const periodLabel = row?.period ?? title;
          const periodTime = formatPeriodClockTime(periodLabel);
          const periodTitle = periodTime
            ? `\u65f6\u6bb5 ${periodLabel}\uff08${periodTime}\uff09`
            : `\u65f6\u6bb5 ${periodLabel}`;
          const lines = items
            .filter((item) => item?.value !== null && item?.value !== undefined && item?.value !== "")
            .map(
              (item) =>
                `${item.marker || ""}<span style="margin-right:12px;">${item.seriesName}</span><strong>${formatChartTooltipValue(item.value)}</strong>`,
            )
            .join("<br/>");
          return `<div style="font-weight:800;margin-bottom:6px;">${htmlEscape(periodTitle)}</div>${lines}${renderArchiveIntervalBlock(row)}`;
        },
      },
      legend: { top: 8, data: legendData },
      grid: { left: 56, right: 28, top: 52, bottom: 42 },
      xAxis: { type: "category", boundaryGap: false, data: periods },
      yAxis: { type: "value", name: "元/MWh", scale: true },
      series,
    },
    true,
  );
}

function renderRollingBacktest(metadata = {}) {
  const tbody = $("#rolling-backtest-table tbody");
  if (!tbody) return;
  const backtests = metadata.rolling_backtest_metrics || {};
  const rows = Object.entries(backtests);
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="10">暂无滚动回测数据</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(([days, row]) => {
      const overall = row.overall || {};
      const netLoadOnlyBaseline = row.net_load_only_baseline || {};
      const high = row.spike_errors?.high || {};
      const evening = row.segments?.evening_peak || {};
      const netLoadOnlyCompare = row.model_vs_net_load_only_similarity || {};
      return `
        <tr>
          <td>最近 ${htmlEscape(days)} 天</td>
          <td>${formatMetricCell(overall.mae)}</td>
          <td>${formatMetricCell(overall.rmse)}</td>
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
  const netLoadOnlyCompare30 = backtest30.model_vs_net_load_only_similarity || backtest14.model_vs_net_load_only_similarity || {};
  const netLoadOnlyImprovement = Number(netLoadOnlyCompare30.mae_improvement);
  const rows = [
    ["最近14天整体", overall14.mae, "平均每个点差多少钱", healthText(overall14.mae, 35, 55)],
    ["最近30天整体", overall30.mae, "更接近真实长期使用", healthText(overall30.mae, 45, 70)],
    ["高价尖峰", high30.mae, "价格冲高时能不能跟上", healthText(high30.mae, 80, 150)],
    ["晚高峰", evening30.mae, "最容易影响交易判断的时段", healthText(evening30.mae, 50, 80)],
    ["方向判断", overall30.direction_accuracy ?? overall14.direction_accuracy, "上涨/下跌方向是否判断对", healthText(overall30.direction_accuracy ?? overall14.direction_accuracy, 65, 55, false)],
    ["净负荷相似法对比", netLoadOnlyCompare30.mae_improvement, "正数表示模型比净负荷相似法平均误差更小", Number.isFinite(netLoadOnlyImprovement) ? (netLoadOnlyImprovement > 0 ? "模型更好" : "净负荷相似法更好或持平") : "暂无数据"],
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
  if (value === null || value === undefined || value === "") return "-";
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return "-";
  return numericValue.toFixed(2);
}

function formatPercentCell(value) {
  const formatted = formatMetricCell(value);
  return formatted === "-" ? "-" : `${formatted}%`;
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return `${(numeric * 100).toFixed(1)}%`;
}

function formatPrice(value) {
  const numeric = Number(Array.isArray(value) ? value[1] : value);
  if (!Number.isFinite(numeric)) return "-";
  return numeric.toFixed(2);
}

function formatBestIterationCell(variant) {
  const averageValue = Number(variant.best_iteration_avg);
  const maxValue = Number(variant.best_iteration_max);
  if (!Number.isFinite(averageValue) && !Number.isFinite(maxValue)) return "-";
  const averageText = Number.isFinite(averageValue) ? averageValue.toFixed(0) : "-";
  const maxText = Number.isFinite(maxValue) ? maxValue.toFixed(0) : "-";
  return `${averageText} / ${maxText}`;
}

function formatBooleanText(value, trueText = "是", falseText = "否") {
  if (value === true) return trueText;
  if (value === false) return falseText;
  return "-";
}

function formatChartTooltipValue(value) {
  const rawValue = Array.isArray(value) ? value[value.length - 1] : value;
  const numericValue = Number(rawValue);
  if (!Number.isFinite(numericValue)) return rawValue ?? "-";
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 2,
  }).format(numericValue);
}

function formatPeriodClockTime(period) {
  const numericPeriod = Number(period);
  if (!Number.isFinite(numericPeriod)) return "";
  const totalMinutes = Math.round(numericPeriod * 15);
  if (totalMinutes < 0 || totalMinutes > 1440) return "";
  if (totalMinutes === 1440) return "24:00";
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function sortVersionsForDisplay(versions) {
  const sortKey = currentVersionSort();
  const list = [...versions];
  const metricKeyMap = {
    final_mae_asc: "final_mae",
    final_rmse_asc: "final_rmse",
    rolling_14_mae_asc: "rolling_14_mae",
    rolling_30_mae_asc: "rolling_30_mae",
    rolling_30_high_price_mae_asc: "rolling_30_high_price_mae",
    rolling_30_evening_peak_mae_asc: "rolling_30_evening_peak_mae",
    rolling_30_thermal_space_similarity_mae_asc: "rolling_30_thermal_space_similarity_mae",
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

function versionAlgorithmVariants(item) {
  return Array.isArray(item.algorithm_variants) && item.algorithm_variants.length
    ? item.algorithm_variants
    : [
        {
          model_backend_label: item.selected_model_backend_label || item.selected_model_backend || "-",
          final_mae: item.final_mae,
          final_rmse: item.final_rmse,
          max_abs_error: item.rolling_30_max_abs_error,
          direction_accuracy: item.rolling_30_direction_accuracy,
          best_iteration_avg: item.best_iteration_avg,
          best_iteration_max: item.best_iteration_max,
          best_iteration_min: item.best_iteration_min,
          valid_rows: item.sample_rows,
          is_selected: true,
        },
      ];
}

function renderVersionAlgorithmCell(variant) {
  const selectedClass = variant.is_selected ? " selected" : "";
  const selectedText = variant.is_selected ? `<span class="algorithm-selected-mark">\u5f53\u524d</span>` : "";
  return `
    <span class="algorithm-chip${selectedClass}">
      <span class="algorithm-chip-name">${htmlEscape(variant.model_backend_label || variant.model_backend || variant.variant_key || "-")}</span>
      ${selectedText}
    </span>
  `;
}

function renderVersionStatusTags(item) {
  const tags = [];
  if (item.is_default) tags.push(`<span class="status-tag default">默认模型</span>`);
  if (item.is_previous) tags.push(`<span class="status-tag previous">上一版</span>`);
  if (item.is_pinned_default && !item.is_default) tags.push(`<span class="status-tag pinned">固定默认</span>`);
  return tags.join(" ") || `<span class="status-tag muted">历史版本</span>`;
}

function renderVersionModelTitle(item) {
  const summary = item.version_summary || {};
  const price = summary.price_model || {};
  const algorithm = price.backend_label || item.selected_model_backend_label || item.selected_model_backend || "-";
  return `
    <div class="version-row-title">${htmlEscape(item.version_key || item.run_id || "-")}</div>
    <div class="version-row-subtitle">
      ${htmlEscape(algorithm)} · ${htmlEscape(price.selected_model_key || item.selected_model_key || "-")}
      · ${htmlEscape(item.segment_count ?? "-")} 段 · ${htmlEscape(item.sample_rows ?? "-")} 行
    </div>
    <div class="version-row-chips">
      ${versionAlgorithmVariants(item).slice(0, 3).map(renderVersionAlgorithmCell).join("")}
    </div>
  `;
}

function renderModelBadge(status, mainValue, subValue = "") {
  return `
    <div class="version-model-badge ${status !== true ? "disabled" : ""}">
      <strong>${htmlEscape(mainValue || "-")}</strong>
      <span>${htmlEscape(subValue || "")}</span>
    </div>
  `;
}

function renderVersionDetailField(label, value) {
  return `
    <div class="version-detail-field">
      <span>${htmlEscape(label)}</span>
      <strong>${htmlEscape(value ?? "-")}</strong>
    </div>
  `;
}

function collectOpenVersionDetailKeys() {
  const keys = new Set(App.openVersionDetailKeys || []);
  $$("#versions-table .version-detail-toggle[open]").forEach((node) => {
    const key = node.dataset.versionKey;
    if (key) keys.add(key);
  });
  return keys;
}

function rememberVersionDetailState(versionKey, isOpen) {
  if (!App.openVersionDetailKeys) App.openVersionDetailKeys = new Set();
  const key = String(versionKey || "");
  if (!key) return;
  if (isOpen) {
    App.openVersionDetailKeys.add(key);
  } else {
    App.openVersionDetailKeys.delete(key);
  }
}

function renderVersionDetailSection(title, rows) {
  return `
    <section class="version-detail-section">
      <div class="version-detail-title">${htmlEscape(title)}</div>
      <div class="version-detail-grid">
        ${rows.map(([label, value]) => renderVersionDetailField(label, value)).join("")}
      </div>
    </section>
  `;
}

function formatVersionWindow(config = {}) {
  const range = config.start_date || config.end_date ? `${config.start_date || "-"} ~ ${config.end_date || "-"}` : "-";
  return `${range} / ${config.training_window_days ?? "-"} 天 / 验证 ${config.valid_days ?? "-"} 天`;
}

function renderSelectedSegmentModels(models = {}) {
  const entries = Object.entries(models || {});
  if (!entries.length) return "-";
  return entries.slice(0, 6).map(([segment, model]) => `${segment}: ${model}`).join("；");
}

function renderIntervals(intervals = []) {
  if (!Array.isArray(intervals) || !intervals.length) return "-";
  return intervals.map((item) => item.label || `${item.min ?? "-"}-${item.max ?? "-"}`).join(" / ");
}

function renderVersionDetail(item) {
  const detail = item.version_detail || {};
  const summary = item.version_summary || {};
  const training = detail.training || {};
  const price = detail.price_model || {};
  const interval = detail.price_interval_model || {};
  const thermal = detail.thermal_capacity_model || {};
  const intervalSummary = summary.price_interval_model || {};
  const thermalSummary = summary.thermal_capacity_model || {};
  return `
    <div class="version-detail-layout">
      ${renderVersionDetailSection("训练窗口", [
        ["价格预测模型", formatVersionWindow(training.price || {})],
        ["价格区间模型", formatVersionWindow(training.interval || {})],
        ["开机容量模型", formatVersionWindow(training.thermal_capacity || {})],
      ])}
      ${renderVersionDetailSection("价格预测模型", [
        ["模型后端", price.selected_model_backend_label || item.selected_model_backend_label || "-"],
        ["最优变体", price.selected_model_key || item.selected_model_key || "-"],
        ["候选变体数", (price.algorithm_variants || item.algorithm_variants || []).length],
        ["分段数量", price.segment_count ?? item.segment_count ?? "-"],
        ["每段模型", renderSelectedSegmentModels(price.selected_segment_price_models)],
        ["高价加权", formatBooleanText(price.high_price_weighting?.enabled, "开启", "关闭")],
      ])}
      ${renderVersionDetailSection("价格区间模型", [
        ["状态", enabledText(interval.enabled ?? intervalSummary.enabled)],
        ["模型后端", interval.selected_model_backend_label || interval.selected_model_backend || "-"],
        ["最优模型", interval.selected_model_key || intervalSummary.selected_model_key || "-"],
        ["区间数量", interval.interval_count ?? intervalSummary.interval_count ?? "-"],
        ["特征数量", interval.feature_count ?? intervalSummary.feature_count ?? "-"],
        ["训练/验证样本", `${interval.train_rows ?? intervalSummary.train_rows ?? "-"} / ${interval.valid_rows ?? intervalSummary.valid_rows ?? "-"}`],
        ["区间配置", renderIntervals(interval.intervals)],
        ["准确率", versionMetricText(interval.metrics?.accuracy ?? intervalSummary.accuracy, formatPercent)],
        ["高价召回", versionMetricText(interval.metrics?.high_price_recall ?? intervalSummary.high_price_recall, formatPercent)],
      ])}
      ${renderVersionDetailSection("开机容量模型", [
        ["状态", enabledText(thermal.enabled ?? thermalSummary.enabled)],
        ["模型后端", thermal.selected_model_backend_label || thermal.selected_model_backend || thermalSummary.selected_model_backend_label || "-"],
        ["最优模型", thermal.selected_model_key || thermalSummary.selected_model_key || "-"],
        ["候选变体数", thermal.model_variants ? Object.keys(thermal.model_variants).length : thermalSummary.candidate_count ?? "-"],
        ["MAE", versionMetricText(thermal.metrics?.mae ?? thermalSummary.mae)],
        ["RMSE", versionMetricText(thermal.metrics?.rmse ?? thermalSummary.rmse)],
        ["最大误差", versionMetricText(thermal.metrics?.max_error ?? thermalSummary.max_error)],
        ["偏差", versionMetricText(thermal.metrics?.bias ?? thermalSummary.bias)],
        ["特征数量", thermal.feature_count ?? thermalSummary.feature_count ?? "-"],
        ["训练/验证样本", `${thermal.train_rows ?? "-"} / ${thermal.valid_rows ?? "-"}`],
      ])}
    </div>
  `;
}

function renderModelVersionOptions(selector, versions, defaultLabel) {
  const select = $(selector);
  if (!select) return;
  const currentValue = select.value || "";
  const options = (versions || []).map((item) => {
    const tags = [];
    if (item.is_default) tags.push("默认");
    if (item.segment_count) tags.push(`${item.segment_count}段`);
    const label = `${item.version_key}${tags.length ? `（${tags.join(" / ")}）` : ""}`;
    return `<option value="${htmlEscape(item.version_key)}">${htmlEscape(label)}</option>`;
  });
  select.innerHTML = `<option value="">${htmlEscape(defaultLabel)}</option>${options.join("")}`;
  if ([...select.options].some((option) => option.value === currentValue)) {
    select.value = currentValue;
  }
}

function renderPredictionModelSelect(versions) {
  renderModelVersionOptions("#predict-model-version", versions, "使用当前默认日前模型");
}

function renderRealtimePredictionModelSelect(versions) {
  renderModelVersionOptions("#predict-realtime-model-version", versions, "使用当前默认实时模型");
}

async function loadRealtimeModelVersions() {
  const data = await request("/api/model/versions?target=realtime");
  renderRealtimePredictionModelSelect(data.versions || []);
  return data;
}

function renderMultiDayModelSelect(versions) {
  const select = $("#multi-day-model-version");
  if (!select) return;
  const currentValue = select.value || "";
  const options = (versions || []).map((item) => {
    const tags = [];
    if (item.is_default) tags.push("默认");
    if (item.segment_count) tags.push(`${item.segment_count}段`);
    const label = `${item.version_key}${tags.length ? `（${tags.join(" / ")}）` : ""}`;
    return `<option value="${htmlEscape(item.version_key)}">${htmlEscape(label)}</option>`;
  });
  select.innerHTML = `<option value="">使用默认启用模型</option>${options.join("")}`;
  if ([...select.options].some((option) => option.value === currentValue)) {
    select.value = currentValue;
  }
}

function renderVersions(versions) {
  const openDetailKeys = collectOpenVersionDetailKeys();
  const selectedKeys = new Set(selectedVersionKeys());
  const currentVersionKey = $("#version-select")?.value || "";
  const metadata = App.versionModelMetadata || App.currentModelMetadata || {};
  const enrichedVersions = (versions || []).map((item) => enrichCurrentVersionItem(item, metadata));
  const displayVersions = sortVersionsForDisplay(enrichedVersions);
  App.versions = displayVersions;
  setVersionSort(currentVersionSort());
  if (App.versionTarget !== "realtime") {
    renderPredictionModelSelect(displayVersions);
    renderMultiDayModelSelect(displayVersions);
  }
  $("#version-select").innerHTML = displayVersions.length
    ? displayVersions.map((item) => `<option value="${htmlEscape(item.version_key)}">${htmlEscape(item.label || item.version_key)}</option>`).join("")
    : `<option value="">暂无历史模型</option>`;
  if (displayVersions.some((item) => String(item.version_key) === currentVersionKey)) {
    $("#version-select").value = currentVersionKey;
  }

  const tbody = $("#versions-table tbody");
  if (!displayVersions.length) {
    tbody.innerHTML = `<tr><td colspan="12">暂无历史模型版本</td></tr>`;
    syncSelectAllVersionsState();
    return;
  }
  tbody.innerHTML = displayVersions
    .map((item) => {
      const checked = selectedKeys.has(String(item.version_key)) ? " checked" : "";
      const summary = item.version_summary || {};
      const price = summary.price_model || {};
      const interval = summary.price_interval_model || {};
      const thermal = summary.thermal_capacity_model || {};
      const versionKey = String(item.version_key || "");
      const detailOpen = openDetailKeys.has(versionKey) ? " open" : "";
      return `
        <tr class="version-main-row">
          <td><input type="checkbox" class="version-check" value="${htmlEscape(item.version_key)}"${checked}></td>
          <td>${renderVersionModelTitle(item)}</td>
          <td>${htmlEscape(item.created_at || "-")}</td>
          <td>${htmlEscape(modelVersionDateRange(item))}</td>
          <td class="metric-strong">${formatMetricCell(price.mae ?? item.final_mae)}</td>
          <td class="metric-strong">${formatMetricCell(price.rmse ?? item.final_rmse)}</td>
          <td>${formatMetricCell(price.rolling_30_mae ?? item.rolling_30_mae)}</td>
          <td>${renderModelBadge(interval.enabled, versionMetricText(interval.accuracy, formatPercent), `高价召回 ${versionMetricText(interval.high_price_recall, formatPercent)}`)}</td>
          <td>${renderModelBadge(thermal.enabled, versionMetricText(thermal.mae), `RMSE ${versionMetricText(thermal.rmse)}`)}</td>
          <td>${formatMetricCell(price.high_price_mae ?? item.rolling_30_high_price_mae)}</td>
          <td>${renderVersionStatusTags(item)}</td>
          <td><span class="version-detail-cue">下方展开</span></td>
        </tr>
        <tr class="version-detail-row">
          <td></td>
          <td colspan="11">
            <details class="version-detail-toggle" data-version-key="${htmlEscape(versionKey)}"${detailOpen}>
              <summary>展开完整详情</summary>
              ${renderVersionDetail(item)}
            </details>
          </td>
        </tr>
      `;
    })
    .join("");
  syncSelectAllVersionsState();
  updateVersionSortHeaders();
  injectHelpAffordances($("#versions-table"));
}

function renderVersionDiagnostics(target, metadata = {}) {
  const panel = $("#version-diagnostics-panel");
  if (panel) panel.dataset.target = target;
  renderMetrics(metadata.metrics || {});
  renderModelComparison(metadata);
  renderRollingBacktest(metadata);
  renderModelHealth(metadata);
  renderDailyErrorRank(metadata);
}

function renderTargetModelVersions(target = "dayahead", versions = [], metadata = {}) {
  App.versionTarget = target === "realtime" ? "realtime" : "dayahead";
  App.versionModelMetadata = metadata || {};
  App.modelVersionsByTarget[App.versionTarget] = versions || [];
  App.modelMetadataByTarget[App.versionTarget] = metadata || {};
  $$("#model-version-target [data-target]").forEach((button) => {
    button.classList.toggle("active", button.dataset.target === App.versionTarget);
  });
  renderVersions(versions || []);
  renderCurrentVersionOverview(versions || [], metadata || {});
  renderVersionDiagnostics(App.versionTarget, metadata || {});
}

async function loadModelVersionsForTarget(target = "dayahead") {
  const normalizedTarget = target === "realtime" ? "realtime" : "dayahead";
  const [versionsData, currentModel] = await Promise.all([
    request(`/api/model/versions?target=${encodeURIComponent(normalizedTarget)}`),
    request(`/api/model/current?target=${encodeURIComponent(normalizedTarget)}`),
  ]);
  renderTargetModelVersions(normalizedTarget, versionsData.versions || [], currentModel.metadata || {});
  await loadModelCandidateRankings();
  return versionsData;
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

function renderMultiDayTemplate(columns, rows, metaText) {
  App.multiDayTemplateRows = rows || [];
  const meta = $("#multi-day-template-meta");
  const table = $("#multi-day-template-table");
  if (meta) meta.textContent = metaText || "-";
  if (!table) return;
  if (!columns?.length) {
    table.innerHTML = `<thead><tr><th>字段</th></tr></thead><tbody><tr><td>暂无N天预测文件数据</td></tr></tbody>`;
    return;
  }
  const head = `<thead><tr>${columns.map((col) => `<th>${htmlEscape(col)}</th>`).join("")}</tr></thead>`;
  const body = (rows || [])
    .map(
      (row) => `
        <tr>
          ${columns.map((col) => `<td contenteditable="true" data-col="${htmlEscape(col)}">${htmlEscape(row[col] ?? "")}</td>`).join("")}
        </tr>
      `,
    )
    .join("");
  table.innerHTML = `${head}<tbody>${body}</tbody>`;
}

function collectMultiDayTemplateRows() {
  return $$("#multi-day-template-table tbody tr").map((tr) => {
    const row = {};
    tr.querySelectorAll("td").forEach((td) => {
      row[td.dataset.col] = td.textContent.trim();
    });
    return row;
  });
}

async function loadMultiDayTemplate() {
  const data = await request("/api/forecast/multi-day-template");
  const detectedDates = data.detected_forecast_dates?.length ? ` | 后续日期：${data.detected_forecast_dates.join("、")}` : "";
  const baselineDate = data.baseline_date ? ` | 基准日：${data.baseline_date}` : "";
  renderMultiDayTemplate(data.columns || [], data.rows || [], `${data.sheet_name || "预测文件-N天"} · 共 ${data.row_count || 0} 行${baselineDate}${detectedDates}`);
}

async function saveMultiDayTemplate() {
  await request("/api/forecast/multi-day-template/save", {
    method: "POST",
    body: JSON.stringify({ rows: collectMultiDayTemplateRows() }),
  });
  showToast("预测文件-N天已保存");
}

function currentMultiDayRecentReferenceDays() {
  const value = Number($("#multi-day-recent-reference-days")?.value || App.config?.default_recent_reference_days || App.config?.default_reference_days || 1);
  return clampReferenceDays(value, 1);
}

function currentMultiDayKnnSimilarityConfig() {
  return {
    knn_k: readPositiveInt("#multi-day-knn-similar-k", App.config?.default_knn_similarity?.knn_k || 5),
    knn_max_distance: readPositiveNumber("#multi-day-knn-similar-max-distance", App.config?.default_knn_similarity?.knn_max_distance || 3.0),
    weighted_knn_k: readPositiveInt("#multi-day-weighted-knn-k", App.config?.default_knn_similarity?.weighted_knn_k || 5),
    weighted_knn_max_distance: readPositiveNumber("#multi-day-weighted-knn-max-distance", App.config?.default_knn_similarity?.weighted_knn_max_distance || 3.0),
  };
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

function clampReferenceDays(value, fallback = 1) {
  const maxValue = Number(App.config?.max_reference_days || 100);
  return Number.isFinite(value) && value >= 1 ? Math.min(Math.round(value), maxValue) : fallback;
}

function currentRecentReferenceDays() {
  const value = Number($("#recent-reference-days")?.value || App.config?.default_recent_reference_days || App.config?.default_reference_days || 1);
  return clampReferenceDays(value, 1);
}

function currentSameTypeReferenceDays() {
  const value = Number($("#same-type-reference-days")?.value || App.config?.default_same_type_reference_days || App.config?.default_reference_days || 1);
  return clampReferenceDays(value, 1);
}

function currentReferenceDays() {
  return Math.max(currentRecentReferenceDays(), currentSameTypeReferenceDays());
}

function predictionReferenceDaysForStrategy(strategyKey, variant = null) {
  const requested = Number(variant?.reference_days_requested);
  if (Number.isFinite(requested) && requested >= 1) return clampReferenceDays(requested, 1);
  if (strategyKey === "recent_same_type_days") return currentSameTypeReferenceDays();
  return currentRecentReferenceDays();
}

function currentTrainingMode() {
  return currentModelTrainingMode("price");
}

function readPositiveInt(selector, fallback) {
  const value = Number($(selector)?.value || fallback);
  return Number.isFinite(value) && value >= 1 ? Math.round(value) : fallback;
}

function readPositiveNumber(selector, fallback) {
  const value = Number($(selector)?.value || fallback);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function currentKnnSimilarityConfig() {
  return {
    knn_k: readPositiveInt("#knn-similar-k", App.config?.default_knn_similarity?.knn_k || 5),
    knn_max_distance: readPositiveNumber("#knn-similar-max-distance", App.config?.default_knn_similarity?.knn_max_distance || 3.0),
    weighted_knn_k: readPositiveInt("#weighted-knn-k", App.config?.default_knn_similarity?.weighted_knn_k || 5),
    weighted_knn_max_distance: readPositiveNumber("#weighted-knn-max-distance", App.config?.default_knn_similarity?.weighted_knn_max_distance || 3.0),
  };
}

function currentModelTrainingMode(prefix, target = "dayahead") {
  const fieldPrefix = `${trainingTargetPrefix(target)}${prefix}`;
  return $(`#${fieldPrefix}-training-mode`)?.value || App.config?.default_training_mode || "rolling_window";
}

function currentTrainingWindowDays(prefix = "price", target = "dayahead") {
  const fieldPrefix = `${trainingTargetPrefix(target)}${prefix}`;
  return readPositiveInt(`#${fieldPrefix}-training-window-days`, App.config?.default_training_window_days || 60);
}

function collectModelTrainingConfig(prefix, target = "dayahead") {
  const fieldPrefix = `${trainingTargetPrefix(target)}${prefix}`;
  const trainingMode = currentModelTrainingMode(prefix, target);
  return {
    training_mode: trainingMode,
    training_window_days: currentTrainingWindowDays(prefix, target),
    start_date: $(`#${fieldPrefix}-train-start-date`)?.value || null,
    end_date: $(`#${fieldPrefix}-train-end-date`)?.value || null,
    enable_start: Boolean($(`#${fieldPrefix}-enable-start`)?.checked),
    enable_end: Boolean($(`#${fieldPrefix}-enable-end`)?.checked),
    valid_days: readPositiveInt(`#${fieldPrefix}-valid-days`, 14),
    num_boost_round: readPositiveInt(`#${fieldPrefix}-num-boost-round`, 400),
  };
}

function currentWindowOptimizationMaxHistoryDays(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  const value = Number(
    $(`#${prefix}window-optimization-max-history-days`)?.value
      || App.config?.default_window_optimization_max_history_days
      || 100,
  );
  return Number.isFinite(value) && value >= 1 ? Math.round(value) : 100;
}

function currentWindowOptimizationValidDays(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  const value = Number($(`#${prefix}window-optimization-valid-days`)?.value || App.config?.default_window_optimization_valid_days || 10);
  return Number.isFinite(value) && value >= 1 ? Math.round(value) : 10;
}

function currentWindowOptimizationRollingHorizons(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  const rawValue = String(
    $(`#${prefix}window-optimization-rolling-horizons`)?.value
      || (App.config?.default_window_optimization_rolling_backtest_horizons || [14]).join(",")
      || "14",
  );
  const values = rawValue
    .replace(/，/g, ",")
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((value) => Number.isInteger(value) && value >= 1 && value <= 365);
  const uniqueValues = [...new Set(values)];
  if (!uniqueValues.length) {
    throw new Error("滚动回测天数至少填写一个有效正整数，例如 14 或 14,30");
  }
  return uniqueValues;
}

function currentWindowOptimizationNumBoostRound(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  const value = Number($(`#${prefix}window-optimization-num-boost-round`)?.value || 400);
  return Number.isFinite(value) && value >= 1 ? Math.round(value) : 400;
}

function currentWindowOptimizationFineRadius(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  const value = Number($(`#${prefix}window-optimization-fine-radius`)?.value || 15);
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

function segmentDraftKey(target = "dayahead") {
  return target === "realtime" ? `${segmentDraftStorageKey}_realtime` : segmentDraftStorageKey;
}

function segmentSearchCountsKey(target = "dayahead") {
  return target === "realtime" ? `${segmentSearchCountsStorageKey}_realtime` : segmentSearchCountsStorageKey;
}

function loadSegmentDrafts(target = "dayahead") {
  try {
    const data = JSON.parse(localStorage.getItem(segmentDraftKey(target)) || "{}");
    return data && typeof data === "object" ? data : {};
  } catch {
    return {};
  }
}

function saveSegmentDraftForCount(count, rows, target = "dayahead") {
  if (!count || !Array.isArray(rows) || !rows.length) return;
  const drafts = loadSegmentDrafts(target);
  drafts[String(count)] = cloneSegmentRows(rows);
  localStorage.setItem(segmentDraftKey(target), JSON.stringify(drafts));
}

function segmentRowsForCount(count, target = "dayahead") {
  const drafts = loadSegmentDrafts(target);
  const savedRows = drafts[String(count)];
  if (Array.isArray(savedRows) && savedRows.length === Number(count)) {
    return cloneSegmentRows(savedRows);
  }
  return buildEvenSegmentRows(Number(count || defaultSegmentCount));
}

function availableSegmentSearchCounts(target = "dayahead") {
  const counts = new Set([3, 6]);
  Object.keys(loadSegmentDrafts(target)).forEach((key) => {
    const count = Number(key);
    if (Number.isInteger(count) && count > 0) counts.add(count);
  });
  const rows = trainingSegmentRows(target);
  if (Array.isArray(rows) && rows.length) counts.add(rows.length);
  return [...counts].sort((a, b) => a - b);
}

function storedSegmentSearchCounts(options, target = "dayahead") {
  const optionSet = new Set(options);
  try {
    const parsed = JSON.parse(localStorage.getItem(segmentSearchCountsKey(target)) || "null");
    if (Array.isArray(parsed)) {
      const counts = parsed.map(Number).filter((count) => optionSet.has(count));
      if (counts.length) return counts;
    }
  } catch {
    // ignore invalid localStorage
  }
  return [defaultSegmentCount].filter((count) => optionSet.has(count));
}

function saveSegmentSearchCounts(counts, target = "dayahead") {
  localStorage.setItem(segmentSearchCountsKey(target), JSON.stringify(counts));
}

function renderSegmentSearchCounts(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  const container = $(`#${prefix}segment-search-counts`);
  if (!container) return;
  const options = availableSegmentSearchCounts(target);
  const selected = new Set(storedSegmentSearchCounts(options, target));
  container.innerHTML = options
    .map((count) => `
      <label class="segment-search-chip">
        <input type="checkbox" value="${count}" ${selected.has(count) ? "checked" : ""} />
        <span>${count} 段</span>
      </label>
    `)
    .join("");
  container.querySelectorAll("input[type='checkbox']").forEach((input) => {
    input.addEventListener("change", () => {
      const counts = Array.from(container.querySelectorAll("input[type='checkbox']:checked")).map((item) => Number(item.value));
      saveSegmentSearchCounts(counts, target);
    });
  });
}

function selectedSegmentSearchCounts(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  const checked = Array.from($$(`#${prefix}segment-search-counts input[type='checkbox']:checked`)).map((item) => Number(item.value));
  const counts = checked.filter((count) => Number.isInteger(count) && count > 0);
  if (!counts.length) throw new Error("请至少选择一个参与寻优的时段数");
  saveSegmentSearchCounts(counts, target);
  return counts;
}

function collectSegmentSearchConfig(target = "dayahead") {
  const rows = trainingSegmentRows(target);
  if (segmentMode(target) === "custom" && rows.length) {
    saveSegmentDraftForCount(rows.length, rows, target);
  }
  const counts = selectedSegmentSearchCounts(target);
  return {
    segment_search_enabled: true,
    segment_search_counts: counts,
    segment_search_configs: counts.map((count) => ({
      segment_count: count,
      segment_config: segmentRowsForCount(count, target),
    })),
  };
}

function segmentMode(target = "dayahead") {
  return $(`#${trainingTargetPrefix(target)}segment-mode`)?.value || "default";
}

function validateSegmentRows(rows, target = "dayahead") {
  if (segmentMode(target) !== "custom") return { ok: true, message: `使用系统默认 ${defaultSegmentCount} 段` };
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

function renderSegmentConfigTable(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  const tbody = $(`#${prefix}segment-config-table tbody`);
  if (!tbody) return;
  const isCustom = segmentMode(target) === "custom";
  const rows = isCustom ? trainingSegmentRows(target) : defaultSegmentRows;
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
  const validation = validateSegmentRows(rows, target);
  const status = $(`#${prefix}segment-validation-text`);
  if (status) {
    status.textContent = validation.message;
    status.classList.toggle("error-text", !validation.ok);
  }
}

function collectSegmentConfig(target = "dayahead") {
  const rows = trainingSegmentRows(target);
  if (segmentMode(target) !== "custom") return { segment_mode: "default", segment_config: null };
  const validation = validateSegmentRows(rows, target);
  if (!validation.ok) {
    throw new Error(validation.message);
  }
  saveSegmentDraftForCount(rows.length, rows, target);
  return {
    segment_mode: "custom",
    segment_config: rows.map((row) => ({
      name: row.name,
      start_time: normalizeTimeText(row.start_time),
      end_time: normalizeTimeText(row.end_time),
    })),
  };
}

function collectHighPriceWeighting(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  return {
    enabled: Boolean($(`#${prefix}high-price-weight-enabled`)?.checked),
    quantile: Number($(`#${prefix}high-price-quantile`)?.value || 0.8),
    multiplier: Number($(`#${prefix}high-price-multiplier`)?.value || 2),
  };
}

function legacyNormalizePriceIntervalRows(rows) {
  const source = Array.isArray(rows) && rows.length >= 2 ? rows : defaultPriceIntervals;
  return source.map((row) => ({
    label: String(row.label || "").trim(),
    min: row.min === null || row.min === undefined || row.min === "" ? null : Number(row.min),
    max: row.max === null || row.max === undefined || row.max === "" ? null : Number(row.max),
  }));
}

function legacyRenderPriceIntervalTable() {
  const body = $("#price-interval-table tbody");
  if (!body) return;
  body.innerHTML = App.priceIntervals
    .map((row, index) => {
      const first = index === 0;
      const last = index === App.priceIntervals.length - 1;
      return `
        <tr>
          <td><input class="table-input interval-label-input" data-index="${index}" value="${htmlEscape(row.label)}" /></td>
          <td><input class="table-input interval-min-input" data-index="${index}" type="number" step="0.01" value="${row.min ?? ""}" ${first ? "disabled" : ""} /></td>
          <td><input class="table-input interval-max-input" data-index="${index}" type="number" step="0.01" value="${row.max ?? ""}" ${last ? "disabled" : ""} /></td>
          <td>${first ? "最低价档" : last ? "最高价档" : "中间价档"}</td>
        </tr>
      `;
    })
    .join("");
  injectHelpAffordances(body);
}

function legacyCollectPriceIntervals() {
  const rows = App.priceIntervals.map((row) => ({ ...row }));
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    row.label = $(`.interval-label-input[data-index="${index}"]`)?.value?.trim() || row.label;
    const minInput = $(`.interval-min-input[data-index="${index}"]`);
    const maxInput = $(`.interval-max-input[data-index="${index}"]`);
    row.min = minInput?.disabled || minInput?.value === "" ? null : Number(minInput.value);
    row.max = maxInput?.disabled || maxInput?.value === "" ? null : Number(maxInput.value);
  }
  for (let index = 0; index < rows.length; index += 1) {
    if (index === 0) rows[index].min = null;
    if (index === rows.length - 1) rows[index].max = null;
    if (index > 0) rows[index].min = rows[index - 1].max;
    if (index < rows.length - 1 && !Number.isFinite(Number(rows[index].max))) {
      throw new Error("价格区间上限必须填写");
    }
    if (index < rows.length - 1 && Number(rows[index].max) <= Number(rows[index].min ?? -Infinity)) {
      throw new Error("价格区间上限必须大于下限");
    }
  }
  App.priceIntervals = rows;
  renderPriceIntervalTable();
  return rows;
}

function formatPriceBoundary(value) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) return "";
  return Number.isInteger(numberValue) ? String(numberValue) : String(Math.round(numberValue * 100) / 100);
}

function priceIntervalLabel(minValue, maxValue) {
  return `${formatPriceBoundary(minValue)}-${formatPriceBoundary(maxValue)}`;
}

function normalizePriceIntervalRows(rows) {
  const source = Array.isArray(rows) && rows.length >= 2 ? rows : defaultPriceIntervals;
  const normalized = source.map((row) => ({
    label: String(row.label || "").trim(),
    min: row.min === null || row.min === undefined || row.min === "" ? null : Number(row.min),
    max: row.max === null || row.max === undefined || row.max === "" ? null : Number(row.max),
  }));
  normalized[0].min = priceIntervalMin;
  normalized[normalized.length - 1].max = priceIntervalMax;
  for (let index = 1; index < normalized.length; index += 1) {
    normalized[index].min = Number.isFinite(Number(normalized[index - 1].max))
      ? Number(normalized[index - 1].max)
      : normalized[index].min;
  }
  return normalized.map((row) => ({
    ...row,
    label: priceIntervalLabel(row.min, row.max),
  }));
}

function renderPriceIntervalTable(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  const body = $(`#${prefix}price-interval-table tbody`);
  if (!body) return;
  setTrainingPriceIntervals(target, normalizePriceIntervalRows(trainingPriceIntervals(target)));
  const intervals = trainingPriceIntervals(target);
  body.innerHTML = intervals
    .map((row, index) => {
      const first = index === 0;
      const last = index === intervals.length - 1;
      return `
        <tr class="price-interval-row">
          <td><span class="interval-range-pill">${htmlEscape(priceIntervalLabel(row.min, row.max))}</span></td>
          <td><input class="mini-input interval-min-input" data-index="${index}" type="number" step="0.01" value="${row.min ?? ""}" disabled /></td>
          <td><input class="mini-input interval-max-input" data-index="${index}" type="number" step="0.01" value="${row.max ?? ""}" ${last ? "disabled" : ""} /></td>
          <td class="interval-note-cell">${first ? "起点固定 0" : last ? "终点固定 1500" : "修改上限后自动衔接"}</td>
          <td class="interval-delete-cell">
            <button class="tiny-action-btn interval-delete-btn" type="button" data-index="${index}" ${intervals.length <= 2 ? "disabled" : ""}>删除</button>
          </td>
        </tr>
      `;
    })
    .join("");
  injectHelpAffordances(body);
}

function collectPriceIntervals(target = "dayahead") {
  const prefix = trainingTargetPrefix(target);
  const rows = trainingPriceIntervals(target).map((row) => ({ ...row }));
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const minInput = $(`#${prefix}price-interval-table .interval-min-input[data-index="${index}"]`);
    const maxInput = $(`#${prefix}price-interval-table .interval-max-input[data-index="${index}"]`);
    row.min = minInput?.value === "" ? null : Number(minInput.value);
    row.max = maxInput?.value === "" ? null : Number(maxInput.value);
  }
  for (let index = 0; index < rows.length; index += 1) {
    if (index === 0) rows[index].min = priceIntervalMin;
    if (index === rows.length - 1) rows[index].max = priceIntervalMax;
    if (index > 0) rows[index].min = rows[index - 1].max;
    if (index < rows.length - 1 && !Number.isFinite(Number(rows[index].max))) {
      throw new Error("价格区间上限必须填写");
    }
    if (Number(rows[index].min) < priceIntervalMin || Number(rows[index].max) > priceIntervalMax) {
      throw new Error("价格区间范围必须在 0 到 1500 之间");
    }
    if (Number(rows[index].max) <= Number(rows[index].min ?? -Infinity)) {
      throw new Error("价格区间上限必须大于下限");
    }
    rows[index].label = priceIntervalLabel(rows[index].min, rows[index].max);
  }
  setTrainingPriceIntervals(target, rows);
  renderPriceIntervalTable(target);
  return rows;
}

function addPriceIntervalRow(target = "dayahead") {
  const rows = collectPriceIntervals(target);
  let splitIndex = 0;
  let widest = -Infinity;
  rows.forEach((row, index) => {
    const width = Number(row.max) - Number(row.min);
    if (Number.isFinite(width) && width > widest) {
      widest = width;
      splitIndex = index;
    }
  });
  if (!Number.isFinite(widest) || widest <= 1) {
    showToast("当前区间太窄，暂不适合继续拆分", "error");
    return;
  }
  const splitAt = Math.round((Number(rows[splitIndex].min) + Number(rows[splitIndex].max)) / 2);
  rows.splice(splitIndex + 1, 0, { label: "", min: splitAt, max: rows[splitIndex].max });
  rows[splitIndex].max = splitAt;
  setTrainingPriceIntervals(target, normalizePriceIntervalRows(rows));
  renderPriceIntervalTable(target);
}

function deletePriceIntervalRow(index, target = "dayahead") {
  const rows = collectPriceIntervals(target);
  if (rows.length <= 2) {
    showToast("价格区间至少保留 2 段", "error");
    return;
  }
  rows.splice(index, 1);
  setTrainingPriceIntervals(target, normalizePriceIntervalRows(rows));
  renderPriceIntervalTable(target);
}

function collectTrainingAdvancedConfig(target = "dayahead") {
  return {
    ...collectSegmentConfig(target),
    high_price_weighting: collectHighPriceWeighting(target),
    price_intervals: collectPriceIntervals(target),
  };
}

function collectWindowOptimizationPayload(target = "dayahead") {
  return {
    force: true,
    max_history_days: currentWindowOptimizationMaxHistoryDays(target),
    valid_days: currentWindowOptimizationValidDays(target),
    num_boost_round: currentWindowOptimizationNumBoostRound(target),
    price_model_config: {
      ...collectModelTrainingConfig("price", target),
      training_mode: "rolling_window",
      valid_days: currentWindowOptimizationValidDays(target),
      num_boost_round: currentWindowOptimizationNumBoostRound(target),
    },
    interval_model_config: {
      ...collectModelTrainingConfig("interval", target),
      training_mode: "rolling_window",
      valid_days: currentWindowOptimizationValidDays(target),
      num_boost_round: currentWindowOptimizationNumBoostRound(target),
    },
    fine_radius: currentWindowOptimizationFineRadius(target),
    rolling_backtest_horizons: currentWindowOptimizationRollingHorizons(target),
    ...collectTrainingAdvancedConfig(target),
    ...collectSegmentSearchConfig(target),
  };
}

function initializeAdvancedTrainingControls() {
  const preferences = App.config?.training_preferences || {};
  const hasCustomSegments = preferences.segment_mode === "custom" && Array.isArray(preferences.segment_config);
  const segmentConfig = hasCustomSegments ? preferences.segment_config : defaultSegmentRows;
  const normalizedSegmentRows = segmentConfig.map((row) => ({
    name: row.name,
    start_time: row.start_time || "00:00",
    end_time: row.end_time || "24:00",
  }));
  App.segmentRows = cloneSegmentRows(normalizedSegmentRows);
  App.realtimeSegmentRows = cloneSegmentRows(normalizedSegmentRows);
  const modeSelect = $("#segment-mode");
  if (modeSelect) modeSelect.value = hasCustomSegments ? "custom" : "default";
  const realtimeModeSelect = $("#realtime-segment-mode");
  if (realtimeModeSelect) realtimeModeSelect.value = hasCustomSegments ? "custom" : "default";
  const countSelect = $("#segment-count");
  if (countSelect) countSelect.value = String(App.segmentRows.length || defaultSegmentCount);
  const realtimeCountSelect = $("#realtime-segment-count");
  if (realtimeCountSelect) realtimeCountSelect.value = String(App.realtimeSegmentRows.length || defaultSegmentCount);
  saveSegmentDraftForCount(App.segmentRows.length || defaultSegmentCount, App.segmentRows, "dayahead");
  saveSegmentDraftForCount(App.realtimeSegmentRows.length || defaultSegmentCount, App.realtimeSegmentRows, "realtime");
  const highConfig = preferences.high_price_weighting || {};
  if ($("#high-price-weight-enabled")) $("#high-price-weight-enabled").checked = Boolean(highConfig.enabled);
  if ($("#high-price-quantile")) $("#high-price-quantile").value = highConfig.quantile ?? 0.8;
  if ($("#high-price-multiplier")) $("#high-price-multiplier").value = highConfig.multiplier ?? 2;
  if ($("#realtime-high-price-weight-enabled")) $("#realtime-high-price-weight-enabled").checked = Boolean(highConfig.enabled);
  if ($("#realtime-high-price-quantile")) $("#realtime-high-price-quantile").value = highConfig.quantile ?? 0.8;
  if ($("#realtime-high-price-multiplier")) $("#realtime-high-price-multiplier").value = highConfig.multiplier ?? 2;
  App.priceIntervals = normalizePriceIntervalRows(preferences.price_intervals);
  App.realtimePriceIntervals = normalizePriceIntervalRows(preferences.price_intervals);
  renderPriceIntervalTable("dayahead");
  renderPriceIntervalTable("realtime");
  renderSegmentConfigTable("dayahead");
  renderSegmentConfigTable("realtime");
  renderSegmentSearchCounts("dayahead");
  renderSegmentSearchCounts("realtime");
}

function syncTrainingModeControls() {
  ["dayahead", "realtime"].forEach((target) => {
    ["price", "interval"].forEach((prefix) => syncModelTrainingModeControls(prefix, target));
  });
}

function syncModelTrainingModeControls(prefix, target = "dayahead") {
  const fieldPrefix = `${trainingTargetPrefix(target)}${prefix}`;
  const isRolling = currentModelTrainingMode(prefix, target) === "rolling_window";
  const windowInput = $(`#${fieldPrefix}-training-window-days`);
  if (windowInput) windowInput.disabled = !isRolling;
  const enableStart = $(`#${fieldPrefix}-enable-start`);
  const enableEnd = $(`#${fieldPrefix}-enable-end`);
  if (enableStart) enableStart.disabled = isRolling;
  if (enableEnd) enableEnd.disabled = isRolling;
  setDatePickerDisabled(`${fieldPrefix}-train-start-picker`, isRolling || !enableStart?.checked);
  setDatePickerDisabled(`${fieldPrefix}-train-end-picker`, isRolling || !enableEnd?.checked);
}

function formatReferenceStrategyLabel(strategyKey, label, referenceDays = currentReferenceDays()) {
  const baseLabel = label || referenceStrategyLabelMap[strategyKey] || strategyKey || "-";
  return String(baseLabel).replace(/\s*N\s*/g, ` ${referenceDays} `).replace(/\s+/g, " ").trim();
}

function modelSimilarityDiff(row) {
  const value = Number(row?.model_similarity_diff);
  if (Number.isFinite(value)) return value;
  const legacyValue = Number(row?.residual_pred);
  if (Number.isFinite(legacyValue)) return legacyValue;
  const predicted = Number(row?.predicted_price);
  const netLoadOnly = Number(row?.net_load_only_similar_price);
  return Number.isFinite(predicted) && Number.isFinite(netLoadOnly) ? predicted - netLoadOnly : 0;
}

function syncPredictionStrategySelectors(prediction) {
  if (!prediction) return;
}

function renderPredictionBundle(prediction) {
  App.lastPrediction = prediction;
  syncPredictionStrategySelectors(prediction);
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
    "predicted_interval",
    "predicted_interval_probability",
    "high_price_probability",
    "interval_backtest_accuracy",
    "price_interval_consistency",
    "recent_n_days_net_load_only_similar_price",
    "recent_n_days_knn_similar_price",
    "recent_n_days_weighted_knn_regression_price",
    "recent_n_days_predicted_price",
    "recent_n_days_realtime_predicted_price",
    "recent_n_days_scenario_similarity_adjusted_price",
    "recent_n_days_similarity_blend_weight",
    "recent_n_days_similarity_adjustment_reason",
    "recent_same_type_days_net_load_only_similar_price",
    "recent_same_type_days_knn_similar_price",
    "recent_same_type_days_weighted_knn_regression_price",
    "recent_same_type_days_predicted_price",
    "recent_same_type_days_realtime_predicted_price",
    "recent_same_type_days_scenario_similarity_adjusted_price",
    "recent_same_type_days_similarity_blend_weight",
    "recent_same_type_days_similarity_adjustment_reason",
    "prediction_price_diff",
    "net_load",
  ];
  const formatPriceValue = (value) => {
    const numberValue = Number(value);
    return Number.isFinite(numberValue) ? numberValue.toFixed(2) : "";
  };
  const rows = primaryRows.map((row) => {
    const periodKey = String(row.period);
    const recentRow = variantRowMaps.recent_n_days?.get(periodKey);
    const sameTypeRow = variantRowMaps.recent_same_type_days?.get(periodKey);
    const recentPrice = recentRow ? Number(recentRow.predicted_price || 0) : null;
    const sameTypePrice = sameTypeRow ? Number(sameTypeRow.predicted_price || 0) : null;
    return {
      date: row.date,
      period: row.period,
      predicted_interval: row.predicted_interval || "-",
      predicted_interval_probability: formatPercent(row.predicted_interval_probability),
      high_price_probability: formatPercent(row.high_price_probability),
      interval_backtest_accuracy: formatPercent(row.interval_backtest_accuracy),
      price_interval_consistency: row.price_interval_consistency || "-",
      recent_n_days_net_load_only_similar_price: recentRow ? formatPriceValue(recentRow.net_load_only_similar_price) : "",
      recent_n_days_knn_similar_price: recentRow ? formatPriceValue(recentRow.knn_similar_price) : "",
      recent_n_days_weighted_knn_regression_price: recentRow ? formatPriceValue(recentRow.weighted_knn_regression_price) : "",
      recent_n_days_predicted_price: recentPrice === null ? "" : recentPrice.toFixed(2),
      recent_n_days_realtime_predicted_price: recentRow ? formatPriceValue(recentRow.realtime_predicted_price) : "",
      recent_n_days_scenario_similarity_adjusted_price: recentRow ? formatPriceValue(recentRow.scenario_similarity_adjusted_price) : "",
      recent_n_days_similarity_blend_weight: recentRow ? formatPercent(recentRow.similarity_blend_weight) : "",
      recent_n_days_similarity_adjustment_reason: recentRow ? recentRow.similarity_adjustment_reason || "" : "",
      recent_same_type_days_net_load_only_similar_price: sameTypeRow ? formatPriceValue(sameTypeRow.net_load_only_similar_price) : "",
      recent_same_type_days_knn_similar_price: sameTypeRow ? formatPriceValue(sameTypeRow.knn_similar_price) : "",
      recent_same_type_days_weighted_knn_regression_price: sameTypeRow ? formatPriceValue(sameTypeRow.weighted_knn_regression_price) : "",
      recent_same_type_days_predicted_price: sameTypePrice === null ? "" : sameTypePrice.toFixed(2),
      recent_same_type_days_realtime_predicted_price: sameTypeRow ? formatPriceValue(sameTypeRow.realtime_predicted_price) : "",
      recent_same_type_days_scenario_similarity_adjusted_price: sameTypeRow ? formatPriceValue(sameTypeRow.scenario_similarity_adjusted_price) : "",
      recent_same_type_days_similarity_blend_weight: sameTypeRow ? formatPercent(sameTypeRow.similarity_blend_weight) : "",
      recent_same_type_days_similarity_adjustment_reason: sameTypeRow ? sameTypeRow.similarity_adjustment_reason || "" : "",
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
  Object.values(App.multiDayCharts || {}).forEach((chart) => {
    if (chart) chart.resize();
  });
}

function multiDayChartKey(day, index) {
  return `multi-day-${String(day?.forecast_date || index).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

function clearMultiDayCharts() {
  Object.values(App.multiDayCharts || {}).forEach((chart) => {
    try {
      chart?.dispose?.();
    } catch {
      chart?.clear?.();
    }
  });
  App.multiDayCharts = {};
}

function multiDaySeriesValue(row, key) {
  const value = Number(row?.[key]);
  return Number.isFinite(value) ? Number(value.toFixed(4)) : null;
}

function renderMultiDayPrediction(prediction) {
  const target = $("#multi-day-results");
  const meta = $("#multi-day-prediction-meta");
  if (!target) return;
  App.lastMultiDayPrediction = prediction || null;
  const days = prediction?.days || [];
  if (!days.length) {
    clearMultiDayCharts();
    target.innerHTML = `<div class="empty-state">暂无多天预测结果</div>`;
    if (meta) meta.textContent = "尚未执行多天预测";
    App.multiDayPredictionSignature = "";
    return;
  }

  const signature = JSON.stringify(days.map((day) => [day.forecast_date, day.rows || []]));
  if (App.multiDayPredictionSignature !== signature) {
    clearMultiDayCharts();
    target.innerHTML = days
      .map((day, index) => {
        const rows = day.rows || [];
        const maxHigh = rows.reduce((maxValue, row) => Math.max(maxValue, Number(row.high_price_probability || 0)), 0);
        const firstInterval = rows.find((row) => row.predicted_interval)?.predicted_interval || "-";
        const chartKey = multiDayChartKey(day, index);
        return `
          <article class="strategy-chart-panel multi-day-chart-panel">
            <div class="strategy-chart-title multi-day-chart-title">
              <span>${htmlEscape(day.forecast_date || `第${index + 1}天`)}</span>
              <span class="multi-day-chart-badge">高价最高 ${htmlEscape(formatPercent(maxHigh))}</span>
              <span class="multi-day-chart-badge">区间 ${htmlEscape(firstInterval)}</span>
            </div>
            <div id="${htmlEscape(chartKey)}" class="chart-stage strategy-chart-stage multi-day-chart-stage"></div>
          </article>
        `;
      })
      .join("");
    requestAnimationFrame(() => {
      days.forEach((day, index) => renderMultiDayDayChart(day, index));
      resizePredictionCharts();
    });
    App.multiDayPredictionSignature = signature;
  }

  if (meta) {
    const baselineText = prediction.baseline_date ? `基准日：${prediction.baseline_date} | ` : "";
    meta.textContent = `${baselineText}预测 ${days.length} 天 | 最近天数：${currentMultiDayRecentReferenceDays()} 天 | 结果可导出为多 sheet Excel`;
  }
}

function renderMultiDayDayChart(day, index) {
  if (!window.echarts) return;
  const chartKey = multiDayChartKey(day, index);
  const target = $(`#${chartKey}`);
  if (!target) return;
  const chart = App.multiDayCharts[chartKey] || window.echarts.init(target);
  App.multiDayCharts[chartKey] = chart;
  if (!App.chartResizeBound) {
    window.addEventListener("resize", () => resizePredictionCharts());
    App.chartResizeBound = true;
  }
  const rows = day?.rows || [];
  if (!rows.length) {
    chart.clear();
    return;
  }
  const periods = rows.map((row) => row.period);
  const rowByPeriod = new Map(rows.map((row) => [String(row.period), row]));
  const seriesConfig = [
    ["场景修正参考价", "scenario_similarity_adjusted_price", { width: 2, type: "dashed" }],
    ["当前模型预测价格", "predicted_price", { width: 3 }],
    ["净负荷相似法预测价格", "net_load_only_similar_price", { width: 2, type: "dashed" }],
    ["KNN相似法预测价格", "knn_similar_price", { width: 2, type: "dotted" }],
    ["加权KNN回归预测价格", "weighted_knn_regression_price", { width: 2, type: "dashed" }],
  ];
  const highRiskPoints = rows
    .filter((row) => Number(row.high_price_probability || 0) >= 0.5 || Number(row.extreme_price_probability || 0) >= 0.2)
    .map((row) => [row.period, multiDaySeriesValue(row, "predicted_price"), row.predicted_interval || "-", Number(row.high_price_probability || 0)]);
  chart.setOption(
    {
      backgroundColor: "transparent",
      animationDuration: 500,
      color: ["#f97316", "#1677ff", "#16a34a", "#7c3aed", "#0891b2", "#ef4444"],
      legend: {
        top: 6,
        left: 10,
        type: "scroll",
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { color: "#4b5563", fontSize: 12 },
      },
      tooltip: {
        trigger: "axis",
        confine: true,
        backgroundColor: "rgba(17,24,39,0.92)",
        borderWidth: 0,
        textStyle: { color: "#ffffff" },
        formatter(params) {
          const items = Array.isArray(params) ? params : [params];
          const period = items[0]?.axisValueLabel ?? items[0]?.name ?? "";
          const row = rowByPeriod.get(String(period));
          const periodTime = formatPeriodClockTime(period);
          const lines = items
            .filter((item) => item.seriesType !== "scatter")
            .map((item) => `${item.marker}${htmlEscape(item.seriesName)}：${formatPrice(item.value)}`);
          if (row) {
            lines.push(`价格区间：${htmlEscape(row.predicted_interval || "-")}`);
            lines.push(`区间概率：${formatPercent(row.predicted_interval_probability)}`);
            lines.push(`高价概率：${formatPercent(row.high_price_probability)}`);
          }
          return [`${htmlEscape(day.forecast_date || "")} 时段 ${htmlEscape(period)}${periodTime ? `（${htmlEscape(periodTime)}）` : ""}`, ...lines].join("<br/>");
        },
      },
      grid: { left: 54, right: 32, top: 58, bottom: 34 },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: periods,
        axisLabel: { color: "#86909c" },
        axisLine: { lineStyle: { color: "#d9d9d9" } },
      },
      yAxis: {
        type: "value",
        name: "Price",
        min: 0,
        max: 1500,
        axisLabel: { color: "#86909c" },
        splitLine: { lineStyle: { color: "rgba(5,5,5,0.06)" } },
      },
      series: [
        ...seriesConfig.map(([name, key, lineStyle]) => ({
          name,
          type: "line",
          smooth: false,
          symbol: key === "predicted_price" ? "circle" : "none",
          symbolSize: 4,
          lineStyle,
          data: rows.map((row) => multiDaySeriesValue(row, key)),
        })),
        {
          name: "高价概率点",
          type: "scatter",
          symbol: "pin",
          symbolSize: 18,
          z: 6,
          itemStyle: { color: "#ef4444", borderColor: "#fff", borderWidth: 1 },
          data: highRiskPoints,
        },
      ],
    },
    true,
  );
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
  if (target) target.innerHTML = "";
  if (!target || !prediction?.thermal_capacity) return;
  const info = prediction.thermal_capacity;
  const sourceText = info.source === "model" ? "模型预测开机容量" : "手动开机容量";
  target.innerHTML = `
    <div class="chart-stat">
      <span>本次开机容量</span>
      <strong>${sourceText} ${formatNumber(info.value, 0)} MW</strong>
      <small>模型参考 ${formatNumber(info.model_value, 0)} MW / 预测文件 ${formatNumber(info.file_value, 0)} MW</small>
    </div>
  `;
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
  const recentReferenceDays = predictionReferenceDaysForStrategy("recent_n_days", variantMap.recent_n_days);
  const sameTypeReferenceDays = predictionReferenceDaysForStrategy("recent_same_type_days", variantMap.recent_same_type_days);
  const chartSignature = JSON.stringify(variants.map(([key, variant]) => [key, predictionVariantSignature(variant)]));

  if (App.predictionChartSignature !== chartSignature) {
    referenceStrategyOrder.forEach((strategyKey) => {
      renderStrategyChart(strategyKey, variantMap[strategyKey], predictionReferenceDaysForStrategy(strategyKey, variantMap[strategyKey]));
    });
    App.predictionChartSignature = chartSignature;
    requestAnimationFrame(() => resizePredictionCharts());
  }

  $("#prediction-meta").textContent = `预测日期：${forecastDate} | 最近天数：${recentReferenceDays} 天 | 同类型日个数：${sameTypeReferenceDays} 个 | 两个参考口径独立展示`;
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
  const realtimePredicted = rows.map((row) => {
    const value = Number(row.realtime_predicted_price);
    return Number.isFinite(value) ? value : null;
  });
  const hasRealtimePredicted = realtimePredicted.some((value) => value !== null);
  const scenarioSimilarityAdjusted = rows.map((row) => {
    const value = Number(row.scenario_similarity_adjusted_price);
    return Number.isFinite(value) ? value : null;
  });
  const rowByPeriod = new Map(rows.map((row) => [String(row.period), row]));
  const highRiskPoints = rows
    .filter((row) => Number(row.high_price_probability || 0) >= 0.5 || Number(row.extreme_price_probability || 0) >= 0.2)
    .map((row) => [row.period, Number(row.predicted_price || 0), row.predicted_interval || "-", Number(row.high_price_probability || 0)]);
  const netLoadOnlySimilar = rows.map((row) => {
    const value = Number(row.net_load_only_similar_price);
    return Number.isFinite(value) ? value : null;
  });
  const knnSimilar = rows.map((row) => {
    const value = Number(row.knn_similar_price);
    return Number.isFinite(value) ? value : null;
  });
  const weightedKnn = rows.map((row) => {
    const value = Number(row.weighted_knn_regression_price);
    return Number.isFinite(value) ? value : null;
  });
  const showDiff = config.showDiff !== false;
  const diff = showDiff ? rows.map((row) => modelSimilarityDiff(row)) : [];
  const predictedName = formatReferenceStrategyLabel(strategyKey, config.predictedName, referenceDays);
  const realtimePredictedName = formatReferenceStrategyLabel(strategyKey, "实时模型预测价格", referenceDays);
  const scenarioSimilarityName = formatReferenceStrategyLabel(strategyKey, "场景修正参考价", referenceDays);
  const netLoadOnlyName = formatReferenceStrategyLabel(strategyKey, config.netLoadOnlyName, referenceDays);
  const knnName = formatReferenceStrategyLabel(strategyKey, "KNN相似法预测价格", referenceDays);
  const weightedKnnName = formatReferenceStrategyLabel(strategyKey, "加权KNN回归预测价格", referenceDays);
  const diffName = showDiff ? formatReferenceStrategyLabel(strategyKey, config.residualName, referenceDays) : "";
  const legendData = showDiff
    ? [predictedName, scenarioSimilarityName, netLoadOnlyName, knnName, weightedKnnName, diffName]
    : [predictedName, scenarioSimilarityName, netLoadOnlyName, knnName, weightedKnnName];
  if (hasRealtimePredicted) {
    legendData.splice(1, 0, realtimePredictedName);
  }
  const gridConfig = showDiff
    ? [
        { left: 54, right: 38, top: 52, height: 210 },
        { left: 54, right: 38, top: 292, height: 74 },
      ]
    : [{ left: 54, right: 38, top: 52, bottom: 34 }];
  const xAxisConfig = showDiff
    ? [
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
      ]
    : [
        {
          type: "category",
          boundaryGap: false,
          data: periods,
          axisLabel: { color: "#86909c" },
          axisLine: { lineStyle: { color: "#d9d9d9" } },
        },
      ];
  const yAxisConfig = showDiff
    ? [
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
      ]
    : [
        {
          type: "value",
          name: "Price",
          min: 0,
          max: 1500,
          axisLabel: { color: "#86909c" },
          splitLine: { lineStyle: { color: "rgba(5,5,5,0.06)" } },
        },
      ];
  const series = [
    {
      name: predictedName,
      type: "line",
      smooth: false,
      symbol: "circle",
      symbolSize: 5,
      lineStyle: { width: 3 },
      areaStyle: { color: "rgba(22,119,255,0.08)" },
      z: 4,
      data: predicted,
    },
    {
      name: scenarioSimilarityName,
      type: "line",
      smooth: false,
      symbol: "none",
      lineStyle: { width: 2, type: "dashed" },
      data: scenarioSimilarityAdjusted,
    },
    {
      name: "高价概率点",
      type: "scatter",
      symbol: "pin",
      symbolSize: 18,
      z: 6,
      itemStyle: { color: "#ef4444", borderColor: "#fff", borderWidth: 1 },
      data: highRiskPoints,
    },
    {
      name: netLoadOnlyName,
      type: "line",
      smooth: false,
      symbol: "none",
      lineStyle: { width: 2, type: "dashed" },
      data: netLoadOnlySimilar,
    },
    {
      name: knnName,
      type: "line",
      smooth: false,
      symbol: "none",
      lineStyle: { width: 2, type: "dotted" },
      data: knnSimilar,
    },
    {
      name: weightedKnnName,
      type: "line",
      smooth: false,
      symbol: "none",
      lineStyle: { width: 2, type: "dashed" },
      data: weightedKnn,
    },
  ];
  if (hasRealtimePredicted) {
    series.splice(1, 0, {
      name: realtimePredictedName,
      type: "line",
      smooth: false,
      symbol: "circle",
      symbolSize: 4,
      lineStyle: { width: 3, type: "solid" },
      z: 5,
      data: realtimePredicted,
    });
  }
  if (showDiff) {
    series.push({
      name: diffName,
      type: "bar",
      xAxisIndex: 1,
      yAxisIndex: 1,
      barMaxWidth: 10,
      data: diff,
    });
  }

  chart.setOption(
    {
      backgroundColor: "transparent",
      animationDuration: 500,
      color: ["#1677ff", "#dc2626", "#f97316", "#52c41a", "#722ed1", "#13c2c2", "#fa8c16"],
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
          const row = rowByPeriod.get(String(title));
          const periodLabel = row?.period ?? title;
          const periodTime = formatPeriodClockTime(periodLabel);
          const periodTitle = periodTime ? `时段 ${periodLabel}（${periodTime}）` : `时段 ${periodLabel}`;
          const lines = items
            .filter((item) => item?.value !== null && item?.value !== undefined && item?.value !== "")
            .map(
              (item) =>
                `${item.marker || ""}<span style="margin-right:12px;">${item.seriesName}</span><strong>${formatChartTooltipValue(item.value)}</strong>`,
            )
            .join("<br/>");
          const intervalLines = row
            ? `
              <div style="height:1px;background:rgba(255,255,255,0.16);margin:8px 0;"></div>
              <div>最可能区间：<strong>${htmlEscape(row.predicted_interval || "-")}</strong></div>
              <div>价格区间概率：<strong>${formatPercent(row.predicted_interval_probability)}</strong></div>
              <div>高价概率：<strong>${formatPercent(row.high_price_probability)}</strong></div>
              <div>&gt;1000 概率：<strong>${formatPercent(row.extreme_price_probability)}</strong></div>
              <div>历史命中率：<strong>${formatPercent(row.interval_backtest_accuracy)}</strong></div>
              <div>一致性：<strong>${htmlEscape(row.price_interval_consistency || "-")}</strong></div>
            `
            : "";
          return `<div style="font-weight:800;margin-bottom:6px;">${htmlEscape(periodTitle)}</div>${lines}${intervalLines}`;
        },
      },
      legend: {
        top: 8,
        textStyle: { color: "#4e5969" },
        data: legendData,
      },
      grid: gridConfig,
      xAxis: xAxisConfig,
      yAxis: yAxisConfig,
      series,
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
    "realtime-optimize": "等待训练实时价格模型",
    "dual-optimize": "等待一键训练两套模型",
    predict: "\u7b49\u5f85\u6267\u884c\u9884\u6d4b",
    "predict-multi-day": "等待执行多天预测",
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
  const dualJob = App.jobStates["dual-optimize"];
  const dualState = dualJob && !dualJob.running && !dualJob.error && !dualJob.cancelled
    ? ProgressState.deriveDualOptimizationState?.(dualJob.result)
    : null;
  applyProgressCard("dual-optimize", dualState || deriveJobState(dualJob, "dual-optimize"));
  applyProgressCard("optimize", deriveJobState(App.jobStates.optimize, "optimize"));
  applyProgressCard("realtime-optimize", deriveJobState(App.jobStates["realtime-optimize"], "realtime-optimize"));
  applyProgressCard("train", deriveJobState(App.jobStates.train, "train"));
  applyProgressCard("predict", deriveJobState(App.jobStates.predict, "predict"));
  applyProgressCard("predict-multi-day", deriveJobState(App.jobStates["predict-multi-day"], "predict-multi-day"));
  syncStopButtons();
}

function syncStopButtons() {
  const states = {
    "dual-optimize": Boolean(App.activeJobIds["dual-optimize"] && App.jobStates["dual-optimize"]?.running),
    optimize: Boolean(App.activeJobIds.optimize && App.jobStates.optimize?.running),
    "realtime-optimize": Boolean(App.activeJobIds["realtime-optimize"] && App.jobStates["realtime-optimize"]?.running),
    train: Boolean(App.activeJobIds.train && App.jobStates.train?.running),
    predict: Boolean(App.activeJobIds.predict && App.jobStates.predict?.running),
    "predict-multi-day": Boolean(App.activeJobIds["predict-multi-day"] && App.jobStates["predict-multi-day"]?.running),
  };
  $("#stop-dual-optimize-btn")?.classList.toggle("hidden", !states["dual-optimize"]);
  $("#stop-optimize-btn")?.classList.toggle("hidden", !states.optimize);
  $("#stop-realtime-optimize-btn")?.classList.toggle("hidden", !states["realtime-optimize"]);
  $("#stop-train-btn")?.classList.toggle("hidden", !states.train);
  $("#stop-predict-btn")?.classList.toggle("hidden", !states.predict);
  $("#stop-predict-multi-day-btn")?.classList.toggle("hidden", !states["predict-multi-day"]);
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
  const modes = ["train", "predict", "optimize", "realtime-optimize", "dual-optimize", "predict-multi-day"];
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
  App.activeJobIds = { train: null, predict: null, optimize: null, "realtime-optimize": null, "dual-optimize": null, "predict-multi-day": null };
  App.jobStates = { train: null, predict: null, optimize: null, "realtime-optimize": null, "dual-optimize": null, "predict-multi-day": null };
  App.statusFocus = null;
  App.predictSessionStarted = false;
  App.multiDaySessionStarted = false;
  renderProgressSections();
  renderStatusPanel({});
  renderPredictionBundle(null);
  renderMultiDayPrediction(null);
}

async function loadConfig() {
  App.config = await request("/api/config");
  applyModelTrainingDefaults();
  if ($("#window-optimization-max-history-days") && App.config?.default_window_optimization_max_history_days) {
    $("#window-optimization-max-history-days").value = App.config.default_window_optimization_max_history_days;
  }
  if ($("#window-optimization-valid-days") && App.config?.default_window_optimization_valid_days) {
    $("#window-optimization-valid-days").value = App.config.default_window_optimization_valid_days;
  }
  if ($("#window-optimization-rolling-horizons") && App.config?.default_window_optimization_rolling_backtest_horizons) {
    $("#window-optimization-rolling-horizons").value = App.config.default_window_optimization_rolling_backtest_horizons.join(",");
  }
  if ($("#realtime-window-optimization-max-history-days") && App.config?.default_window_optimization_max_history_days) {
    $("#realtime-window-optimization-max-history-days").value = App.config.default_window_optimization_max_history_days;
  }
  if ($("#realtime-window-optimization-valid-days") && App.config?.default_window_optimization_valid_days) {
    $("#realtime-window-optimization-valid-days").value = App.config.default_window_optimization_valid_days;
  }
  if ($("#realtime-window-optimization-rolling-horizons") && App.config?.default_window_optimization_rolling_backtest_horizons) {
    $("#realtime-window-optimization-rolling-horizons").value = App.config.default_window_optimization_rolling_backtest_horizons.join(",");
  }
  const predictionReference = App.config?.prediction_preferences?.prediction_reference || {};
  const knnDefaults = predictionReference.knn_similarity || App.config?.default_knn_similarity || {};
  if ($("#recent-reference-days")) {
    $("#recent-reference-days").value = predictionReference.recent_reference_days || App.config?.default_recent_reference_days || App.config?.default_reference_days || 1;
  }
  if ($("#same-type-reference-days")) {
    $("#same-type-reference-days").value = predictionReference.same_type_reference_days || App.config?.default_same_type_reference_days || App.config?.default_reference_days || 1;
  }
  if ($("#knn-similar-k")) {
    $("#knn-similar-k").value = knnDefaults.knn_k || 5;
  }
  if ($("#knn-similar-max-distance")) {
    $("#knn-similar-max-distance").value = knnDefaults.knn_max_distance || 3.0;
  }
  if ($("#weighted-knn-k")) {
    $("#weighted-knn-k").value = knnDefaults.weighted_knn_k || 5;
  }
  if ($("#weighted-knn-max-distance")) {
    $("#weighted-knn-max-distance").value = knnDefaults.weighted_knn_max_distance || 3.0;
  }
  if ($("#multi-day-recent-reference-days")) {
    $("#multi-day-recent-reference-days").value = predictionReference.recent_reference_days || App.config?.default_recent_reference_days || App.config?.default_reference_days || 1;
  }
  if ($("#multi-day-knn-similar-k")) {
    $("#multi-day-knn-similar-k").value = knnDefaults.knn_k || 5;
  }
  if ($("#multi-day-knn-similar-max-distance")) {
    $("#multi-day-knn-similar-max-distance").value = knnDefaults.knn_max_distance || 3.0;
  }
  if ($("#multi-day-weighted-knn-k")) {
    $("#multi-day-weighted-knn-k").value = knnDefaults.weighted_knn_k || 5;
  }
  if ($("#multi-day-weighted-knn-max-distance")) {
    $("#multi-day-weighted-knn-max-distance").value = knnDefaults.weighted_knn_max_distance || 3.0;
  }
  syncTrainingModeControls();
  renderConfigPaths();
}

function modelRecommendation(prefix) {
  const state = App.config?.window_optimization || {};
  const recommendedKey = prefix === "interval" ? "interval_model_recommended" : "price_model_recommended";
  const configKey = prefix === "interval" ? "interval_model_config" : "price_model_config";
  return state[recommendedKey] || state[configKey] || {};
}

function applyModelTrainingDefaults() {
  ["dayahead", "realtime"].forEach((target) => {
    ["price", "interval"].forEach((prefix) => {
      const recommended = modelRecommendation(prefix);
      const fieldPrefix = `${trainingTargetPrefix(target)}${prefix}`;
      const mode = recommended.training_mode || App.config?.default_training_mode || "rolling_window";
      if ($(`#${fieldPrefix}-training-mode`)) $(`#${fieldPrefix}-training-mode`).value = mode;
      if ($(`#${fieldPrefix}-training-window-days`)) {
        $(`#${fieldPrefix}-training-window-days`).value = recommended.training_window_days || App.config?.default_training_window_days || 60;
      }
      if ($(`#${fieldPrefix}-valid-days`)) $(`#${fieldPrefix}-valid-days`).value = recommended.valid_days || 14;
      if ($(`#${fieldPrefix}-num-boost-round`)) $(`#${fieldPrefix}-num-boost-round`).value = recommended.num_boost_round || 400;
    });
  });
}

async function saveTrainingPreferences(target = "dayahead") {
  const preferences = await request("/api/training/preferences", {
    method: "POST",
    body: JSON.stringify({
      target,
      ...collectTrainingAdvancedConfig(target),
    }),
  });
  App.config = {
    ...App.config,
    training_preferences: preferences.preferences,
    prediction_preferences: preferences.preferences,
  };
  showToast("训练配置已保存，重新训练后生效");
}

async function refreshSummary() {
  const [statusData, currentModel, versionsData, realtimeCurrentModel, realtimeVersionsData] = await Promise.all([
    request("/api/status"),
    request("/api/model/current"),
    request("/api/model/versions"),
    request("/api/model/current?target=realtime"),
    request("/api/model/versions?target=realtime"),
  ]);
  App.currentModelMetadata = currentModel.metadata || {};
  App.modelVersionsByTarget.dayahead = versionsData.versions || [];
  App.modelVersionsByTarget.realtime = realtimeVersionsData.versions || [];
  App.modelMetadataByTarget.dayahead = currentModel.metadata || {};
  App.modelMetadataByTarget.realtime = realtimeCurrentModel.metadata || {};
  await refreshTrackedJobs();
  ProgressState.reconcileJobStatesWithStatus?.(App, statusData);
  renderTopStatus(statusData);
  renderStatusPanel(statusData);
  renderProgressSections();
  renderTargetModelVersions(
    App.versionTarget,
    App.modelVersionsByTarget[App.versionTarget] || [],
    App.modelMetadataByTarget[App.versionTarget] || {},
  );
  renderRealtimePredictionModelSelect(realtimeVersionsData.versions || []);
  renderModelSummary(versionsData.versions || [], currentModel.metadata || {});
  if (App.predictSessionStarted && statusData.last_prediction?.rows?.length) {
    renderPredictionBundle(statusData.last_prediction);
  }
  if ((App.multiDaySessionStarted || statusData.last_multi_day_prediction?.days?.length) && statusData.last_multi_day_prediction?.days?.length) {
    renderMultiDayPrediction(statusData.last_multi_day_prediction);
  }
}

async function refreshRuntimeStatus() {
  const statusData = await request("/api/status");
  await refreshTrackedJobs();
  ProgressState.reconcileJobStatesWithStatus?.(App, statusData);
  renderTopStatus(statusData);
  renderStatusPanel(statusData);
  renderProgressSections();
  if (App.predictSessionStarted && statusData.last_prediction?.rows?.length) {
    renderPredictionBundle(statusData.last_prediction);
  }
  if ((App.multiDaySessionStarted || statusData.last_multi_day_prediction?.days?.length) && statusData.last_multi_day_prediction?.days?.length) {
    renderMultiDayPrediction(statusData.last_multi_day_prediction);
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

function syncThermalCapacityControls() {
  const useModel = Boolean($("#thermal-capacity-use-model")?.checked);
  const input = $("#thermal-capacity-input");
  if (input) input.disabled = useModel;
}

function renderThermalCapacityPreview(preview) {
  App.thermalCapacityPreview = preview || null;
  const label = $("#thermal-capacity-model-value");
  const checkbox = $("#thermal-capacity-use-model");
  const modelValue = Number(preview?.model_value);
  const fileValue = Number(preview?.file_value);
  const available = Boolean(preview?.available) && Number.isFinite(modelValue);
  if (Number.isFinite(fileValue)) {
    const input = $("#thermal-capacity-input");
    if (input && !input.dataset.userEdited) input.value = fileValue;
    const hint = $("#thermal-capacity-file-hint");
    if (hint) hint.textContent = `预测文件值：${formatNumber(fileValue, 0)} MW`;
  }
  if (label) {
    label.textContent = available
      ? `模型预测值：${formatNumber(modelValue, 0)} MW`
      : `模型预测值：${preview?.error ? `暂无（${preview.error}）` : "暂无"}`;
  }
  if (checkbox) {
    checkbox.disabled = !available;
    if (!available) checkbox.checked = false;
  }
  syncThermalCapacityControls();
}

async function loadThermalCapacityPreview() {
  try {
    const data = await request("/api/forecast/thermal-capacity-preview");
    renderThermalCapacityPreview(data);
  } catch (error) {
    renderThermalCapacityPreview({ available: false, error: error.message });
  }
}

function currentThermalCapacityPayload() {
  const manualValue = Number($("#thermal-capacity-input")?.value);
  return {
    mode: $("#thermal-capacity-use-model")?.checked ? "model" : "manual",
    manual_value: Number.isFinite(manualValue) ? manualValue : null,
  };
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

async function saveTemplate() {
  await request("/api/forecast/template/save", {
    method: "POST",
    body: JSON.stringify({ rows: collectTemplateRows() }),
  });
  showToast("预测文件已保存");
}

async function startTrain(target = "dayahead") {
  const normalizedTarget = target === "realtime" ? "realtime" : "dayahead";
  const btn = normalizedTarget === "realtime" ? $("#train-realtime-btn") : $("#train-btn");
  const targetLabel = normalizedTarget === "realtime" ? "实时模型" : "日前模型";
  const originalText = btn?.textContent || "手动重训模型";
  try {
    setButtonLoading(btn, true, originalText);
    setPendingState("train", "正在提交训练任务...");
    const data = await request("/api/train", {
      method: "POST",
      body: JSON.stringify({
        target: target === "realtime" ? "realtime" : "dayahead",
        price_model_config: collectModelTrainingConfig("price", normalizedTarget),
        interval_model_config: collectModelTrainingConfig("interval", normalizedTarget),
        ...collectTrainingAdvancedConfig(normalizedTarget),
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
    const el = normalizedTarget === "realtime" ? $("#train-realtime-btn") : $("#train-btn");
    if (el) setButtonLoading(el, false, originalText);
    syncStopButtons();
  }
}

async function startDualWindowOptimization() {
  const btn = $("#dual-optimize-window-btn");
  const originalText = btn?.textContent || "一键训练两套价格模型";
  try {
    setButtonLoading(btn, true, originalText);
    App.statusFocus = "dual-optimize";
    App.pendingStatus = {
      job_type: "dual_optimize",
      progress: 3,
      status: "正在提交两套价格模型总控任务...",
      logs: ["[本地] 正在提交两套价格模型总控任务..."],
      running: true,
    };
    applyProgressCard("dual-optimize", { progress: 3, label: "提交中", status: "正在提交两套价格模型总控任务...", type: "running" });
    renderStatusPanel({ current_job: App.pendingStatus, recent_jobs: [] });
    const data = await request("/api/dual-window-optimization/run", {
      method: "POST",
      body: JSON.stringify({
        force: true,
        dayahead_payload: collectWindowOptimizationPayload("dayahead"),
        realtime_payload: collectWindowOptimizationPayload("realtime"),
      }),
    });
    App.activeJobIds["dual-optimize"] = data.job_id;
    App.jobStates["dual-optimize"] = {
      job_id: data.job_id,
      job_type: "dual_optimize",
      progress: 5,
      status: `两套价格模型总控任务已启动：${data.job_id}`,
      logs: [`[本地] 两套价格模型总控任务已启动：${data.job_id}`],
      running: true,
    };
    App.pendingStatus = null;
    syncStopButtons();
    applyProgressCard("dual-optimize", { progress: 5, label: "训练中", status: `两套价格模型总控任务已启动：${data.job_id}`, type: "running" });
    showToast("两套价格模型总控任务已启动");
    await refreshSummary();
  } catch (error) {
    App.pendingStatus = null;
    applyProgressCard("dual-optimize", { progress: 0, label: "错误", status: error.message, type: "error" });
    showToast(error.message, "error");
  } finally {
    setButtonLoading(btn, false, originalText);
    syncStopButtons();
  }
}

async function startWindowOptimization() {
  const btn = $("#optimize-window-btn");
  const originalText = btn?.textContent || "自动寻优并训练最优模型";
  try {
    setButtonLoading(btn, true, originalText);
    App.statusFocus = "optimize";
    App.pendingStatus = {
      job_type: "optimize",
      progress: 3,
      status: "正在提交自动寻优任务...",
      logs: ["[本地] 正在提交自动寻优任务..."],
      running: true,
    };
    applyProgressCard("optimize", { progress: 3, label: "\u63d0\u4ea4\u4e2d", status: "正在提交自动寻优任务...", type: "running" });
    renderStatusPanel({ current_job: App.pendingStatus, recent_jobs: [] });
    const data = await request("/api/window-optimization/run", {
      method: "POST",
      body: JSON.stringify(collectWindowOptimizationPayload("dayahead")),
    });
    if (data.started && data.job?.job_id) {
      App.activeJobIds.optimize = data.job.job_id;
      App.jobStates.optimize = {
        job_id: data.job.job_id,
        job_type: "optimize",
        progress: 5,
        status: `自动寻优已启动：${data.job.job_id}`,
        logs: [`[本地] 自动寻优已启动：${data.job.job_id}`],
        running: true,
      };
      App.pendingStatus = null;
      syncStopButtons();
      applyProgressCard("optimize", { progress: 5, label: "\u5bfb\u4f18\u4e2d", status: `自动寻优已启动：${data.job.job_id}`, type: "running" });
      showToast("自动寻优已启动");
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

async function startRealtimeWindowOptimization() {
  const btn = $("#realtime-optimize-window-btn");
  const originalText = btn?.textContent || "训练实时价格模型";
  try {
    setButtonLoading(btn, true, originalText);
    App.statusFocus = "realtime-optimize";
    App.pendingStatus = {
      job_type: "realtime_optimize",
      progress: 3,
      status: "正在提交实时价格模型寻优任务...",
      logs: ["[本地] 正在提交实时价格模型寻优任务..."],
      running: true,
    };
    applyProgressCard("realtime-optimize", { progress: 3, label: "提交中", status: "正在提交实时价格模型寻优任务...", type: "running" });
    renderStatusPanel({ current_job: App.pendingStatus, recent_jobs: [] });
    const data = await request("/api/realtime-window-optimization/run", {
      method: "POST",
      body: JSON.stringify(collectWindowOptimizationPayload("realtime")),
    });
    if (data.started && data.job?.job_id) {
      App.activeJobIds["realtime-optimize"] = data.job.job_id;
      App.jobStates["realtime-optimize"] = {
        job_id: data.job.job_id,
        job_type: "realtime_optimize",
        progress: 5,
        status: `实时价格模型寻优已启动：${data.job.job_id}`,
        logs: [`[本地] 实时价格模型寻优已启动：${data.job.job_id}`],
        running: true,
      };
      App.pendingStatus = null;
      syncStopButtons();
      applyProgressCard("realtime-optimize", { progress: 5, label: "寻优中", status: `实时价格模型寻优已启动：${data.job.job_id}`, type: "running" });
      showToast("实时价格模型寻优已启动");
    } else {
      App.pendingStatus = null;
      applyProgressCard("realtime-optimize", deriveJobState(App.jobStates["realtime-optimize"], "realtime-optimize"));
      showToast(data.reason === "job_running" ? "当前已有任务运行，稍后再试" : "实时价格模型无需重新寻优");
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
    const data = await request("/api/predict", {
      method: "POST",
      body: JSON.stringify({
        reference_days: currentReferenceDays(),
        recent_reference_days: currentRecentReferenceDays(),
        same_type_reference_days: currentSameTypeReferenceDays(),
        knn_similarity: currentKnnSimilarityConfig(),
        model_version_key: $("#predict-model-version")?.value || "",
        realtime_model_version_key: $("#predict-realtime-model-version")?.value || "",
        thermal_capacity: currentThermalCapacityPayload(),
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
    if (App.lastPrediction?.forecast_date) {
      await loadPredictionArchiveRecords(App.lastPrediction.forecast_date);
    }
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

async function startMultiDayPredict() {
  const btn = $("#predict-multi-day-btn");
  const originalText = btn?.textContent || "执行多天预测";
  try {
    setButtonLoading(btn, true, originalText);
    App.multiDaySessionStarted = true;
    setPendingState("predict-multi-day", "正在保存并提交多天预测任务...");
    await saveMultiDayTemplate();
    const data = await request("/api/predict-multi-day", {
      method: "POST",
      body: JSON.stringify({
        reference_days: currentMultiDayRecentReferenceDays(),
        recent_reference_days: currentMultiDayRecentReferenceDays(),
        knn_similarity: currentMultiDayKnnSimilarityConfig(),
        model_version_key: $("#multi-day-model-version")?.value || "",
      }),
    });
    App.activeJobIds["predict-multi-day"] = data.job_id;
    App.jobStates["predict-multi-day"] = {
      job_id: data.job_id,
      job_type: "predict_multi_day",
      progress: 5,
      status: `多天预测任务已启动：${data.job_id}`,
      logs: [`[本地] 多天预测任务已启动：${data.job_id}`],
      running: true,
    };
    syncStopButtons();
    applyProgressCard("predict-multi-day", { progress: 5, label: "预测中", status: `多天预测任务已启动：${data.job_id}`, type: "running" });
    showToast(`已启动多天预测任务：${data.job_id}，等待完成...`);
    const job = await pollJobUntilDone(data.job_id);
    if (!job) {
      App.activeJobIds["predict-multi-day"] = null;
      syncStopButtons();
      applyProgressCard("predict-multi-day", { progress: 0, label: "超时", status: "多天预测超时，请检查服务器状态", type: "error" });
      showToast("多天预测超时，请检查服务器状态", "error");
      return;
    }
    App.jobStates["predict-multi-day"] = job;
    App.activeJobIds["predict-multi-day"] = null;
    syncStopButtons();
    if (job.error) {
      applyProgressCard("predict-multi-day", { progress: job.progress || 0, label: "失败", status: job.error, type: "error" });
      showToast(`多天预测失败：${job.error.split("\n")[0]}`, "error");
    } else if (job.cancelled) {
      applyProgressCard("predict-multi-day", { progress: job.progress || 0, label: "已停止", status: "多天预测已停止", type: "error" });
      showToast("多天预测已停止");
    } else {
      const prediction = job.result?.multi_day_prediction || job.result?.result?.multi_day_prediction;
      if (prediction?.days?.length) {
        renderMultiDayPrediction(prediction);
      }
      applyProgressCard("predict-multi-day", { progress: 100, label: "已完成", status: "多天预测完成", type: "success" });
      showToast("多天预测已完成");
    }
    await refreshSummary();
    await loadDataQuality();
  } catch (error) {
    showToast(error.message, "error");
    applyProgressCard("predict-multi-day", { progress: 0, label: "错误", status: error.message, type: "error" });
  } finally {
    const el = $("#predict-multi-day-btn");
    if (el) setButtonLoading(el, false, originalText);
    syncStopButtons();
  }
}

function exportMultiDayPrediction() {
  window.open("/api/predict-multi-day/export", "_blank", "noopener");
}

async function activateVersion() {
  const versionKey = $("#version-select").value;
  if (!versionKey) {
    showToast("请先选择历史模型版本", "error");
    return;
  }
  const data = await request("/api/model/activate", {
    method: "POST",
    body: JSON.stringify({ target: App.versionTarget, version_key: versionKey }),
  });
  showToast(data.message || "已切换默认模型版本");
  await refreshSummary();
}

async function rollbackVersion() {
  const data = await request("/api/model/rollback", {
    method: "POST",
    body: JSON.stringify({ target: App.versionTarget }),
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
    body: JSON.stringify({ target: App.versionTarget, version_keys: versionKeys }),
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
    const skippedText = data.skipped_count ? `，${data.skipped_count} 项因权限或占用未删除` : "";
    const summary = `已清理 ${formatBytes(data.total_bytes)} / ${data.total_files || 0} 个文件${skippedText}，保留最新预测结果、模型和最新异常报告。`;
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
    "dual-optimize": $("#stop-dual-optimize-btn"),
    optimize: $("#stop-optimize-btn"),
    "realtime-optimize": $("#stop-realtime-optimize-btn"),
    train: $("#stop-train-btn"),
    predict: $("#stop-predict-btn"),
    "predict-multi-day": $("#stop-predict-multi-day-btn"),
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
  $("#train-btn").addEventListener("click", () => startTrain("dayahead").catch((error) => showToast(error.message, "error")));
  $("#train-realtime-btn")?.addEventListener("click", () => startTrain("realtime").catch((error) => showToast(error.message, "error")));
  $("#dual-optimize-window-btn")?.addEventListener("click", () => startDualWindowOptimization().catch((error) => showToast(error.message, "error")));
  $("#optimize-window-btn")?.addEventListener("click", () => startWindowOptimization().catch((error) => showToast(error.message, "error")));
  $("#realtime-optimize-window-btn")?.addEventListener("click", () => startRealtimeWindowOptimization().catch((error) => showToast(error.message, "error")));
  $("#stop-optimize-btn")?.addEventListener("click", () => cancelJob("optimize"));
  $("#stop-dual-optimize-btn")?.addEventListener("click", () => cancelJob("dual-optimize"));
  $("#stop-realtime-optimize-btn")?.addEventListener("click", () => cancelJob("realtime-optimize"));
  $("#stop-train-btn").addEventListener("click", () => cancelJob("train"));
  $("#refresh-train-metrics-btn").addEventListener("click", () => refreshSummary().then(() => showToast("当前指标已刷新")).catch((error) => showToast(error.message, "error")));
  $("#reload-template-btn").addEventListener("click", () => loadTemplate().then(() => showToast("预测文件已重新加载")).catch((error) => showToast(error.message, "error")));
  $("#save-template-btn").addEventListener("click", () => saveTemplate().catch((error) => showToast(error.message, "error")));
  $("#predict-btn").addEventListener("click", () => startPredict().catch((error) => showToast(error.message, "error")));
  $("#stop-predict-btn").addEventListener("click", () => cancelJob("predict"));
  $("#thermal-capacity-use-model")?.addEventListener("change", syncThermalCapacityControls);
  $("#thermal-capacity-input")?.addEventListener("input", (event) => {
    event.currentTarget.dataset.userEdited = "1";
  });
  $("#reload-multi-day-template-btn")?.addEventListener("click", () => loadMultiDayTemplate().then(() => showToast("预测文件-N天已重新加载")).catch((error) => showToast(error.message, "error")));
  $("#save-multi-day-template-btn")?.addEventListener("click", () => saveMultiDayTemplate().catch((error) => showToast(error.message, "error")));
  $("#predict-multi-day-btn")?.addEventListener("click", () => startMultiDayPredict().catch((error) => showToast(error.message, "error")));
  $("#stop-predict-multi-day-btn")?.addEventListener("click", () => cancelJob("predict-multi-day"));
  $("#export-multi-day-btn")?.addEventListener("click", exportMultiDayPrediction);
  $("#refresh-model-rank-btn")?.addEventListener("click", () => loadModelCandidateRankings().then(() => showToast("模型排序已刷新")).catch((error) => showToast(error.message, "error")));
  $("#save-segment-models-btn")?.addEventListener("click", () => saveSegmentModelSelection().catch((error) => showToast(error.message, "error")));
  $("#model-rank-metric")?.addEventListener("change", () => loadModelCandidateRankings().catch((error) => showToast(error.message, "error")));
  ["#model-rank-price-min", "#model-rank-price-max"].forEach((selector) => {
    $(selector)?.addEventListener("change", () => {
      if ($("#model-rank-metric")?.value === "mae_range") {
        loadModelCandidateRankings().catch((error) => showToast(error.message, "error"));
      }
    });
  });
  $("#model-rank-table")?.addEventListener("change", (event) => {
    const select = event.target.closest("[data-segment-model-select]");
    if (!select) return;
    App.selectedSegmentPriceModels[select.dataset.segmentModelSelect] = select.value;
    renderModelCandidateRankings();
  });
  $("#archive-review-refresh-btn")?.addEventListener("click", () => loadPredictionArchiveRecords().catch((error) => showToast(error.message, "error")));
  $("#archive-review-date")?.addEventListener("change", () => loadPredictionArchiveRecords().catch((error) => showToast(error.message, "error")));
  $("#archive-review-select")?.addEventListener("change", (event) => {
    loadPredictionArchiveDetail(event.target.value).catch((error) => showToast(error.message, "error"));
  });
  $("#refresh-quality-btn")?.addEventListener("click", () => loadDataQuality().then(() => showToast("数据异常报告已刷新")).catch((error) => showToast(error.message, "error")));
  $$("#prediction-chart-layout-control [data-chart-layout]").forEach((button) => {
    button.addEventListener("click", () => setPredictionChartLayout(button.dataset.chartLayout));
  });
  $("#activate-version-btn").addEventListener("click", () => activateVersion().catch((error) => showToast(error.message, "error")));
  $("#rollback-btn").addEventListener("click", () => rollbackVersion().catch((error) => showToast(error.message, "error")));
  $("#delete-versions-btn").addEventListener("click", () => deleteSelectedVersions().catch((error) => showToast(error.message, "error")));
  $$("#model-version-target [data-target]").forEach((button) => {
    button.addEventListener("click", () => loadModelVersionsForTarget(button.dataset.target).catch((error) => showToast(error.message, "error")));
  });
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
  $("#versions-table").addEventListener("toggle", (event) => {
    const detail = event.target.closest?.(".version-detail-toggle");
    if (detail) rememberVersionDetailState(detail.dataset.versionKey, detail.open);
  }, true);
  ["dayahead", "realtime"].forEach((target) => {
    ["price", "interval"].forEach((prefix) => {
      const fieldPrefix = `${trainingTargetPrefix(target)}${prefix}`;
      $(`#${fieldPrefix}-training-mode`)?.addEventListener("change", () => syncModelTrainingModeControls(prefix, target));
      $(`#${fieldPrefix}-enable-start`)?.addEventListener("change", (event) => {
        if (currentModelTrainingMode(prefix, target) === "rolling_window") {
          syncModelTrainingModeControls(prefix, target);
          return;
        }
        setDatePickerDisabled(`${fieldPrefix}-train-start-picker`, !event.target.checked);
      });
      $(`#${fieldPrefix}-enable-end`)?.addEventListener("change", (event) => {
        if (currentModelTrainingMode(prefix, target) === "rolling_window") {
          syncModelTrainingModeControls(prefix, target);
          return;
        }
        setDatePickerDisabled(`${fieldPrefix}-train-end-picker`, !event.target.checked);
      });
    });
  });
  $("#segment-mode")?.addEventListener("change", () => {
    renderSegmentConfigTable();
    renderSegmentSearchCounts();
  });
  $("#segment-count")?.addEventListener("change", (event) => {
    saveSegmentDraftForCount(App.segmentRows.length, App.segmentRows);
    const selectedCount = Number(event.target.value || defaultSegmentCount);
    App.segmentRows = segmentRowsForCount(selectedCount);
    saveSegmentDraftForCount(selectedCount, App.segmentRows, "dayahead");
    saveSegmentSearchCounts([selectedCount], "dayahead");
    const modeSelect = $("#segment-mode");
    if (modeSelect) modeSelect.value = "custom";
    renderSegmentConfigTable();
    renderSegmentSearchCounts();
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
    renderSegmentSearchCounts();
  });
  $("#realtime-segment-mode")?.addEventListener("change", () => {
    renderSegmentConfigTable("realtime");
    renderSegmentSearchCounts("realtime");
  });
  $("#realtime-segment-count")?.addEventListener("change", (event) => {
    saveSegmentDraftForCount(App.realtimeSegmentRows.length, App.realtimeSegmentRows, "realtime");
    const selectedCount = Number(event.target.value || defaultSegmentCount);
    App.realtimeSegmentRows = segmentRowsForCount(selectedCount, "realtime");
    saveSegmentDraftForCount(selectedCount, App.realtimeSegmentRows, "realtime");
    saveSegmentSearchCounts([selectedCount], "realtime");
    const modeSelect = $("#realtime-segment-mode");
    if (modeSelect) modeSelect.value = "custom";
    renderSegmentConfigTable("realtime");
    renderSegmentSearchCounts("realtime");
  });
  $("#realtime-segment-config-table")?.addEventListener("change", (event) => {
    const index = Number(event.target.dataset.index);
    if (!Number.isInteger(index) || !App.realtimeSegmentRows[index]) return;
    if (event.target.matches(".segment-name-input")) {
      App.realtimeSegmentRows[index].name = event.target.value.trim();
    }
    if (event.target.matches(".segment-end-input")) {
      App.realtimeSegmentRows[index].end_time = normalizeTimeText(event.target.value);
      if (App.realtimeSegmentRows[index + 1]) {
        App.realtimeSegmentRows[index + 1].start_time = App.realtimeSegmentRows[index].end_time;
      }
    }
    saveSegmentDraftForCount(App.realtimeSegmentRows.length, App.realtimeSegmentRows, "realtime");
    renderSegmentConfigTable("realtime");
    renderSegmentSearchCounts("realtime");
  });
  $("#price-interval-table")?.addEventListener("change", () => {
    try {
      collectPriceIntervals("dayahead");
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  $("#price-interval-table")?.addEventListener("click", (event) => {
    const button = event.target.closest(".interval-delete-btn");
    if (!button) return;
    deletePriceIntervalRow(Number(button.dataset.index), "dayahead");
  });
  $("#add-price-interval-btn")?.addEventListener("click", () => {
    try {
      addPriceIntervalRow("dayahead");
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  $("#reset-price-intervals-btn")?.addEventListener("click", () => {
    setTrainingPriceIntervals("dayahead", normalizePriceIntervalRows(defaultPriceIntervals));
    renderPriceIntervalTable("dayahead");
    showToast("已恢复默认价格区间，保存并重训后生效");
  });
  $("#save-price-intervals-btn")?.addEventListener("click", () => saveTrainingPreferences("dayahead").catch((error) => showToast(error.message, "error")));
  $("#realtime-price-interval-table")?.addEventListener("change", () => {
    try {
      collectPriceIntervals("realtime");
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  $("#realtime-price-interval-table")?.addEventListener("click", (event) => {
    const button = event.target.closest(".interval-delete-btn");
    if (!button) return;
    deletePriceIntervalRow(Number(button.dataset.index), "realtime");
  });
  $("#realtime-add-price-interval-btn")?.addEventListener("click", () => {
    try {
      addPriceIntervalRow("realtime");
    } catch (error) {
      showToast(error.message, "error");
    }
  });
  $("#realtime-reset-price-intervals-btn")?.addEventListener("click", () => {
    setTrainingPriceIntervals("realtime", normalizePriceIntervalRows(defaultPriceIntervals));
    renderPriceIntervalTable("realtime");
    showToast("已恢复实时模型默认价格区间，保存并重训后生效");
  });
  $("#realtime-save-price-intervals-btn")?.addEventListener("click", () => saveTrainingPreferences("realtime").catch((error) => showToast(error.message, "error")));
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
  initDatePicker("price-train-start-picker", "price-train-start-date", "2025-01-01");
  initDatePicker("price-train-end-picker", "price-train-end-date", "2026-03-31");
  initDatePicker("interval-train-start-picker", "interval-train-start-date", "2025-01-01");
  initDatePicker("interval-train-end-picker", "interval-train-end-date", "2026-03-31");
  initDatePicker("realtime-price-train-start-picker", "realtime-price-train-start-date", "2025-01-01");
  initDatePicker("realtime-price-train-end-picker", "realtime-price-train-end-date", "2026-03-31");
  initDatePicker("realtime-interval-train-start-picker", "realtime-interval-train-start-date", "2025-01-01");
  initDatePicker("realtime-interval-train-end-picker", "realtime-interval-train-end-date", "2026-03-31");
  await loadConfig();
  initializeAdvancedTrainingControls();
  renderConfigPaths();
  setArchiveReviewDate(new Date().toISOString().slice(0, 10));
  const initResults = await Promise.allSettled([refreshSummary(), loadLogs(), loadTemplate(), loadThermalCapacityPreview(), loadMultiDayTemplate(), loadModelCandidateRankings(), loadPredictionArchiveRecords()]);
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
    Promise.allSettled([refreshRuntimeStatus(), loadLogs()]).then((results) => {
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
