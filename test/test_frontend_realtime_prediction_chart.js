const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const appJs = fs.readFileSync(path.join(__dirname, "../frontend_app/assets/app.js"), "utf8");
const chartFunction = appJs.slice(
  appJs.indexOf("function renderPredictionChart"),
  appJs.indexOf("function applyProgressCard"),
);

assert.match(chartFunction, /realtimePredicted/);
assert.match(chartFunction, /realtime_predicted_price/);
assert.match(chartFunction, /实时模型预测价格/);

console.log("frontend realtime prediction chart checks passed");
