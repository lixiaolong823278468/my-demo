from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_PRICE_INTERVALS: list[dict[str, float | str | None]] = [
    {"label": "0-250", "min": 0.0, "max": 250.0},
    {"label": "250-300", "min": 250.0, "max": 300.0},
    {"label": "300-400", "min": 300.0, "max": 400.0},
    {"label": "400-600", "min": 400.0, "max": 600.0},
    {"label": "600-1000", "min": 600.0, "max": 1000.0},
    {"label": "1000-1500", "min": 1000.0, "max": 1500.0},
]
PRICE_INTERVAL_MIN = 0.0
PRICE_INTERVAL_MAX = 1500.0


@dataclass
class IntervalModelBundle:
    metadata: dict[str, Any]
    models: dict[str, Any]


@dataclass
class IntervalPredictionResult:
    labels: list[str]
    probabilities: np.ndarray
    interval_probability: list[float]
    high_price_probability: list[float]
    extreme_price_probability: list[float]
    backtest_accuracy: list[float | None]


def normalize_price_intervals(
    intervals: list[dict[str, Any]] | None,
    *,
    allow_legacy_open_bounds: bool = False,
) -> list[dict[str, float | str | None]]:
    raw_intervals = intervals if intervals else DEFAULT_PRICE_INTERVALS
    normalized: list[dict[str, float | str | None]] = []
    previous_max: float | None = None
    for index, item in enumerate(raw_intervals):
        if not isinstance(item, dict):
            raise ValueError("价格区间配置必须是对象列表")
        lower = item.get("min")
        upper = item.get("max")
        lower_value = None if lower is None or lower == "" else float(lower)
        upper_value = None if upper is None or upper == "" else float(upper)
        if index == 0 and lower_value is None and allow_legacy_open_bounds:
            lower_value = PRICE_INTERVAL_MIN
        if index == len(raw_intervals) - 1 and upper_value is None and allow_legacy_open_bounds:
            upper_value = PRICE_INTERVAL_MAX
        if index == 0 and lower_value != PRICE_INTERVAL_MIN:
            raise ValueError("第一个价格区间下限必须为 0")
        if index == len(raw_intervals) - 1 and upper_value != PRICE_INTERVAL_MAX:
            raise ValueError("最后一个价格区间上限必须为 1500")
        if lower_value is not None and previous_max is not None and abs(lower_value - previous_max) > 1e-9:
            raise ValueError("价格区间必须首尾连续")
        if lower_value is not None and upper_value is not None and lower_value >= upper_value:
            raise ValueError("价格区间上限必须大于下限")
        label = interval_label_text(lower_value, upper_value)
        normalized.append({"label": label, "min": lower_value, "max": upper_value})
        previous_max = upper_value
    if len(normalized) < 2:
        raise ValueError("价格区间数量至少为 2")
    return normalized


def interval_label_text(lower: float | None, upper: float | None) -> str:
    if lower is None and upper is not None:
        return f"<{format_interval_number(upper)}"
    if lower is not None and upper is None:
        return f">{format_interval_number(lower)}"
    return f"{format_interval_number(lower)}-{format_interval_number(upper)}"


def format_interval_number(value: float | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return str(round(float(value), 4)).rstrip("0").rstrip(".")


def interval_label_for_price(price: float, intervals: list[dict[str, Any]]) -> str:
    value = float(price)
    for index, item in enumerate(intervals):
        lower = item.get("min")
        upper = item.get("max")
        lower_ok = lower is None or value >= float(lower)
        upper_ok = upper is None or value < float(upper) or (index == len(intervals) - 1 and value <= float(upper))
        if lower_ok and upper_ok:
            return str(item["label"])
    raise ValueError(f"价格 {value} 超出价格区间范围")


def interval_index_for_price(price: float, intervals: list[dict[str, Any]]) -> int:
    label = interval_label_for_price(price, intervals)
    return interval_labels(intervals).index(label)


def interval_labels(intervals: list[dict[str, Any]]) -> list[str]:
    return [str(item["label"]) for item in intervals]


def label_prices(prices: pd.Series, intervals: list[dict[str, Any]]) -> pd.Series:
    return pd.to_numeric(prices, errors="coerce").map(lambda value: interval_label_for_price(value, intervals) if pd.notna(value) else None)


def score_interval_metrics(metrics: dict[str, float | int | None]) -> float:
    interval_accuracy = float(metrics.get("interval_accuracy") or 0.0)
    top2_accuracy = float(metrics.get("top2_accuracy") or 0.0)
    log_loss = float(metrics.get("log_loss") or 0.0)
    high_price_recall = float(metrics.get("high_price_recall") or 0.0)
    return -interval_accuracy - 0.5 * top2_accuracy + 0.3 * log_loss - 0.5 * high_price_recall


def compute_interval_metrics(
    actual_labels: list[str] | pd.Series,
    probabilities: np.ndarray,
    intervals: list[dict[str, Any]],
) -> dict[str, float | int | None]:
    labels = interval_labels(intervals)
    actual = [str(item) for item in actual_labels]
    if len(actual) == 0 or probabilities.size == 0:
        return {
            "rows": 0,
            "interval_accuracy": None,
            "top2_accuracy": None,
            "log_loss": None,
            "high_price_recall": None,
            "low_price_recall": None,
            "score": None,
        }
    probabilities = normalize_probability_matrix(probabilities, len(labels))
    actual_indices = np.array([labels.index(label) if label in labels else -1 for label in actual], dtype=int)
    valid_mask = actual_indices >= 0
    if not np.any(valid_mask):
        return {"rows": len(actual), "interval_accuracy": None, "top2_accuracy": None, "log_loss": None, "high_price_recall": None, "low_price_recall": None, "score": None}
    actual_indices = actual_indices[valid_mask]
    probabilities = probabilities[valid_mask]
    top1 = np.argmax(probabilities, axis=1)
    top2 = np.argsort(probabilities, axis=1)[:, -2:]
    clipped = np.clip(probabilities[np.arange(len(actual_indices)), actual_indices], 1e-12, 1.0)
    metrics: dict[str, float | int | None] = {
        "rows": int(len(actual_indices)),
        "interval_accuracy": float(np.mean(top1 == actual_indices)),
        "top2_accuracy": float(np.mean([actual_indices[index] in top2[index] for index in range(len(actual_indices))])),
        "log_loss": float(-np.mean(np.log(clipped))),
        "high_price_recall": recall_for_group(actual_indices, top1, high_price_indices(intervals)),
        "low_price_recall": recall_for_group(actual_indices, top1, low_price_indices(intervals)),
    }
    metrics["score"] = float(score_interval_metrics(metrics))
    return metrics


def recall_for_group(actual_indices: np.ndarray, predicted_indices: np.ndarray, group_indices: set[int]) -> float | None:
    if not group_indices:
        return None
    actual_mask = np.array([index in group_indices for index in actual_indices], dtype=bool)
    if not np.any(actual_mask):
        return None
    predicted_mask = np.array([index in group_indices for index in predicted_indices], dtype=bool)
    return float(np.mean(predicted_mask[actual_mask]))


def high_price_indices(intervals: list[dict[str, Any]]) -> set[int]:
    indices: set[int] = set()
    for index, item in enumerate(intervals):
        lower = item.get("min")
        upper = item.get("max")
        if (lower is not None and float(lower) >= 600.0) or (upper is None and lower is not None and float(lower) >= 1000.0):
            indices.add(index)
    return indices


def low_price_indices(intervals: list[dict[str, Any]]) -> set[int]:
    return {index for index, item in enumerate(intervals) if item.get("max") is not None and float(item["max"]) <= 250.0}


def extreme_price_indices(intervals: list[dict[str, Any]]) -> set[int]:
    return {index for index, item in enumerate(intervals) if item.get("min") is not None and float(item["min"]) >= 1000.0}


def normalize_probability_matrix(probabilities: np.ndarray, class_count: int) -> np.ndarray:
    array = np.asarray(probabilities, dtype=float)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if array.shape[1] != class_count:
        fixed = np.zeros((array.shape[0], class_count), dtype=float)
        fixed[:, : min(class_count, array.shape[1])] = array[:, : min(class_count, array.shape[1])]
        array = fixed
    row_sums = array.sum(axis=1)
    row_sums[row_sums == 0] = 1.0
    return array / row_sums[:, None]


def split_train_valid_by_date(frame: pd.DataFrame, valid_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    unique_dates = sorted(pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d").unique().tolist())
    if valid_days > 0 and len(unique_dates) > valid_days:
        valid_dates = set(unique_dates[-valid_days:])
        valid_df = frame[pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d").isin(valid_dates)].copy()
        train_df = frame[~pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d").isin(valid_dates)].copy()
        return train_df, valid_df
    return frame.copy(), frame.iloc[0:0].copy()


def available_interval_backends() -> dict[str, str]:
    backends = {"xgboost": "XGBoost"}
    try:
        import lightgbm  # noqa: F401

        backends["lightgbm"] = "LightGBM"
    except Exception:
        pass
    try:
        import catboost  # noqa: F401

        backends["catboost"] = "CatBoost"
    except Exception:
        pass
    return backends


def interval_model_file_name(segment_name: str, backend: str) -> str:
    if backend == "lightgbm":
        return f"{segment_name}.txt"
    if backend == "catboost":
        return f"{segment_name}.cbm"
    return f"{segment_name}.json"


def train_interval_backend(
    backend: str,
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    feature_columns: list[str],
    label_column: str,
    class_count: int,
    num_boost_round: int,
    output_path: Path,
) -> tuple[Any, np.ndarray | None, int | None]:
    train_x = train_df[feature_columns].astype(float)
    train_y = train_df[label_column].astype(int)
    valid_x = valid_df[feature_columns].astype(float) if not valid_df.empty else None

    if backend == "lightgbm":
        import lightgbm as lgb

        train_dataset = lgb.Dataset(train_x, label=train_y, feature_name=feature_columns)
        valid_sets = [train_dataset]
        callbacks = []
        if valid_x is not None:
            valid_sets.append(lgb.Dataset(valid_x, label=valid_df[label_column].astype(int), reference=train_dataset, feature_name=feature_columns))
            callbacks.append(lgb.early_stopping(30, verbose=False))
        model = lgb.train(
            {
                "objective": "multiclass",
                "num_class": class_count,
                "metric": "multi_logloss",
                "learning_rate": 0.05,
                "max_depth": 5,
                "seed": 42,
                "verbosity": -1,
            },
            train_dataset,
            num_boost_round=num_boost_round,
            valid_sets=valid_sets,
            callbacks=callbacks,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(model.model_to_string(), encoding="utf-8")
        best_iteration = int(model.best_iteration) if getattr(model, "best_iteration", 0) else None
        prediction = model.predict(valid_x, num_iteration=best_iteration) if valid_x is not None else None
        return model, prediction, best_iteration

    if backend == "catboost":
        from catboost import CatBoostClassifier

        model = CatBoostClassifier(
            iterations=num_boost_round,
            learning_rate=0.05,
            depth=5,
            loss_function="MultiClass",
            random_seed=42,
            verbose=False,
            allow_writing_files=False,
        )
        fit_kwargs: dict[str, Any] = {}
        if valid_x is not None:
            fit_kwargs["eval_set"] = (valid_x, valid_df[label_column].astype(int))
            fit_kwargs["early_stopping_rounds"] = 30
            fit_kwargs["use_best_model"] = True
        model.fit(train_x, train_y, **fit_kwargs)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(str(output_path))
        best_iteration = int(model.get_best_iteration()) if model.get_best_iteration() is not None else None
        prediction = model.predict_proba(valid_x) if valid_x is not None else None
        return model, prediction, best_iteration

    import xgboost as xgb

    dtrain = xgb.DMatrix(train_x, label=train_y, feature_names=feature_columns)
    params = {
        "objective": "multi:softprob",
        "num_class": class_count,
        "eval_metric": "mlogloss",
        "eta": 0.05,
        "max_depth": 5,
        "min_child_weight": 1,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "seed": 42,
    }
    evals = [(dtrain, "train")]
    train_kwargs: dict[str, Any] = {"params": params, "dtrain": dtrain, "num_boost_round": num_boost_round, "evals": evals, "verbose_eval": False}
    dvalid = None
    if valid_x is not None:
        dvalid = xgb.DMatrix(valid_x, label=valid_df[label_column].astype(int), feature_names=feature_columns)
        evals.append((dvalid, "valid"))
        train_kwargs["early_stopping_rounds"] = 30
    model = xgb.train(**train_kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(output_path))
    best_iteration = int(model.attr("best_iteration")) if model.attr("best_iteration") else None
    prediction = None
    if dvalid is not None:
        iteration_range = (0, best_iteration + 1) if best_iteration is not None else None
        prediction = model.predict(dvalid, iteration_range=iteration_range) if iteration_range else model.predict(dvalid)
    return model, prediction, best_iteration


def train_interval_models(
    frame: pd.DataFrame,
    target_column: str,
    feature_columns: list[str],
    segment_config: list[dict[str, Any]],
    output_dir: Path,
    intervals: list[dict[str, Any]] | None = None,
    valid_days: int = 14,
    num_boost_round: int = 400,
    backends: dict[str, str] | None = None,
) -> dict[str, Any]:
    intervals = normalize_price_intervals(intervals)
    labels = interval_labels(intervals)
    class_count = len(labels)
    training_frame = frame.dropna(subset=[target_column]).copy()
    training_frame["interval_label"] = label_prices(training_frame[target_column], intervals)
    training_frame["interval_label_id"] = training_frame["interval_label"].map({label: index for index, label in enumerate(labels)}).astype(int)
    backends = backends or available_interval_backends()
    output_dir.mkdir(parents=True, exist_ok=True)
    variant_metrics: dict[str, dict[str, Any]] = {}
    model_variants: dict[str, dict[str, Any]] = {}
    segment_names = [str(item["name"]) for item in segment_config]

    for backend_key, backend_label in backends.items():
        variant_key = f"interval_{backend_key}"
        variant_dir = output_dir / variant_key
        all_actual: list[str] = []
        all_probabilities: list[np.ndarray] = []
        segment_metrics: dict[str, dict[str, Any]] = {}
        try:
            for segment_name in segment_names:
                segment_df = training_frame[training_frame["segment"] == segment_name].copy()
                if segment_df.empty:
                    continue
                train_df, valid_df = split_train_valid_by_date(segment_df, valid_days)
                model_path = variant_dir / interval_model_file_name(segment_name, backend_key)
                _, valid_probabilities, best_iteration = train_interval_backend(
                    backend_key,
                    train_df,
                    valid_df,
                    feature_columns,
                    "interval_label_id",
                    class_count,
                    num_boost_round,
                    model_path,
                )
                metrics: dict[str, Any] = {"train_rows": int(len(train_df)), "valid_rows": int(len(valid_df)), "best_iteration": best_iteration}
                if valid_probabilities is not None and not valid_df.empty:
                    valid_probabilities = normalize_probability_matrix(valid_probabilities, class_count)
                    metrics.update(compute_interval_metrics(valid_df["interval_label"].astype(str).tolist(), valid_probabilities, intervals))
                    all_actual.extend(valid_df["interval_label"].astype(str).tolist())
                    all_probabilities.append(valid_probabilities)
                segment_metrics[segment_name] = metrics
        except Exception as exc:
            variant_metrics[variant_key] = {"overall": {"rows": 0, "score": None, "error": str(exc)}, "segments": segment_metrics}
            continue
        if all_probabilities:
            overall_probabilities = np.vstack(all_probabilities)
            overall_metrics = compute_interval_metrics(all_actual, overall_probabilities, intervals)
        else:
            overall_metrics = {"rows": 0, "interval_accuracy": None, "top2_accuracy": None, "log_loss": None, "high_price_recall": None, "low_price_recall": None, "score": None}
        variant_metrics[variant_key] = {"overall": overall_metrics, "segments": segment_metrics}
        model_variants[variant_key] = {
            "model_dir": variant_key,
            "model_backend": backend_key,
            "model_backend_label": backend_label,
            "feature_columns": feature_columns,
        }

    if not model_variants:
        raise RuntimeError("没有可用的价格区间分类模型后端")
    selected_model_key = min(
        model_variants,
        key=lambda key: (float(variant_metrics[key]["overall"].get("score")) if variant_metrics[key]["overall"].get("score") is not None else float("inf"), key),
    )
    selected_segment_models = select_interval_segment_models(model_variants, variant_metrics, segment_names)
    return {
        "enabled": True,
        "intervals": intervals,
        "labels": labels,
        "target_column": target_column,
        "feature_columns": feature_columns,
        "selected_model_key": selected_model_key,
        "selected_segment_models": selected_segment_models,
        "selected_model_backend": model_variants[selected_model_key]["model_backend"],
        "selected_model_backend_label": model_variants[selected_model_key]["model_backend_label"],
        "model_variants": model_variants,
        "variant_metrics": variant_metrics,
        "metrics": variant_metrics[selected_model_key],
        "overall_accuracy": variant_metrics[selected_model_key]["overall"].get("interval_accuracy"),
    }


def select_interval_segment_models(
    model_variants: dict[str, dict[str, Any]],
    variant_metrics: dict[str, dict[str, Any]],
    segment_names: list[str],
) -> dict[str, str]:
    selected: dict[str, str] = {}
    for segment_name in segment_names:
        candidates = []
        for variant_key in model_variants:
            score = variant_metrics.get(variant_key, {}).get("segments", {}).get(segment_name, {}).get("score")
            if score is not None:
                candidates.append((float(score), variant_key))
        if candidates:
            selected[segment_name] = min(candidates)[1]
            continue
        fallback_candidates = []
        for variant_key in model_variants:
            score = variant_metrics.get(variant_key, {}).get("overall", {}).get("score")
            if score is not None:
                fallback_candidates.append((float(score), variant_key))
        if fallback_candidates:
            selected[segment_name] = min(fallback_candidates)[1]
    return selected


def load_interval_backend_model(model_path: Path, backend: str):
    if backend == "lightgbm":
        import lightgbm as lgb

        return lgb.Booster(model_str=model_path.read_text(encoding="utf-8"))
    if backend == "catboost":
        from catboost import CatBoostClassifier

        model = CatBoostClassifier()
        model.load_model(str(model_path))
        return model
    import xgboost as xgb

    model = xgb.Booster()
    model.load_model(str(model_path))
    return model


def load_interval_model_bundle(model_dir: Path, metadata: dict[str, Any] | None) -> IntervalModelBundle | None:
    if not metadata or not metadata.get("enabled"):
        return None
    default_selected_key = str(metadata["selected_model_key"])
    selected_segment_models = metadata.get("selected_segment_models") if isinstance(metadata.get("selected_segment_models"), dict) else {}
    models: dict[str, Any] = {}
    for segment_name in metadata.get("metrics", {}).get("segments", {}):
        selected_key = str(selected_segment_models.get(segment_name) or default_selected_key)
        variant = metadata["model_variants"][selected_key]
        backend = str(variant.get("model_backend") or "xgboost")
        variant_dir = model_dir / str(variant.get("model_dir", selected_key))
        model_path = variant_dir / interval_model_file_name(segment_name, backend)
        if model_path.exists():
            models[segment_name] = {"backend": backend, "model": load_interval_backend_model(model_path, backend)}
    return IntervalModelBundle(metadata=metadata, models=models)


def predict_interval_probabilities(frame: pd.DataFrame, bundle: IntervalModelBundle | None) -> IntervalPredictionResult:
    if bundle is None:
        row_count = len(frame)
        return IntervalPredictionResult([""] * row_count, np.zeros((row_count, 0)), [0.0] * row_count, [0.0] * row_count, [0.0] * row_count, [None] * row_count)
    metadata = bundle.metadata
    intervals = normalize_price_intervals(metadata.get("intervals"))
    labels = interval_labels(intervals)
    class_count = len(labels)
    feature_columns = list(metadata.get("feature_columns") or [])
    probabilities = np.zeros((len(frame), class_count), dtype=float)
    predicted_labels = [""] * len(frame)
    interval_probability = [0.0] * len(frame)
    high_indices = high_price_indices(intervals)
    extreme_indices = extreme_price_indices(intervals)
    high_probability = [0.0] * len(frame)
    extreme_probability = [0.0] * len(frame)
    backtest_accuracy: list[float | None] = [metadata.get("overall_accuracy")] * len(frame)
    for segment_name, model_item in bundle.models.items():
        mask = frame["segment"].astype(str) == segment_name
        if not mask.any():
            continue
        segment_frame = frame.loc[mask]
        segment_probabilities = predict_interval_backend(segment_frame, model_item["model"], model_item["backend"], feature_columns, class_count)
        row_indices = np.where(mask.to_numpy())[0]
        probabilities[row_indices, :] = segment_probabilities
        top_indices = np.argmax(segment_probabilities, axis=1)
        segment_accuracy = metadata.get("metrics", {}).get("segments", {}).get(segment_name, {}).get("interval_accuracy", metadata.get("overall_accuracy"))
        for offset, row_index in enumerate(row_indices):
            predicted_labels[row_index] = labels[int(top_indices[offset])]
            interval_probability[row_index] = float(segment_probabilities[offset, int(top_indices[offset])])
            high_probability[row_index] = float(segment_probabilities[offset, list(high_indices)].sum()) if high_indices else 0.0
            extreme_probability[row_index] = float(segment_probabilities[offset, list(extreme_indices)].sum()) if extreme_indices else 0.0
            backtest_accuracy[row_index] = segment_accuracy
    return IntervalPredictionResult(predicted_labels, probabilities, interval_probability, high_probability, extreme_probability, backtest_accuracy)


def predict_interval_backend(frame: pd.DataFrame, model: Any, backend: str, feature_columns: list[str], class_count: int) -> np.ndarray:
    feature_frame = frame[feature_columns].astype(float)
    if backend == "lightgbm":
        return normalize_probability_matrix(model.predict(feature_frame), class_count)
    if backend == "catboost":
        return normalize_probability_matrix(model.predict_proba(feature_frame), class_count)
    import xgboost as xgb

    dmatrix = xgb.DMatrix(feature_frame, feature_names=feature_columns)
    return normalize_probability_matrix(model.predict(dmatrix), class_count)


def price_interval_consistency(price: float, predicted_interval: str, intervals: list[dict[str, Any]]) -> str:
    if not predicted_interval:
        return ""
    actual_label = interval_label_for_price(float(price), intervals)
    if actual_label == predicted_interval:
        return "一致"
    labels = interval_labels(intervals)
    if labels.index(actual_label) < labels.index(predicted_interval):
        return "偏低"
    return "偏高"


def append_interval_prediction_columns(frame: pd.DataFrame, result: IntervalPredictionResult, intervals: list[dict[str, Any]], price_column: str = "predicted_price") -> pd.DataFrame:
    output = frame.copy()
    output["predicted_interval"] = result.labels
    output["predicted_interval_probability"] = [round(value, 6) for value in result.interval_probability]
    output["interval_probabilities"] = [json.dumps(dict(zip(interval_labels(intervals), row)), ensure_ascii=False) for row in result.probabilities.tolist()]
    output["high_price_probability"] = [round(value, 6) for value in result.high_price_probability]
    output["extreme_price_probability"] = [round(value, 6) for value in result.extreme_price_probability]
    output["interval_backtest_accuracy"] = [None if value is None else round(float(value), 6) for value in result.backtest_accuracy]
    output["price_interval_consistency"] = [
        price_interval_consistency(price, label, intervals) if pd.notna(price) else ""
        for price, label in zip(output[price_column], result.labels)
    ]
    return output
