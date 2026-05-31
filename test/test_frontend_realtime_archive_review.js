const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const appJs = fs.readFileSync(path.join(__dirname, "../frontend_app/assets/app.js"), "utf8");
const archiveFunction = appJs.slice(
  appJs.indexOf("function renderArchiveMetrics"),
  appJs.indexOf("function renderRollingBacktest"),
);

assert.match(archiveFunction, /realtime_predicted_price/);
assert.match(archiveFunction, /realtime_actual_price/);
assert.match(archiveFunction, /实时模型MAE/);
assert.match(archiveFunction, /实时模型RMSE/);
assert.match(archiveFunction, /实时方向准确率/);
assert.match(archiveFunction, /实时模型预测价格/);
assert.match(archiveFunction, /实际实时价格/);

console.log("frontend realtime archive review checks passed");
