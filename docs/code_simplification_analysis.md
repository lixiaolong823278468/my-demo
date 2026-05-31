# 代码简化分析报告（深入版）

## 一、重复函数（跨文件、同一文件内）

### 1.1 `normalize_text` — 两个文件各写一份
- `dayahead_core.py` L316
- `data_quality.py` L60

完全一样的 `re.sub(r"\s+", "", str(text)).strip().lower()`，查了所有调用点，`data_quality` 只在自身内部用，`dayahead_core` 广泛使用。直接让 `data_quality` import `dayahead_core` 的版本即可。

### 1.2 `minutes_to_time_text` — 两个文件各写一份，且逻辑不一致
- `dayahead_core.py` L216：不处理 >= 1440 边界，传入即报错。
- `api_server.py` L101：`>= 1440` 返回 `"24:00"`。

调用场景完全重叠（时段名→时间字符串），应该合并到一个公共位置，统一边界行为。

### 1.3 `extract_month_day` — 两个版本，正则有细微差异
- `dayahead_core.py` L683：用了 `(?<!\d)` 和 `(?!\d)` 零宽断言防止误匹配。
- `data_quality.py` L64：没有零宽断言，`"15月120日"` 这类输入会匹配到 `5月12`。

应统一为 `dayahead_core` 的更严谨版本。

### 1.4 `convert_capacity_to_mw` — 两个版本，单位覆盖有差异
- `dayahead_core.py` L690：处理 GW、kW/千瓦、万千瓦。
- `data_quality.py` L121：额外处理了 KW 的大写形式。

应该合并并补全所有已知单位变体。

### 1.5 `extract_thermal_on_capacity` ≈ `extract_running_unit_capacity`
- `dayahead_core.py` L701
- `data_quality.py` L132

两个函数用完全一样的正则模式从文本中提取火电开机容量，只是函数名不同。合并为一个。

### 1.6 `resolve_column` — 签名不同，逻辑相同
- `dayahead_core.py` L643：`resolve_column(columns, candidates, required: bool)` — required=True 时抛 KeyError。
- `data_quality.py` L75：`resolve_column(columns, candidates)` — 找不到返回 None。

核心匹配逻辑完全一致。统一为 `data_quality` 的 API（返回 Optional），调用方自行判断。

### 1.7 `resolve_forecast_template_column` — 两个版本
- `dayahead_core.py` L2283：有 `required` 参数，月日 token 用 `.` 和 `月…日` 两种格式。
- `data_quality.py` L89：无 required 参数，月日 token 多了 `/` 和 `-` 格式。

合并时取所有 token 的并集，参数用 Optional 返回。

### 1.8 `model_file_name` / `interval_model_file_name` — 完全相同
- `dayahead_core.py` L1113
- `price_interval.py` L221

都根据 backend 返回不同扩展名。合并。

### 1.9 `split_train_valid` / `split_train_valid_by_date` — 本质相同
- `dayahead_core.py` L875：用 `pd.Timestamp` 比较。
- `price_interval.py` L194：用字符串比较。

合并为用 `pd.Timestamp` 的版本。

### 1.10 `safe_value` / `sanitize_scalar` / `json_safe` — 都是"转为可序列化值"
- `data_quality.py` L147：`safe_value`
- `api_server.py` L231：`sanitize_scalar`
- `prediction_archive.py` L27：`json_safe`

三个函数做了相似的事（NaN→None, Timestamp→str, np.integer→int）。提取到统一的 `serialization.py` 模块。

### 1.11 `read_json_file` / `read_json` / `read_model_metadata` — 都是"读 JSON 文件"
- `api_server.py` L274
- `web_app.py` L67
- `dayahead_core.py` L2981

统一提取。

---

## 二、相同的数值指标计算在多个位置重复

### 2.1 `MAE + 0.2 * RMSE` 打分公式 — 出现了 5 次
| 位置 | 函数名 | 文件 |
|------|--------|------|
| L1450 | `segment_model_score` | dayahead_core.py |
| L2010-2016 | `variant_score`（train_and_register 内） | dayahead_core.py |
| L573 | `window_score` | api_server.py |
| L1436-1441 | `candidate_metric_value`（default_score） | dayahead_core.py |
| L106 | `score_interval_metrics` | price_interval.py |

建议抽取为 `def composite_score(mae, rmse, mae_weight=1.0, rmse_weight=0.2)` 公共函数。

### 2.2 加权平均指标汇总 — 出现了 3 次
三个函数做完全相同的事：遍历 `{segment_name: {metrics}}` 字典，用 `valid_rows` 作权重计算加权平均的 MAE、RMSE、P90、方向准确率等。

- `summarize_model_quality_metrics` — dayahead_core.py L2988
- `summarize_variant_display_metrics` — dayahead_core.py L3055
- `summarize_metric_rows` — api_server.py L548

可以统一为一个 `def weighted_summary(segments_metrics, keys)` 函数。

---

## 三、DataFrame 构建模式的高度重复（最重要的问题）

同样的列结构在 4 个地方被独立构建：

### 3.1 `DayAheadDataBuilder.prepare_single_sheet`（L849-872）
### 3.2 `try_load_forecast_template`（L2372-2398）
### 3.3 `load_forecast_generic` 的 fallback 分支（L2480-2498）
### 3.4 `build_reference_frame` 的列过滤（L2571-2583）

四个地方都涉及 `date, period, hour, weekday, month, is_weekend, is_holiday, day_type, total_load, net_load, renewable_power, thermal_space_load_ratio, thermal_on_capacity` 这些字段。

可以提取一个 `def build_day_dataframe(date, periods, total_load, net_load, renewable_power, thermal_on_capacity, day_type, sheet_name, source_file) -> pd.DataFrame` 工厂函数。

---

## 四、`train_and_register` 的 metadata 字典爆炸（L2058-2153）

这是一个约 95 行的字典构造，存在严重的嵌套自重复：

```
metadata = {
  "training_mode": ...,                    # 第1次
  "price_model_training_config": {         # 子字典
    "training_mode": ...,                  # 第2次（同上）
    "training_window_days": ...,
    "valid_days": ...,
    "num_boost_round": ...,
    ...
  },
  "interval_model_training_config": {      # 又一个子字典
    "training_mode": ...,                  # 第3次（同上）
    ...
  },
  "train_config": {                        # 第4层嵌套
    "training_mode": ...,                  # 第4次 + 里面再嵌套 price/interval 子子字典
    "price_model_config": { ... },         # 第5层
    "interval_model_config": { ... },      # 第6层
    "high_price_weighting": { ... },       # 第2次出现 high_price_weighting
    ...
  },
  "high_price_weighting": { ... },         # 第1次出现
  ...
}
```

同一个 `training_mode = "rolling_window" if config.training_window_days else "manual_date_range"` 计算被重复了 6 次。`high_price_weighting` 结构出现了 3 次。

`log_entry`（L2166-2190）又是 `metadata` 的一个子集。

**建议**：抽取 `build_training_config_dict(config)` 函数只构造一次，metadata 和 log_entry 通过浅拷贝 + `|` 合并生成。

---

## 五、三大后端训练/预测分支的重复

### 5.1 训练分支
`train_backend_model`（L1132，回归）和 `train_interval_backend`（price_interval.py L229，分类）有完全相同的 LightGBM/CatBoost/XGBoost 三分支结构，区别只有 objective 参数和 model 类型。

### 5.2 预测分支
`predict_backend_model`（L2249）和 `predict_interval_backend`（price_interval.py L518）同样是三分支分发，区别在于多分类需要 `normalize_probability_matrix`。

### 5.3 加载分支
`load_backend_model`（L2233）和 `load_interval_backend_model`（price_interval.py L447）几乎一致。

**建议**：定义一个 `ModelBackend` 协议（含 `train`, `predict`, `save`, `load`），然后每个后端实现该协议。训练/预测/加载函数就变成一行委托。

---

## 六、`data_quality.py` 内部简化空间

### 6.1 `enrich_issue_dict` 重复调用
`issue_to_dict`（L571）内部调用 `asdict` 后再调 `enrich_issue_dict`。但 `build_issue`（L217）已经在构造时填充了 year/month/day/time_point/excel_cell/location。所以 `enrich_issue_dict` 只在从 JSON 反序列化时才真正有用。

**建议**：去掉 `issue_to_dict` 中的 `enrich_issue_dict` 调用（因为 dataclass 构造时已填好），仅在 `load_quality_report` 中保留。

### 6.2 `add_missing_field_issue` 和 `add_numeric_issues` 参数爆炸
这两个函数各有 9-11 个关键字参数，其中 6 个在每次调用中都是相同的（task_type, action, file_path, sheet_name, date）。可以封装成 `ValidationContext` 对象。

### 6.3 `validate_history_sheet` 承担两种职责
第 388 行的 `if task_type == "predict"` 分支逻辑与 train 分支完全不同。拆成两个独立函数更清晰。

---

## 七、`web_app.py` 列名映射重复

`render_train_tab`（L253）、`render_selected_version_details`（L426）、`render_version_tab`（L496、L517）都重复定义了相同的 `{"baseline_mae": "相似法参考MAE", ...}` 映射。

抽一个模块级 `METRIC_CN_MAP` 字典。

---

## 八、段循环模式遍布各处

以下模式出现了至少 6 次：
```python
for segment_name in segment_definitions:
    segment_df = frame[frame["segment"] == segment_name]
    ...
```

可以封装为 `def iter_segments(frame, segment_definitions) -> Iterator[tuple[str, pd.DataFrame]]`。

---

## 九、`api_server.py` 内部简化空间

### 9.1 预检逻辑与任务分发耦合
`build_train_worker`（L777）中调用了 `validate_training_result_or_restore`，`build_window_optimization_worker`（L1269）中同样调用了。逻辑可以提取到更上层。

### 9.2 `score` 系列函数散落
`window_score`、`rolling_metric_score`、`interval_probability_score`、`business_window_score` 都在 `api_server.py` 中，但核心指标计算逻辑与 `dayahead_core.py` 中的 `segment_model_score`、`score_interval_metrics` 高度重叠。

---

## 十、优先级总表

| 优先级 | 项目 | 收益 | 风险 |
|--------|------|------|------|
| **最高** | 提取公共 DataFrame 构建函数（消除 3.1-3.4 重复） | 消除 ~200 行重复，降低字段不一致的 bug 风险 | 低 |
| **最高** | 合并 1.1-1.11 所有重复工具函数到公共模块 | 消除 ~150 行重复，消除版本不一致的隐藏 bug | 低 |
| **高** | 统一 `MAE+0.2*RMSE` 打分公式 | 保证所有地方用同一公式 | 低 |
| **高** | 重构 metadata 构建为分层工厂函数 | 从 ~95 行减到 ~30 行，消除重复计算 | 中 |
| **中** | 统一后端训练/预测/加载为协议模式 | 减少 ~200 行重复 | 中 |
| **中** | 统一 `summarize_*` 加权平均为通用函数 | 减少 ~80 行重复 | 低 |
| **中** | `data_quality.py` 的 `ValidationContext` 封装 | 减少参数传递 | 低 |
| **中** | `enrich_issue_dict` 去重 | 减少一层包装 | 低 |
| **低** | 提取 `iter_segments` 迭代器 | 减少 ~30 行重复 | 低 |
| **低** | `web_app.py` 列名映射抽取 | 减少 ~30 行 | 低 |
