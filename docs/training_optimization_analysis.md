# 训练流程优化分析报告

## 一、训练流程概览与耗时拆解

`train_and_register()` 完整训练流程分以下阶段：

| 阶段 | 进度区间 | 默认训练量 | 预估耗时占比 |
|------|---------|-----------|-------------|
| 数据加载与特征工程 | 5%-25% | 1次 | ~5% |
| 多后端多特征组合分时段训练 | 25%-75% | 3后端 × 5时段 = 15次 | ~15% |
| 价格区间分类模型训练 | 76% | 3后端 × 5时段 = 15次 | ~10% |
| 火电开机容量模型训练 | 77% | 3后端 × 1模型 = 3次 | ~2% |
| **滚动回测** | **78%-82%** | **(14+30天) × 5时段 = 220次** | **~65%** |
| 元数据写入与版本注册 | 82%-100% | IO操作 | ~3% |

**核心发现：滚动回测占了总耗时的大约 65%，是最大的瓶颈。** 每次回测对每一天、每一时段都从头训练一个新模型（400轮），总共约 220 次独立模型训练。

---

## 二、优化方案（按优先级排列）

### 优化 1：滚动回测使用增量训练（预计提速 3-5 倍，不影响精度）

**问题：** `rolling_backtest_selected_model()` 对滑动窗口中每一天都从零开始训练。但实际上相邻两天的训练数据只差一天（去掉最早那天，加入新的一天），完全不需要从头训练。

**方案：** 对 XGBoost 使用 `xgb.train(..., xgb_model=previous_model)` 参数进行增量续训。在 LightGBM 中可以通过 `init_model` 参数，在 CatBoost 中可以使用 `init_model`。

```python
# XGBoost 示例：将历史模型作为起点继续训练
model = xgb.train(params, dtrain, num_boost_round=delta_rounds, 
                   xgb_model=previous_booster, ...)
```

**效果：** 将 220 次完整训练（每次 400 轮）变成：1 次完整训练 + 219 次小量增量训练（每次可能只需 10-30 轮收敛）。

**精度影响：** 无。增量训练等价于用新数据重新训练。可通过少量额外轮次（如 50 轮）保证充分收敛。

---

### 优化 2：回测任务并行化（预计提速 3-8 倍，不影响精度）

**问题：** 回测中对每一天的训练是完全独立的——第 N 天的训练只依赖"前 N-1 天"的历史数据，与第 N+1 天没有任何依赖关系。

**方案：** 使用 `concurrent.futures.ProcessPoolExecutor` 或 `joblib.Parallel` 并行训练多个日期的模型。

```python
from concurrent.futures import ProcessPoolExecutor, as_completed

def _train_single_day(args):
    test_date, previous_dates, baseline_df, ... = args
    # 训练该日各时段模型并返回预测
    ...

with ProcessPoolExecutor(max_workers=N) as executor:
    futures = {executor.submit(_train_single_day, args): test_date 
               for test_date, args in day_tasks.items()}
    for future in as_completed(futures):
        predictions.append(future.result())
```

**效果：** 在 4-8 核 CPU 上可获得 3-6 倍提速。

**精度影响：** 无。并行计算的是完全独立的任务。

---

### 优化 3：回测模型使用更少的 boosting 轮数（预计提速 2-4 倍，精度影响极小）

**问题：** 回测模型默认使用 `num_boost_round=400`，与正式训练相同。但回测的目的是评估相对效果而非生产精度，可以适当放宽。

**方案：** 为回测单独设置 `rolling_backtest_num_boost_round`，默认值可设为 100-150 轮，同时保持 `early_stopping_rounds=30`。

```python
# TrainConfig 新增字段
rolling_backtest_num_boost_round: int | None = None  # 默认改为 150
```

**精度影响：** 极小。滚动回测用来比较相对排序（选最优模型/窗口），少量轮数减少带来的方差远小于模型选择策略本身的方差。回测模型不用于预测，不影响线上精度。

---

### 优化 4：分时段训练并行化（预计提速 2-3 倍，不影响精度）

**问题：** `train_segment_models()` 中 5 个时段串行训练。各时段模型完全独立。

**方案：** 使用线程池或进程池并行训练各时段模型。

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = []
    for segment_name in segment_definitions:
        futures.append(executor.submit(
            train_single_segment, segment_name, ...
        ))
    # 收集结果
```

**效果：** 5 个时段并行，提速约 3-4 倍（受 CPU 核数限制）。

**精度影响：** 无。各时段训练完全独立。

---

### 优化 5：多后端选择策略优化（预计提速 1.5-2 倍，精度影响极小）

**问题：** 当前默认训练所有后端（XGBoost + LightGBM + CatBoost），然后选最优。实际生产环境通常固定一个后端（如 XGBoost）。

**方案：** 
1. 在后端选择中增加 early-stop：如果第一个后端（XGBoost）的验证集表现已经达到历史好水平，跳过后续后端训练。
2. 或者提供一个 "快速训练" 模式，仅训练默认后端。

**精度影响：** 极小。如果 XGBoost 表现已经足够好，跳过其他后端不会影响最终模型质量。保守做法是仅在新数据分布变化较大时才重新扫描所有后端。

---

### 优化 6：特征缓存粒度细化（预计提速 10-20%，不影响精度）

**问题：** `attach_similarity_features()` 对每个历史日期依次循环计算，O(n²) 复杂度。在训练窗口较大时（如 240 天），计算量可观。

**方案：** 使用向量化操作替代逐日期循环。

```python
# 当前逐日期循环：
for index in range(1, len(unique_dates)):
    # 对每一天做 nearest_similarity_price 查询

# 优化：使用滑动窗口 + cdist 批量计算
from scipy.spatial.distance import cdist
# 预计算 load matrix，批量计算距离矩阵
```

**精度影响：** 无。计算结果完全相同，只是实现方式从循环变为矩阵运算。

---

### 优化 7：减少 DMatrix 重复构建（预计提速 5-10%，不影响精度）

**问题：** `train_backend_model()` 和 `predict_backend_model()` 每次调用都重新构建 XGBoost DMatrix。在回测中，同一份数据可能被多次构建。

**方案：** 在回测循环中复用已构建的 DMatrix，或缓存最近的 DMatrix。

---

## 三、综合优化效果预估

| 优化项 | 预计提速 | 精度影响 | 实现难度 |
|--------|---------|---------|---------|
| 1. 回测增量训练 | 3-5× | 无 | 中 |
| 2. 回测并行化 | 3-6× | 无 | 中 |
| 3. 回测减少轮数 | 2-4× | 极小 | 低 |
| 4. 分时段并行 | 2-3× | 无 | 低 |
| 5. 后端提前终止 | 1.5-2× | 极小 | 低 |
| 6. 特征向量化 | 10-20% | 无 | 中 |
| 7. DMatrix复用 | 5-10% | 无 | 低 |

**叠加效果：** 如果实现优化 1-5，训练总耗时预计可从当前的若干小时级别降低到 **30-60 分钟**（保守估计提速 5-10 倍）。

---

## 四、建议实施优先级

**第一批（低难度、高收益）：**
- 优化 4：分时段训练并行化
- 优化 3：回测独立配置 num_boost_round
- 优化 5：后端提前终止/快速模式

**第二批（中等难度、极高收益）：**
- 优化 1：回测增量训练
- 优化 2：回测并行化

**第三批（锦上添花）：**
- 优化 6：特征计算向量化
- 优化 7：DMatrix 复用

---

## 五、风险提示

1. **增量训练（优化 1）** 需要验证滑动窗口增量训练的数值稳定性（使用完全重新训练作为 ground truth 对比）。
2. **并行化（优化 2、4）** 在多进程场景需注意内存占用，建议使用 `ProcessPoolExecutor` 配合 `max_tasks_per_child` 防止内存泄漏。
3. **减少轮数（优化 3）** 建议先在回测结果中对比 400 轮 vs 150 轮的模型排序一致性，确认无显著差异后再上线。
