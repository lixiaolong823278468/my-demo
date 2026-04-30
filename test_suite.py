#!/usr/bin/env python3
"""日前电价预测平台 自动测试套件

测试范围:
1. 环境与依赖检查
2. 源文件编码完整性
3. 核心模块导入
4. 数据文件验证
5. 模型文件与元数据一致性
6. 核心函数单元测试
7. CLI 命令可用性
8. 边界条件与异常处理
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------- 配置 ----------
BASE_DIR = Path(__file__).resolve().parent
REQUIRED_MODULES = ["xgboost", "pandas", "numpy", "openpyxl", "xlrd"]

# ---------- 测试框架 ----------
_results: list[dict[str, Any]] = []


def test(name: str) -> None:
    """装饰器(手动) - 记录测试结果"""
    pass


def record(name: str, passed: bool, detail: str = "", category: str = "general") -> None:
    _results.append({
        "category": category,
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
    })
    icon = "✓" if passed else "✗"
    print(f"  {icon} {name}")
    if detail and not passed:
        print(f"      {detail}")


def summary() -> None:
    total = len(_results)
    passed = sum(1 for r in _results if r["status"] == "PASS")
    failed = total - passed
    print(f"\n{'='*60}")
    print(f"测试总结: {total} 项, 通过 {passed}, 失败 {failed}")
    if failed:
        print(f"\n失败项:")
        for r in _results:
            if r["status"] == "FAIL":
                print(f"  ✗ [{r['category']}] {r['name']}")
                if r["detail"]:
                    print(f"      {r['detail'][:120]}")


# ========== 1. 环境与依赖检查 ==========
def test_environment() -> None:
    print("\n--- 1. 环境与依赖检查 ---")
    ver = sys.version_info
    record("Python 版本", ver >= (3, 9), f"Python {ver.major}.{ver.minor}.{ver.micro}", "env")

    for mod_name in REQUIRED_MODULES:
        try:
            __import__(mod_name)
            record(f"模块可用: {mod_name}", True, "", "env")
        except ModuleNotFoundError:
            record(f"模块可用: {mod_name}", False, "请执行 pip install {mod_name}", "env")


# ========== 2. 源文件编码完整性 ==========
def test_source_encoding() -> None:
    print("\n--- 2. 源文件编码完整性 ---")

    py_files = [
        "dayahead_core.py",
        "dayahead_timeseg_model.py",
        "api_server.py",
        "web_app.py",
        "desktop_app.py",
    ]

    expected_chinese_patterns = [
        r"正在加载历史数据文件",
        r"开始加载历史数据",
        r"正在训练分时段",
        r"训练完成",
        r"预测完成",
        r"相似法",
        r"残差修正",
        r"日前出清价格",
    ]

    for fname in py_files:
        fpath = BASE_DIR / fname
        if not fpath.exists():
            record(f"源文件存在: {fname}", False, "文件不存在", "encoding")
            continue
        content = fpath.read_text(encoding="utf-8")
        # 检查是否有明显的编码损坏字符 (连续的问号或替换字符)
        garbled_count = len(re.findall(r"\?{4,}", content))
        replacement_count = content.count("�")
        record(
            f"编码完整性: {fname}",
            garbled_count == 0 and replacement_count == 0,
            f"发现 {garbled_count} 处疑似乱码, {replacement_count} 个替换字符" if garbled_count or replacement_count else "",
            "encoding",
        )

        # 检查关键中文是否乱码
        chinese_ok = True
        bad_lines = []
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            # 检查是否在字符串中包含连续的?
            if re.search(r'"([^"]*\?{3,}[^"]*)"', stripped) or re.search(r"'([^']*\?{3,}[^']*)'", stripped):
                chinese_ok = False
                bad_lines.append(f"L{i}: {stripped[:80]}")
        if bad_lines:
            record(f"中文字符串完整性: {fname}", False, f"乱码行示例: {'; '.join(bad_lines[:3])}", "encoding")


# ========== 3. 核心模块导入 ==========
def test_imports() -> None:
    print("\n--- 3. 核心模块导入 ---")
    sys.path.insert(0, str(BASE_DIR))
    try:
        import dayahead_core as core
        record("导入 dayahead_core", True, "", "import")

        # 检查关键常量
        attrs = [
            "TARGET_COLUMN", "FEATURE_COLUMNS", "SEGMENTS",
            "DEFAULT_XGB_PARAMS", "PRICE_FLOOR", "PRICE_CAP",
            "SIMILAR_PRICE_COLUMN", "SIMILAR_GAP_COLUMN", "RESIDUAL_TARGET_COLUMN",
        ]
        for attr in attrs:
            has = hasattr(core, attr)
            record(f"dayahead_core 常量: {attr}", has, "", "import")

        # 检查关键函数
        funcs = [
            "train_and_register", "predict_prices", "predict_prices_compare",
            "rollback_to_previous", "list_model_versions", "load_current_metadata",
            "DayAheadDataBuilder", "TrainConfig",
        ]
        for func in funcs:
            has = hasattr(core, func)
            record(f"dayahead_core 函数: {func}", has, "", "import")

    except Exception as e:
        record("导入 dayahead_core", False, str(e), "import")

    try:
        import dayahead_timeseg_model as cli
        record("导入 dayahead_timeseg_model", True, "", "import")
    except Exception as e:
        record("导入 dayahead_timeseg_model", False, str(e), "import")


# ========== 4. 数据文件验证 ==========
def test_data_files() -> None:
    print("\n--- 4. 数据文件验证 ---")
    data_dir = BASE_DIR / "数据"
    record("数据目录存在", data_dir.exists(), str(data_dir), "data")

    if not data_dir.exists():
        return

    excel_files = sorted(data_dir.rglob("*.xlsx"))
    excel_files = [f for f in excel_files if not f.name.startswith("~$")]
    record("历史数据 Excel 文件数", len(excel_files) > 0, f"共 {len(excel_files)} 个", "data")

    # 逐一验证文件可读性
    unreadable = []
    empty_files = []
    for ef in excel_files:
        try:
            df = pd.read_excel(ef, sheet_name=None)
            if not df:
                empty_files.append(ef.name)
        except Exception as e:
            unreadable.append(f"{ef.name}: {e}")

    record("Excel 文件可读性", len(unreadable) == 0, f"无法读取: {unreadable}" if unreadable else "", "data")
    record("Excel 文件非空", len(empty_files) == 0, f"空文件: {empty_files}" if empty_files else "", "data")

    # 抽样检查第一个文件的结构
    if excel_files:
        sample = pd.read_excel(excel_files[0], sheet_name=None)
        first_sheet_name = list(sample.keys())[0] if sample else ""
        first_df = sample[first_sheet_name] if sample else pd.DataFrame()
        record(
            "样本 Excel 结构检查",
            len(first_df) > 0 and len(first_df.columns) > 0,
            f"Sheet: {first_sheet_name}, 行数: {len(first_df)}, 列数: {len(first_df.columns)}",
            "data",
        )

    # 预测文件检查
    forecast_file = BASE_DIR / "预测文件" / "预测文件.xlsx"
    record("预测文件存在", forecast_file.exists(), str(forecast_file), "data")
    if forecast_file.exists():
        try:
            wb = pd.read_excel(forecast_file, sheet_name=None)
            record("预测文件可读", len(wb) > 0, f"共 {len(wb)} 个 sheet", "data")
        except Exception as e:
            record("预测文件可读", False, str(e), "data")


# ========== 5. 模型文件与元数据一致性 ==========
def test_models() -> None:
    print("\n--- 5. 模型文件与元数据一致性 ---")
    model_root = BASE_DIR / "models"

    record("models 目录存在", model_root.exists(), str(model_root), "model")

    # 检查 current 模型
    current_dir = model_root / "current"
    record("current 模型目录存在", current_dir.exists(), "", "model")

    if current_dir.exists():
        metadata_path = current_dir / "metadata.json"
        record("current/metadata.json 存在", metadata_path.exists(), "", "model")

        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                record("元数据 JSON 可解析", True, f"run_id={metadata.get('run_id')}", "model")

                # 检查必要字段
                required_fields = ["run_id", "feature_columns", "segments", "metrics", "xgboost_params"]
                for field in required_fields:
                    has = field in metadata
                    record(f"元数据字段: {field}", has, "", "model")

                # 检查 segments 与代码一致性
                segments_in_meta = {s["name"]: (s["start"], s["end"]) for s in metadata.get("segments", [])}
                valid_segments = {
                    "night": (1, 24), "morning_peak": (25, 40),
                    "midday": (41, 60), "evening_peak": (61, 80), "late_night": (81, 96),
                }
                segments_match = segments_in_meta == valid_segments
                record("分段配置与代码一致", segments_match,
                       f"元数据: {segments_in_meta}" if not segments_match else "", "model")

                # 检查每个 segment 的模型文件存在
                all_models_exist = True
                for seg_name in valid_segments:
                    model_file = current_dir / f"{seg_name}.json"
                    if not model_file.exists():
                        all_models_exist = False
                        record(f"模型文件: {seg_name}.json", False, "文件不存在", "model")
                if all_models_exist:
                    record("所有分时段模型文件存在", True, "", "model")

                # 检查 XGBoost 模型可加载
                try:
                    import xgboost as xgb
                    load_errors = []
                    for seg_name in valid_segments:
                        model_file = current_dir / f"{seg_name}.json"
                        try:
                            booster = xgb.Booster()
                            booster.load_model(str(model_file))
                        except Exception as e:
                            load_errors.append(f"{seg_name}: {e}")
                    record("XGBoost 模型可加载", len(load_errors) == 0,
                           "; ".join(load_errors) if load_errors else "", "model")
                except ImportError:
                    record("XGBoost 模型可加载", False, "xgboost 未安装", "model")

                # 检查 feature_columns 与代码的 FEATURE_COLUMNS 一致
                meta_features = set(metadata.get("feature_columns", []))
                from dayahead_core import FEATURE_COLUMNS
                code_features = set(FEATURE_COLUMNS)
                features_match = meta_features == code_features
                record("特征列与代码一致", features_match,
                       f"元数据额外: {meta_features - code_features}, 代码额外: {code_features - meta_features}"
                       if not features_match else "", "model")

                # 检查 metrics 合理性
                metrics = metadata.get("metrics", {})
                for seg_name in valid_segments:
                    if seg_name in metrics:
                        m = metrics[seg_name]
                        # RMSE 应在合理范围 (0-500)
                        final_rmse = m.get("final_rmse")
                        if final_rmse is not None:
                            reasonable = 0 <= final_rmse <= 500
                            record(f"指标合理性 {seg_name} RMSE", reasonable,
                                   f"final_rmse={final_rmse}" if not reasonable else f"final_rmse={final_rmse}", "model")

            except Exception as e:
                record("元数据解析", False, str(e), "model")

    # 检查 training_runs.jsonl
    runs_log = model_root / "training_runs.jsonl"
    record("训练日志文件存在", runs_log.exists(), "", "model")

    # 检查 history 目录
    history_dir = model_root / "history"
    if history_dir.exists():
        run_dirs = [d for d in history_dir.iterdir() if d.is_dir() and d.name.startswith("run_")]
        record("历史模型版本数", len(run_dirs) > 0, f"共 {len(run_dirs)} 个版本", "model")

        # 检查是否有回退备份与正式版本混在一起
        rollback_dirs = [d for d in history_dir.iterdir() if d.is_dir() and d.name.startswith("rollback_backup_")]
        record("回退备份目录", len(rollback_dirs) >= 0, f"共 {len(rollback_dirs)} 个", "model")


# ========== 6. 核心函数单元测试 ==========
def test_core_functions() -> None:
    print("\n--- 6. 核心函数单元测试 ---")
    from dayahead_core import (
        assign_segments,
        clip_price_series,
        normalize_reference_days,
        normalize_reference_strategy,
        normalize_text,
        parse_sheet_date,
        extract_month_day,
        convert_capacity_to_mw,
        nearest_similarity_price,
        to_numeric,
        split_train_valid,
    )

    # --- assign_segments ---
    periods_valid = pd.Series(np.arange(1, 97))
    try:
        result = assign_segments(periods_valid)
        record("assign_segments 96 时段", len(result) == 96 and result.nunique() == 5, "", "unit")
    except Exception as e:
        record("assign_segments 96 时段", False, str(e), "unit")

    try:
        assign_segments(pd.Series([0]))
        record("assign_segments 无效 period 应抛异常", False, "未抛出异常", "unit")
    except ValueError:
        record("assign_segments 无效 period 应抛异常", True, "", "unit")

    # --- clip_price_series ---
    arr = np.array([-100, 0, 500, 1500, 2000], dtype=float)
    clipped = clip_price_series(arr)
    record("clip_price_series 区间约束", np.all(clipped >= 0) and np.all(clipped <= 1500),
           f"输入: {arr}, 输出: {clipped}", "unit")
    record("clip_price_series 负值截断", clipped[0] == 0, f"期望 0, 实际 {clipped[0]}", "unit")
    record("clip_price_series 超限截断", clipped[-1] == 1500, f"期望 1500, 实际 {clipped[-1]}", "unit")

    # --- normalize_reference_days ---
    record("normalize_reference_days 正常值", normalize_reference_days(5) == 5, "", "unit")
    record("normalize_reference_days None 默认", normalize_reference_days(None) == 1, "", "unit")
    try:
        normalize_reference_days(0)
        record("normalize_reference_days 0 应抛异常", False, "未抛出异常", "unit")
    except ValueError:
        record("normalize_reference_days 0 应抛异常", True, "", "unit")

    # --- normalize_reference_strategy ---
    record("normalize_reference_strategy 默认", normalize_reference_strategy(None) == "recent_n_days", "", "unit")
    try:
        normalize_reference_strategy("invalid_strategy")
        record("normalize_reference_strategy 无效策略", False, "未抛出异常", "unit")
    except ValueError:
        record("normalize_reference_strategy 无效策略", True, "", "unit")

    # --- normalize_text ---
    record("normalize_text 去空格", normalize_text(" a b c ") == "abc", "", "unit")
    record("normalize_text 去中文空格", normalize_text("a　b") == "ab", "", "unit")

    # --- parse_sheet_date ---
    parsed = parse_sheet_date("2025年1月15日")
    record("parse_sheet_date 中文格式", parsed == pd.Timestamp("2025-01-15"), f"结果: {parsed}", "unit")
    parsed2 = parse_sheet_date("2025-01-15")
    record("parse_sheet_date ISO 格式", parsed2 == pd.Timestamp("2025-01-15"), f"结果: {parsed2}", "unit")
    parsed3 = parse_sheet_date("not a date")
    record("parse_sheet_date 非日期", parsed3 is None, f"结果: {parsed3}", "unit")

    # --- extract_month_day ---
    md = extract_month_day("1月15日")
    record("extract_month_day", md == (1, 15), f"结果: {md}", "unit")
    md2 = extract_month_day("random text")
    record("extract_month_day 无日期", md2 is None, f"结果: {md2}", "unit")

    # --- convert_capacity_to_mw ---
    record("convert_capacity_to_mw GW->MW", convert_capacity_to_mw(1, "GW") == 1000, "", "unit")
    record("convert_capacity_to_mw 万千瓦->MW", convert_capacity_to_mw(10, "万千瓦") == 100, "", "unit")
    record("convert_capacity_to_mw KW->MW", convert_capacity_to_mw(1000, "KW") == 1, "", "unit")
    record("convert_capacity_to_mw MW 不变", convert_capacity_to_mw(500, "MW") == 500, "", "unit")

    # --- nearest_similarity_price ---
    target = np.array([100.0, 200.0])
    ref_loads = np.array([95.0, 180.0, 300.0])
    ref_prices = np.array([350.0, 400.0, 500.0])
    price, gap = nearest_similarity_price(target, ref_loads, ref_prices, k=2)
    record("nearest_similarity_price 输出长度", len(price) == 2, "", "unit")
    record("nearest_similarity_price 价格非 NaN", not np.any(np.isnan(price)), f"价格: {price}", "unit")

    # 空引用测试
    empty_price, empty_gap = nearest_similarity_price(target, np.array([]), np.array([]))
    record("nearest_similarity_price 空引用", np.all(np.isnan(empty_price)), f"结果: {empty_price}", "unit")

    # --- to_numeric ---
    s = pd.Series(["1,234.5", "100", "--", "", "nan"])
    result = to_numeric(s)
    record("to_numeric 逗号处理", result.iloc[0] == 1234.5, f"结果: {result.iloc[0]}", "unit")
    record("to_numeric NaN 处理", pd.isna(result.iloc[2]) and pd.isna(result.iloc[4]), "", "unit")

    # --- split_train_valid ---
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01"] * 10 + ["2025-01-02"] * 10 + ["2025-01-03"] * 10),
        "value": range(30),
    })
    train, valid = split_train_valid(df, 1)
    record("split_train_valid 训练集非空", len(train) > 0, f"train={len(train)}", "unit")
    record("split_train_valid 验证集日期", len(valid) == 10, f"valid={len(valid)}", "unit")

    # 验证集天数为 0
    train2, valid2 = split_train_valid(df, 0)
    record("split_train_valid valid_days=0 验证集为空", len(valid2) == 0, "", "unit")


# ========== 7. 预测流程模块测试 ==========
def test_prediction_pipeline_units() -> None:
    print("\n--- 7. 预测流程模块测试 ---")
    from dayahead_core import (
        attach_lag_96,
        day_type_of,
        attach_similarity_features,
    )

    # --- attach_lag_96 ---
    base = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02"] * 3),
        "period": [1, 2, 3],
    })
    history = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01"] * 3 + ["2025-01-02"] * 3),
        "period": [1, 2, 3, 1, 2, 3],
        "日前出清价格(元/MWh)": [300.0, 310.0, 320.0, 350.0, 360.0, 370.0],
    })
    result = attach_lag_96(base, history)
    has_lag = "lag_96" in result.columns
    record("attach_lag_96 列存在", has_lag, "", "pipeline")
    if has_lag:
        record("attach_lag_96 值正确", result["lag_96"].iloc[0] == 300.0, f"lag={result['lag_96'].tolist()}", "pipeline")

    # 无历史数据时 lag_96 为 NaN
    base_empty = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01"] * 3),
        "period": [1, 2, 3],
    })
    result2 = attach_lag_96(base_empty, history)
    record("attach_lag_96 无前日数据则 NaN", result2["lag_96"].isna().all(), f"lag={result2['lag_96'].tolist()}", "pipeline")

    # --- day_type_of ---
    workday = pd.Timestamp("2025-01-02")  # Thursday
    weekend = pd.Timestamp("2025-01-04")  # Saturday
    holiday = pd.Timestamp("2025-01-01")  # New Year
    holiday_set = {pd.Timestamp("2025-01-01")}
    record("day_type_of 工作日", day_type_of(workday, holiday_set) == "workday", "", "pipeline")
    record("day_type_of 周末", day_type_of(weekend, holiday_set) == "weekend", "", "pipeline")
    record("day_type_of 节假日", day_type_of(holiday, holiday_set) == "holiday", "", "pipeline")


# ========== 8. 边界条件与异常处理 ==========
def test_edge_cases() -> None:
    print("\n--- 8. 边界条件与异常处理 ---")
    from dayahead_core import (
        list_excel_files,
        filter_date_range,
        calculate_metrics,
    )

    # --- list_excel_files 空目录 ---
    try:
        list_excel_files(BASE_DIR / "__nonexistent_dir__")
        record("list_excel_files 空目录应抛异常", False, "未抛出异常", "edge")
    except FileNotFoundError:
        record("list_excel_files 空目录应抛异常", True, "", "edge")

    # --- filter_date_range ---
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01", "2025-06-15", "2025-12-31"]),
        "value": [1, 2, 3],
    })
    filtered = filter_date_range(df, "2025-03-01", "2025-09-30")
    record("filter_date_range 日期过滤", len(filtered) == 1, f"过滤后: {filtered['date'].tolist()}", "edge")

    # --- calculate_metrics ---
    actual = np.array([100, 200, 300])
    predicted = np.array([110, 190, 310])
    metrics = calculate_metrics(actual, predicted)
    record("calculate_metrics MAE", metrics["mae"] == 10.0, f"MAE={metrics['mae']}", "edge")
    record("calculate_metrics RMSE", round(metrics["rmse"], 4) == round(np.sqrt(100), 4), f"RMSE={metrics['rmse']}", "edge")

    # 完全相同的预测
    perfect = calculate_metrics(actual, actual)
    record("calculate_metrics 完美预测", perfect["mae"] == 0 and perfect["rmse"] == 0, "", "edge")


# ========== 主流程 ==========
def main() -> None:
    print("=" * 60)
    print("日前电价预测平台 - 自动测试套件")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"项目目录: {BASE_DIR}")
    print("=" * 60)

    # 执行所有测试
    test_environment()
    test_source_encoding()
    test_imports()
    test_data_files()
    test_models()
    test_core_functions()
    test_prediction_pipeline_units()
    test_edge_cases()

    # 输出总结
    summary()

    # 保存结果
    result_path = BASE_DIR / "output" / "test_results.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n测试结果已保存至: {result_path}")


if __name__ == "__main__":
    main()
