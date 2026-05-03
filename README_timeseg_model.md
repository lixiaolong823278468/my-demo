# 日前电价预测系统使用文档

## 1. 系统概览

当前系统已经实现以下能力：

- 未来 96 点日前出清价格预测
- 分时段建模
- 相似法基线 + XGBoost 残差修正
- 自定义历史训练时间范围
- 手动重训
- 保留当前模型、上一版模型、历史训练日志与指标
- 预测 Excel 自动回填 `预测价格`
- 真正前后端分离：`HTML / JS / CSS` 独立前端 + `Python API` 后端
- Windows 桌面入口保留

## 2. 当前目录结构

- `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_core.py`：核心训练、预测、版本管理逻辑
- `D:\每日工作\代码示例\预测程序-------\demo1\dayahead_timeseg_model.py`：命令行入口
- `D:\每日工作\代码示例\预测程序-------\demo1\api_server.py`：Python API 后端入口
- `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\`：真正独立前端工程
- `D:\每日工作\代码示例\预测程序-------\demo1\web_app.py`：旧版 Streamlit 原型，现不作为主入口
- `D:\每日工作\代码示例\预测程序-------\demo1\desktop_app.py`：桌面应用入口
- `D:\每日工作\代码示例\预测程序-------\demo1\launch_web.bat`：启动前后端分离网页版
- `D:\每日工作\代码示例\预测程序-------\demo1\launch_desktop.bat`：启动桌面版
- `D:\每日工作\代码示例\预测程序-------\demo1\package_desktop.bat`：打包桌面版
- `D:\每日工作\代码示例\预测程序-------\demo1\数据\`：历史 Excel 数据目录
- `D:\每日工作\代码示例\预测程序-------\demo1\预测文件\`：预测输入文件目录
- `D:\每日工作\代码示例\预测程序-------\demo1\models\`：模型目录
- `D:\每日工作\代码示例\预测程序-------\demo1\output\`：预测输出目录

## 3. 数据要求

### 3.1 历史数据

- 存放在 `D:\每日工作\代码示例\预测程序-------\demo1\数据\`
- 按年存放，例如：
  - `D:\每日工作\代码示例\预测程序-------\demo1\数据\2025年`
  - `D:\每日工作\代码示例\预测程序-------\demo1\数据\2026年`
- 每个 Excel 文件中：
  - 每个 Sheet 表示一天
  - 第 1 行为字段名
  - 第 2 ~ 97 行为 96 个 15 分钟时段

### 3.2 预测文件

默认预测文件为：

- `D:\每日工作\代码示例\预测程序-------\demo1\预测文件\预测文件.xlsx`

当前模板支持按列头中的日期自动识别：

- 最新日期作为预测日
- 默认把参考日价格作为 `lag_96`，用于带 `lag_96` 的模型
- 如果训练时关闭 `lag_96`，预测时会自动跟随模型元数据，不再强制要求参考日价格列
- 预测结果自动写回 `预测价格` 列

## 4. 如何启动与使用

### 4.1 进入目录

```bash
cd /d D:\每日工作\代码示例\预测程序-------\demo1
```

### 4.2 启动网页版

推荐直接双击：

```bash
launch_web.bat
```

或命令行启动：

```bash
python api_server.py --open-browser
```

启动后浏览器会打开：

- `http://127.0.0.1:8000`

网页中可直接：

- 选择训练起止日期
- 点击 `手动重训模型`
- 查看当前模型、上一版模型和历史版本
- 直接编辑预测文件表格
- 点击 `执行预测`
- 实时查看运行状态、进度条、日志和预测曲线

### 4.3 命令行训练模型

全量训练：

```bash
python dayahead_timeseg_model.py train
```

只用 `2025-01-01` 之后的数据：

```bash
python dayahead_timeseg_model.py train --start-date 2025-01-01
```

只用 `2026-02-01` 到 `2026-03-31`：

```bash
python dayahead_timeseg_model.py train --start-date 2026-02-01 --end-date 2026-03-31
```

指定验证集和训练轮数：

```bash
python dayahead_timeseg_model.py train --valid-days 14 --num-boost-round 500
```

关闭 `lag_96` 特征训练：

```bash
python dayahead_timeseg_model.py train --no-lag-96
```

调整相似法权重：

```bash
python dayahead_timeseg_model.py train --similarity-weights "{\"thermal_space\":0.45,\"renewable_power\":0.15,\"thermal_on_capacity\":0.2,\"day_type\":0.1,\"thermal_space_load_ratio\":0.1}"
```

默认权重为：火电空间 `0.45`、新能源 `0.15`、火电容量 `0.20`、日期类型 `0.10`、供需比 `0.10`。权重会写入 `metadata.json` 和 `training_runs.jsonl`，预测时会按当前模型元数据继续使用同一组权重。

### 4.4 命令行执行预测

```bash
python dayahead_timeseg_model.py predict --forecast-file ".\预测文件\预测文件.xlsx"
```

执行后会：

- 输出结果到 `D:\每日工作\代码示例\预测程序-------\demo1\output\dayahead_price_prediction.xlsx`
- 自动回填 `预测文件.xlsx` 中的 `预测价格` 列

### 4.5 查看训练日志

```bash
python dayahead_timeseg_model.py runs
```

### 4.6 回退到上一版模型

```bash
python dayahead_timeseg_model.py rollback
```

## 5. 前端资源目录说明

真正运行中的前端资源在：

- `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\index.html`
- `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.css`
- `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\app.js`
- `D:\每日工作\代码示例\预测程序-------\demo1\frontend_app\assets\vendor\echarts.min.js`

说明如下：

- `frontend_app\index.html`
  - 单页前端入口
  - 负责页面结构、卡片区域、训练页、预测页、版本页、日志页
- `frontend_app\assets\app.css`
  - 前端样式文件
  - 负责 Ant Design Pro 风格的配色、留白、按钮、卡片、表格、浮动状态窗等视觉效果
- `frontend_app\assets\app.js`
  - 前端交互脚本
  - 负责通过 `fetch` 调用 Python API
  - 负责表格编辑、训练与预测按钮、模型版本切换、进度刷新、状态日志展示、曲线渲染
- `frontend_app\assets\vendor\echarts.min.js`
  - 本地 ECharts 资源
  - 用于 96 点预测曲线、提示框、缩放和图例显示

后端通过 `api_server.py` 提供 API 和静态资源服务，前端不再嵌入 Python 文件内部。

## 6. API 后端说明

后端入口：

- `D:\每日工作\代码示例\预测程序-------\demo1\api_server.py`

主要接口包括：

- `GET /api/config`：读取基础路径与价格上下限
- `GET /api/status`：读取当前运行状态、进度和最近结果
- `GET /api/model/current`：读取当前默认模型元数据
- `GET /api/model/versions`：读取正式训练版本列表
- `GET /api/training/logs`：读取训练日志
- `GET /api/forecast/template`：读取预测文件首个 Sheet 并返回表格数据
- `POST /api/forecast/template/save`：保存网页中编辑后的预测文件
- `POST /api/train`：启动后台训练任务
- `POST /api/predict`：启动后台预测任务
- `POST /api/model/activate`：切换默认模型
- `POST /api/model/rollback`：回退到上一版模型
- `POST /api/model/delete`：批量删除历史模型
- `GET /download/output`：下载最新预测结果文件

## 7. 模型版本管理

系统自动保留：

- `models\current`：当前默认模型
- `models\previous`：上一版模型
- `models\history\run_xxx`：每次正式训练后的历史模型
- `models\training_runs.jsonl`：每次训练日志

当前网页版版本列表只展示正式训练版本：

- 会展示 `run_...` 版本
- 不会把 `rollback_backup_...` 这种内部回退备份混入正式版本列表

同时保留以下规则：

- 最新模型默认作为默认模型
- 回退到旧模型时，当前模型仍会保留为上一版
- 默认模型和上一版模型受保护，不能直接删除

## 8. 新历史数据后的重训机制

当你把新的历史 Excel 放入 `D:\每日工作\代码示例\预测程序-------\demo1\数据\` 后：

- 可以直接重新运行 `train`
- 或在网页里点击 `手动重训模型`

系统会：

- 用最新历史数据重新训练
- 自动生成新的正式模型版本
- 保留旧版本
- 记录本次训练指标和日志

## 9. 自定义历史时间范围

支持通过以下方式控制训练范围：

- 网页版中设置 `训练起始日期` 与 `训练结束日期`
- 命令行使用 `--start-date`
- 命令行使用 `--end-date`

典型用法：

- 只用 `2025-01-01` 之后的数据
- 只用 `2026-02-01` 之后的数据
- 只用某一段市场机制更接近当前的近期数据

这在电力现货建模里很重要，因为：

- 过早的数据可能与当前市场规律不一致
- 历史跨度过长有时会降低当前阶段预测效果

## 10. 当前预测方法说明

当前并不是直接用 XGBoost 预测最终价格，而是两步法：

### 10.1 第一步：相似法基线

以预测日的 `火电空间 / 新能源出力 / 火电容量 / 日期类型 / 供需比` 为目标，在参考日中寻找最相近的点，形成相似法基线价格。

### 10.2 第二步：XGBoost 预测残差

模型学习的是：

```text
残差 = 实际日前价格 - 相似法基线价格
```

最终结果为：

```text
最终预测价格 = 相似法基线价格 + 模型预测残差
```

这样做的优点：

- 更接近人工“相似法”思路
- 可解释性更强
- 通常比纯机器学习直接预测更稳

### 10.3 相似法权重贯穿逻辑

相似法权重用于控制“什么样的历史时段算更相似”。当前支持 4 个权重：

- `thermal_space`：火电空间权重，内部计算为 `用电负荷 - 新能源出力`
- `renewable_power`：新能源出力权重
- `thermal_on_capacity`：火电容量权重
- `day_type`：日期类型权重
- `thermal_space_load_ratio`：供需比权重，内部计算为 `火电空间 / 用电负荷`

这组权重会贯穿训练、缓存、元数据和预测链路：

- 训练链路：权重真正参与相似法计算，用来生成 `similar_price` 和 `similar_gap`，再训练 XGBoost 残差模型。
- 缓存：权重作为训练特征缓存 key 的一部分。修改权重后，系统会重新生成相似法特征，避免误用旧权重生成过的缓存。
- 元数据：训练完成后，权重会写入当前模型的 `metadata.json` 和 `models\training_runs.jsonl`，便于复盘每次模型版本的相似法设置。
- 预测链路：预测时会读取当前模型 `metadata.json` 中保存的权重，用同一组权重重新计算预测日的相似法基线，保证训练和预测对“相似”的定义一致。

简单理解：权重主要影响 `相似法基线价格`；缓存和元数据用于保证不串旧结果、可追溯、训练预测一致。

训练页面还会单独维护一份页面偏好：

- 偏好文件位置：`models\training_preferences.json`
- 用途：只决定训练页面下次默认显示什么权重
- 保存时机：在网页训练页面修改权重后会自动保存；点击 `手动重训模型` 时也会再次保存当前页面权重
- 独立性：切换默认模型、回退模型、删除历史模型都不会覆盖训练页面偏好
- 与模型元数据区别：`training_preferences.json` 是页面默认值，`metadata.json` 是某个模型实际训练时使用的权重

### 10.4 `lag_96` 开关

`lag_96` 表示参考日/昨日同一时段价格。它不是电价形成原因，只是给模型提供近期价格状态参考。

- 默认训练会使用 `lag_96`
- 网页训练参数里可以取消勾选 `使用 lag_96（参考日/昨日同点价格）`
- 命令行可使用 `--no-lag-96`
- 预测时不需要手动选择，系统会读取当前模型 `metadata.json` 中的 `feature_columns` 自动判断是否需要 `lag_96`

## 11. 价格边界约束

山西省日前电价预测结果统一限制在：

```text
0 ~ 1500 元/兆瓦时
```

该约束已经写入核心预测链路：

- 网页预测
- 命令行预测
- Excel 回填
- 导出文件

都会保持一致。

## 12. XGBoost 参数详细说明

当前默认参数为：

```python
eta = 0.05
max_depth = 5
min_child_weight = 3
subsample = 0.85
colsample_bytree = 0.85
num_boost_round = 400
```

### 12.1 `eta`

也叫学习率。

作用：

- 控制每一轮树对结果的修正幅度

影响：

- 越小：学习更慢、更稳，不容易过拟合，但通常要更多轮数
- 越大：学习更快，但更容易波动和过拟合

调参建议：

- 如果验证集误差波动大，可以适当降低
- 如果模型明显欠拟合，可以适当提高

### 12.2 `max_depth`

单棵树最大深度。

作用：

- 控制模型复杂度

影响：

- 越大：能学习更复杂关系，但更容易过拟合
- 越小：泛化更稳，但可能欠拟合

调参建议：

- 若模型对尖峰电价抓不住，可尝试略增
- 若训练很好、验证变差，可尝试略减

### 12.3 `min_child_weight`

叶子节点继续分裂所需的最小样本权重。

作用：

- 控制树是否容易继续细分

影响：

- 越大：更保守，不容易过拟合
- 越小：更容易学习细节，也更容易吃噪声

调参建议：

- 数据波动噪声大时可适当增大
- 需要捕捉更细的尖峰时可适当减小

### 12.4 `subsample`

每轮训练抽取样本比例。

作用：

- 控制样本采样强度

影响：

- 越小：随机性更强，抗过拟合更好，但可能不稳定
- 越大：更充分利用数据，但可能过拟合

调参建议：

- 若训练集很好而验证集一般，可适当降低

### 12.5 `colsample_bytree`

每棵树抽取特征比例。

作用：

- 控制特征采样强度

影响：

- 越小：模型更保守，更抗过拟合
- 越大：更充分使用全部特征

调参建议：

- 特征之间相关性高时，可适当降低

### 12.6 `num_boost_round`

总训练轮数。

作用：

- 控制树的总数量

影响：

- 太少：容易欠拟合
- 太多：训练时间增加，也可能过拟合

调参建议：

- 配合 `eta` 一起看
- `eta` 低时通常需要更高轮数

## 13. 桌面版与打包

桌面版启动：

```bash
launch_desktop.bat
```

或：

```bash
python desktop_app.py
```

桌面版打包：

```bash
package_desktop.bat
```

或：

```bash
pyinstaller -F -w desktop_app.py --name dayahead_predictor_desktop
```
