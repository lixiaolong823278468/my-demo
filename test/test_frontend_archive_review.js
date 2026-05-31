const assert = require("node:assert/strict");

const {
  archiveIntervalSummary,
  renderArchiveIntervalTooltipBlock,
} = require("../frontend_app/assets/archive_review.js");

const richRow = {
  predicted_interval: "600-1000",
  predicted_interval_probability: 0.8123,
  high_price_probability: 0.414,
  extreme_price_probability: 0.08,
  interval_backtest_accuracy: 0.733,
  price_interval_consistency: "consistent",
};

const block = renderArchiveIntervalTooltipBlock(richRow);
assert.match(block, /Most likely interval/);
assert.match(block, /600-1000/);
assert.match(block, /Interval probability/);
assert.match(block, /81\.2%/);
assert.match(block, /High-price probability/);
assert.match(block, /41\.4%/);
assert.match(block, /Extreme-price probability/);
assert.match(block, /8\.0%/);
assert.match(block, /Historical hit rate/);
assert.match(block, /73\.3%/);
assert.match(block, /consistent/);

const missingBlock = renderArchiveIntervalTooltipBlock({});
assert.match(missingBlock, /Most likely interval/);
assert.match(missingBlock, /Historical hit rate/);
assert.match(missingBlock, />-</);

assert.equal(
  archiveIntervalSummary([richRow, { predicted_price: 300 }, { predicted_interval: "250-300" }]),
  "Price interval info saved for 2/3 periods",
);
assert.equal(archiveIntervalSummary([{ predicted_price: 300 }]), "No price interval info saved");

console.log("frontend archive review helpers passed");
