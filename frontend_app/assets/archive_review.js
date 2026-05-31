(function (root, factory) {
  const helpers = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = helpers;
  }
  if (root) {
    root.archiveReviewHelpers = helpers;
  }
})(typeof window !== "undefined" ? window : globalThis, function () {
  const intervalKeys = [
    "predicted_interval",
    "predicted_interval_probability",
    "high_price_probability",
    "extreme_price_probability",
    "interval_backtest_accuracy",
    "price_interval_consistency",
  ];
  const defaultLabels = {
    predicted_interval: "Most likely interval",
    predicted_interval_probability: "Interval probability",
    high_price_probability: "High-price probability",
    extreme_price_probability: "Extreme-price probability",
    interval_backtest_accuracy: "Historical hit rate",
    price_interval_consistency: "Consistency",
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatPercent(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(1)}%` : "-";
  }

  function intervalValue(row, key) {
    if (!row || row[key] === null || row[key] === undefined || row[key] === "") {
      return "-";
    }
    if (
      key === "predicted_interval_probability"
      || key === "high_price_probability"
      || key === "extreme_price_probability"
      || key === "interval_backtest_accuracy"
    ) {
      return formatPercent(row[key]);
    }
    return String(row[key]);
  }

  function rowHasIntervalInfo(row) {
    return intervalKeys.some((key) => row?.[key] !== null && row?.[key] !== undefined && row?.[key] !== "");
  }

  function renderArchiveIntervalTooltipBlock(row, labels = defaultLabels) {
    return `
      <div style="height:1px;background:rgba(255,255,255,0.16);margin:8px 0;"></div>
      <div>${escapeHtml(labels.predicted_interval || defaultLabels.predicted_interval)}: <strong>${escapeHtml(intervalValue(row, "predicted_interval"))}</strong></div>
      <div>${escapeHtml(labels.predicted_interval_probability || defaultLabels.predicted_interval_probability)}: <strong>${escapeHtml(intervalValue(row, "predicted_interval_probability"))}</strong></div>
      <div>${escapeHtml(labels.high_price_probability || defaultLabels.high_price_probability)}: <strong>${escapeHtml(intervalValue(row, "high_price_probability"))}</strong></div>
      <div>${escapeHtml(labels.extreme_price_probability || defaultLabels.extreme_price_probability)}: <strong>${escapeHtml(intervalValue(row, "extreme_price_probability"))}</strong></div>
      <div>${escapeHtml(labels.interval_backtest_accuracy || defaultLabels.interval_backtest_accuracy)}: <strong>${escapeHtml(intervalValue(row, "interval_backtest_accuracy"))}</strong></div>
      <div>${escapeHtml(labels.price_interval_consistency || defaultLabels.price_interval_consistency)}: <strong>${escapeHtml(intervalValue(row, "price_interval_consistency"))}</strong></div>
    `;
  }

  function archiveIntervalSummary(rows) {
    const list = Array.isArray(rows) ? rows : [];
    const savedCount = list.filter(rowHasIntervalInfo).length;
    if (!savedCount) return "No price interval info saved";
    return `Price interval info saved for ${savedCount}/${list.length} periods`;
  }

  return {
    archiveIntervalSummary,
    renderArchiveIntervalTooltipBlock,
    rowHasIntervalInfo,
  };
});
