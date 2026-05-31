"""
离线验证三种预测修正方案

用法: 在项目根目录(D:\每日工作\代码示例\预测程序-------\demo1)下运行
    python docs/validate_correction_strategies.py

输出:
    - 控制台打印各方案对比指标
    - output/correction_validation_result.json 详细结果
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dayahead_core import (
    BASE_DIR,
    DEFAULT_MODEL_ROOT,
    DEFAULT_SEGMENT_CONFIG,
    FEATURE_COLUMNS,
    LAG_PRICE_COLUMNS,
    LAG_LOAD_COLUMNS,
    NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN,
    RENEWABLE_POWER_COLUMN,
    TARGET_COLUMN,
    TOTAL_LOAD_COLUMN,
    WEIGHTED_KNN_PRICE_COLUMN,
    TrainConfig,
    assign_segments,
    attach_lag_features,
    attach_similarity_features,
    build_training_frame,
    calculate_metrics,
    clip_price_series,
    load_models,
    make_dmatrix,
    normalize_segment_config,
    predict_backend_model,
    summarize_prediction_errors,
    train_backend_model,
)


def load_validation_with_features() -> pd.DataFrame:
    """加载验证集数据，附加相似法特征和 renewable 信息"""
    print("加载模型和数据...")
    metadata, models, model_dir = load_models(DEFAULT_MODEL_ROOT)
    segment_definitions = normalize_segment_config(
        metadata.get("segment_config") or metadata.get("segments")
    )
    valid_dates = metadata.get("valid_dates", [])
    if not valid_dates:
        print("无验证集日期，使用最近训练配置")
        valid_dates = []  # will use default valid_days

    # 加载训练数据（含完整特征）
    train_config = TrainConfig(
        valid_days=metadata.get("valid_days", 14),
        training_window_days=metadata.get("training_window_days"),
        start_date=metadata.get("train_config", {}).get("start_date"),
        end_date=metadata.get("train_config", {}).get("end_date"),
    )

    history_df, skipped_sheets, _ = build_training_frame(train_config)
    history_df["segment"] = assign_segments(history_df["period"], segment_definitions)

    # 获取验证集
    if valid_dates:
        valid_df = history_df[
            pd.to_datetime(history_df["date"], errors="coerce")
            .dt.strftime("%Y-%m-%d")
            .isin(valid_dates)
        ].copy()
    else:
        unique_dates = sorted(
            pd.to_datetime(history_df["date"], errors="coerce")
            .dt.strftime("%Y-%m-%d")
            .unique()
            .tolist()
        )
        valid_dates = unique_dates[-train_config.valid_days :] if len(unique_dates) > train_config.valid_days else unique_dates
        valid_df = history_df[
            pd.to_datetime(history_df["date"], errors="coerce")
            .dt.strftime("%Y-%m-%d")
            .isin(valid_dates)
        ].copy()

    if valid_df.empty:
        raise ValueError("验证集为空，请检查数据")

    # 计算相似法特征（对整个历史数据）
    print(f"计算相似法特征（验证集 {len(valid_dates)} 天，{len(valid_df)} 条记录）...")
    full_feature_df = history_df.attrs.get("full_feature_history_df")
    if not isinstance(full_feature_df, pd.DataFrame):
        full_feature_df = history_df.copy()

    # 在验证集上使用历史数据计算相似价格
    similarity_ref_df = full_feature_df[
        ~pd.to_datetime(full_feature_df["date"], errors="coerce")
        .dt.strftime("%Y-%m-%d")
        .isin(valid_dates)
    ].copy()

    # 对验证集的每一天，用之前的历史数据计算相似价格
    from dayahead_core import nearest_similarity_price, multi_factor_knn_similarity_price, ensure_similarity_columns, normalize_knn_similarity_config

    valid_df = ensure_similarity_columns(valid_df)
    unique_valid_dates = sorted(
        pd.to_datetime(valid_df["date"], errors="coerce").dt.normalize().unique()
    )

    for current_date in unique_valid_dates:
        mask = pd.to_datetime(valid_df["date"], errors="coerce").dt.normalize() == current_date
        current_day = valid_df.loc[mask]
        # 只用当前日期之前的历史数据
        ref_dates_mask = pd.to_datetime(similarity_ref_df["date"], errors="coerce").dt.normalize() < current_date
        ref_day = similarity_ref_df[ref_dates_mask]

        if ref_day.empty or current_day.empty:
            continue

        # net_load only similarity
        similar_price, similar_gap = nearest_similarity_price(
            current_day["net_load"].to_numpy(dtype=float),
            ref_day["net_load"].to_numpy(dtype=float),
            ref_day[TARGET_COLUMN].to_numpy(dtype=float),
        )
        valid_df.loc[mask, NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN] = similar_price

        # KNN similarity
        knn_result = multi_factor_knn_similarity_price(
            current_day[["net_load", TOTAL_LOAD_COLUMN, RENEWABLE_POWER_COLUMN, "thermal_on_capacity", "period"]],
            ensure_similarity_columns(ref_day),
            k=5, max_distance=3.0, weighted_k=5, weighted_max_distance=3.0,
        )
        valid_df.loc[mask, WEIGHTED_KNN_PRICE_COLUMN] = knn_result["weighted_price"].to_numpy(dtype=float)

    # 生成 ML 模型预测
    print("生成 ML 模型预测...")
    selected_model_key = metadata.get("selected_model_key", "no_lag_96_xgboost")
    selected_segment_models = metadata.get("selected_segment_price_models") if isinstance(
        metadata.get("selected_segment_price_models"), dict
    ) else {}
    variant_meta = metadata["model_variants"][selected_model_key]
    feature_columns = variant_meta["feature_columns"]
    model_backend = variant_meta.get("model_backend", "xgboost")
    variant_models = models[selected_model_key]

    predictions = []
    for segment_name in segment_definitions:
        segment_df = valid_df[valid_df["segment"] == segment_name].copy()
        if segment_df.empty:
            continue
        model_entry = variant_models.get(segment_name)
        if model_entry is None:
            continue
        if isinstance(model_entry, dict) and "model" in model_entry:
            model_obj = model_entry["model"]
            backend = str(model_entry.get("backend", model_backend))
            pred = predict_backend_model(model_obj, backend, segment_df, feature_columns)
        else:
            pred = predict_backend_model(model_entry, model_backend, segment_df, feature_columns)
        segment_df["predicted_price"] = clip_price_series(pred)
        predictions.append(segment_df)

    result_df = pd.concat(predictions, ignore_index=True)
    result_df["predicted_price"] = pd.to_numeric(result_df["predicted_price"], errors="coerce")
    result_df[TARGET_COLUMN] = pd.to_numeric(result_df[TARGET_COLUMN], errors="coerce")
    result_df[NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN] = pd.to_numeric(
        result_df[NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN], errors="coerce"
    )
    result_df[WEIGHTED_KNN_PRICE_COLUMN] = pd.to_numeric(
        result_df[WEIGHTED_KNN_PRICE_COLUMN], errors="coerce"
    )
    result_df[RENEWABLE_POWER_COLUMN] = pd.to_numeric(
        result_df[RENEWABLE_POWER_COLUMN], errors="coerce"
    )
    result_df[TOTAL_LOAD_COLUMN] = pd.to_numeric(
        result_df[TOTAL_LOAD_COLUMN], errors="coerce"
    )
    result_df["net_load"] = pd.to_numeric(result_df["net_load"], errors="coerce")

    # 过滤有效行
    result_df = result_df.dropna(subset=[TARGET_COLUMN, "predicted_price"]).copy()

    return result_df, valid_dates


def evaluate_methods(df: pd.DataFrame) -> dict:
    """评估所有方案"""
    results = {}

    # ---- Baseline: ML 模型原始预测 ----
    results["baseline_ml"] = summarize_prediction_errors(df, "predicted_price")

    # ---- 相似法 ----
    if NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN in df.columns:
        results["similarity_net_load"] = summarize_prediction_errors(
            df.dropna(subset=[NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN]),
            NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN,
        )
    if WEIGHTED_KNN_PRICE_COLUMN in df.columns:
        results["similarity_weighted_knn"] = summarize_prediction_errors(
            df.dropna(subset=[WEIGHTED_KNN_PRICE_COLUMN]),
            WEIGHTED_KNN_PRICE_COLUMN,
        )

    actual = df[TARGET_COLUMN].to_numpy(dtype=float)
    ml_pred = df["predicted_price"].to_numpy(dtype=float)
    similarity_pred = df[NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN].to_numpy(dtype=float) if NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN in df.columns else None
    renewable = df[RENEWABLE_POWER_COLUMN].to_numpy(dtype=float) if RENEWABLE_POWER_COLUMN in df.columns else None
    total_load = df[TOTAL_LOAD_COLUMN].to_numpy(dtype=float) if TOTAL_LOAD_COLUMN in df.columns else None

    # ---- 方案 A: 基于新能源占比的条件混合 ----
    if renewable is not None and total_load is not None and similarity_pred is not None:
        renewable_ratio = np.clip(renewable / np.maximum(total_load, 1.0), 0, 1)
        # 高新能源 → 更多信任相似法；低新能源 → 更多信任 ML
        similarity_weight = np.clip(renewable_ratio * 1.5, 0.1, 0.65)
        blended_a = (1 - similarity_weight) * ml_pred + similarity_weight * similarity_pred
        df_a = df.copy()
        df_a["blended_a"] = clip_price_series(blended_a)
        results["A_conditional_blend"] = summarize_prediction_errors(df_a, "blended_a")

        # 记录不同新能源区间的表现
        results["A_by_renewable"] = {}
        for label, lo, hi in [("low_renewable", 0, 0.15), ("mid_renewable", 0.15, 0.30), ("high_renewable", 0.30, 1.0)]:
            mask = (renewable_ratio >= lo) & (renewable_ratio < hi)
            if mask.sum() > 10:
                sub = df_a.loc[df.index[mask]]
                results["A_by_renewable"][label] = {
                    "count": int(mask.sum()),
                    "blend": summarize_prediction_errors(sub, "blended_a"),
                    "baseline": summarize_prediction_errors(sub, "predicted_price"),
                }

    # ---- 方案 B: 残差修正模型（简单线性回归版本） ----
    if similarity_pred is not None and renewable is not None and total_load is not None:
        residual = actual - ml_pred
        renewable_ratio = np.clip(renewable / np.maximum(total_load, 1.0), 0, 1)
        hour = pd.to_numeric(df["hour"], errors="coerce").to_numpy(dtype=float)

        # 用一半数据训练，一半测试（时间序列按日期切分）
        unique_dates = sorted(pd.to_datetime(df["date"], errors="coerce").dt.normalize().unique())
        split_idx = len(unique_dates) // 2
        train_dates = set(unique_dates[:split_idx])
        test_dates = set(unique_dates[split_idx:])

        train_mask = np.array([pd.Timestamp(d).normalize() in train_dates for d in pd.to_datetime(df["date"], errors="coerce")])
        test_mask = np.array([pd.Timestamp(d).normalize() in test_dates for d in pd.to_datetime(df["date"], errors="coerce")])

        if train_mask.sum() > 20 and test_mask.sum() > 20:
            # 特征: renewable_ratio, hour_sin, hour_cos, net_load, ml_pred
            features_train = np.column_stack([
                renewable_ratio[train_mask],
                np.sin(2 * np.pi * hour[train_mask] / 24),
                np.cos(2 * np.pi * hour[train_mask] / 24),
                pd.to_numeric(df["net_load"], errors="coerce").to_numpy(dtype=float)[train_mask],
                ml_pred[train_mask],
            ])
            target_train = residual[train_mask]

            features_test = np.column_stack([
                renewable_ratio[test_mask],
                np.sin(2 * np.pi * hour[test_mask] / 24),
                np.cos(2 * np.pi * hour[test_mask] / 24),
                pd.to_numeric(df["net_load"], errors="coerce").to_numpy(dtype=float)[test_mask],
                ml_pred[test_mask],
            ])

            from sklearn.linear_model import Ridge
            corrector = Ridge(alpha=1.0)
            corrector.fit(features_train, target_train)
            correction_b = corrector.predict(features_test)

            df_b = df.loc[df.index[test_mask]].copy()
            df_b["corrected_b"] = clip_price_series(ml_pred[test_mask] + correction_b)
            results["B_residual_correction"] = summarize_prediction_errors(df_b, "corrected_b")
            results["B_train_samples"] = int(train_mask.sum())
            results["B_test_samples"] = int(test_mask.sum())

    # ---- 方案 C: 双向修正（基于新能源水平+相似法偏差） ----
    if similarity_pred is not None and renewable is not None:
        model_bias = ml_pred - similarity_pred  # 正=ML偏高, 负=ML偏低
        renewable_ratio = np.clip(renewable / np.maximum(total_load, 1.0), 0, 1)

        # 修正量：ML明显高于相似法 且 新能源高 → 向下修正
        #         ML明显低于相似法 且 新能源低 → 向上修正
        correction_c = np.zeros(len(df), dtype=float)
        # 向上修正：新能源低 + ML显著低于相似法
        up_mask = (renewable_ratio < 0.12) & (model_bias < -50)
        correction_c[up_mask] = np.clip(-model_bias[up_mask] * 0.4, 0, 120)
        # 向下修正：新能源高 + ML显著高于相似法
        down_mask = (renewable_ratio > 0.25) & (model_bias > 50)
        correction_c[down_mask] = np.clip(-model_bias[down_mask] * 0.4, -80, 0)

        df_c = df.copy()
        df_c["corrected_c"] = clip_price_series(ml_pred + correction_c)
        results["C_bidirectional"] = summarize_prediction_errors(df_c, "corrected_c")
        results["C_up_corrected_count"] = int(up_mask.sum())
        results["C_down_corrected_count"] = int(down_mask.sum())

    return results


def segment_analysis(df: pd.DataFrame, results: dict) -> dict:
    """分时段和分价格区间分析"""
    segment_results = {}
    for segment_name, segment_df in df.groupby("segment"):
        if len(segment_df) < 10:
            continue
        seg = {}
        seg["baseline"] = summarize_prediction_errors(segment_df, "predicted_price")
        if NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN in segment_df.columns:
            seg["similarity"] = summarize_prediction_errors(
                segment_df.dropna(subset=[NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN]),
                NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN,
            )
        segment_results[segment_name] = seg

    # 按价格区间分析
    price_bands = {"low": (0, 250), "mid": (250, 400), "high": (400, 600), "spike": (600, 1500)}
    price_results = {}
    for label, (lo, hi) in price_bands.items():
        band_df = df[(df[TARGET_COLUMN] >= lo) & (df[TARGET_COLUMN] < hi)]
        if len(band_df) < 10:
            continue
        band = {}
        band["count"] = len(band_df)
        band["baseline"] = summarize_prediction_errors(band_df, "predicted_price")
        if NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN in band_df.columns:
            band["similarity"] = summarize_prediction_errors(
                band_df.dropna(subset=[NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN]),
                NET_LOAD_ONLY_SIMILAR_PRICE_COLUMN,
            )
        if "corrected_c" in band_df.columns:
            band["bidirectional"] = summarize_prediction_errors(band_df, "corrected_c")
        price_results[label] = band

    return {"segments": segment_results, "price_bands": price_results}


def print_comparison_table(results: dict):
    """打印对比表格"""
    metric_keys = ["mae", "rmse", "bias", "over_rate", "under_rate", "direction_accuracy"]
    metric_labels = ["MAE", "RMSE", "Bias", "偏高率%", "偏低率%", "方向准确率%"]

    print("\n" + "=" * 100)
    print("方案对比")
    print("=" * 100)
    header = f"{'方案':<28}" + "".join(f"{label:>12}" for label in metric_labels)
    print(header)
    print("-" * 100)

    best = {k: float("inf") for k in metric_keys[:2]}
    best.update({k: float("-inf") if k in ["direction_accuracy"] else float("inf") for k in metric_keys[2:]})
    best_name = {k: "" for k in metric_keys}

    for name, metrics in results.items():
        if not isinstance(metrics, dict) or "mae" not in metrics:
            continue
        if metrics.get("mae") is None:
            continue
        values = [metrics.get(k) for k in metric_keys]
        row = f"{name:<28}"
        for i, (k, v) in enumerate(zip(metric_keys, values)):
            if v is None:
                row += f"{'N/A':>12}"
                continue
            row += f"{float(v):>12.4f}"
            if k in ["mae", "rmse", "bias"]:  # 越小越好
                if float(v) < best[k]:
                    best[k] = float(v)
                    best_name[k] = name
            elif k == "direction_accuracy":  # 越大越好
                if float(v) > best[k]:
                    best[k] = float(v)
                    best_name[k] = name
        print(row)

    print("-" * 100)
    best_row = f"{'Best':<28}"
    for k in metric_keys:
        best_row += f"{best_name[k]:>12}" if best_name[k] else f"{'---':>12}"
    print(best_row)
    print("=" * 100)


def main():
    print("=" * 60)
    print("预测修正方案离线验证")
    print("=" * 60)

    try:
        df, valid_dates = load_validation_with_features()
    except Exception as e:
        print(f"\n数据加载失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"\n验证数据: {len(valid_dates)} 天, {len(df)} 条记录")
    print(f"价格范围: {df[TARGET_COLUMN].min():.1f} ~ {df[TARGET_COLUMN].max():.1f}")
    print(f"日期范围: {valid_dates[0] if valid_dates else 'N/A'} ~ {valid_dates[-1] if valid_dates else 'N/A'}")

    # 评估
    results = evaluate_methods(df)

    # 分时段和价格区间分析
    detail = segment_analysis(df, results)
    results["_detail"] = detail

    # 打印对比
    print_comparison_table(results)

    # 分时段详情
    print("\n" + "=" * 80)
    print("分时段 MAE 对比")
    print("=" * 80)
    print(f"{'时段':<16}{'ML Baseline':>14}{'相似法':>14}")
    print("-" * 44)
    for seg_name, seg_data in detail["segments"].items():
        ml_mae = seg_data.get("baseline", {}).get("mae")
        sim_mae = seg_data.get("similarity", {}).get("mae")
        print(f"{seg_name:<16}{ml_mae:>14.4f}{sim_mae if sim_mae else 'N/A':>14}")

    # 价格区间详情
    print("\n" + "=" * 80)
    print("分价格区间 MAE 对比")
    print("=" * 80)
    print(f"{'价格区间':<16}{'数量':>8}{'ML Baseline':>14}{'相似法':>14}")
    print("-" * 52)
    for label, band in detail["price_bands"].items():
        ml_mae = band.get("baseline", {}).get("mae")
        sim_mae = band.get("similarity", {}).get("mae")
        count = band.get("count", 0)
        print(f"{label:<16}{count:>8}{ml_mae:>14.4f}{sim_mae if sim_mae else 'N/A':>14}")

    # 保存详细结果
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "correction_validation_result.json"

    def make_serializable(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {str(k): make_serializable(v) for k, v in obj.items()}
        return obj

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(make_serializable(results), f, ensure_ascii=False, indent=2)

    print(f"\n详细结果已保存到: {output_path}")


if __name__ == "__main__":
    main()
