from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
except ModuleNotFoundError:
    GradientBoostingRegressor = None
    DecisionTreeClassifier = None
    DecisionTreeRegressor = None


ACTUAL_PRICE_COLUMN = "\u65e5\u524d\u51fa\u6e05\u4ef7\u683c(\u5143/MWh)"
DEFAULT_TARGET_DATES = ("2026-05-17", "2026-05-18")
MODEL_NUMERIC_FEATURES = (
    "predicted",
    "period",
    "hour",
    "total_load",
    "net_load",
    "renewable_power",
    "thermal_space_load_ratio",
    "thermal_on_capacity",
    "net_load_only_similar_price",
    "knn_similar_price",
    "weighted_knn_regression_price",
    "high_price_probability",
    "extreme_price_probability",
    "interval_backtest_accuracy",
)
MODEL_CATEGORICAL_FEATURES = ("segment", "day_type", "predicted_interval_by_price")


@dataclass(frozen=True)
class ResidualCorrections:
    overall_mean: float
    overall_median: float
    segment_mean: dict[str, float]
    segment_median: dict[str, float]
    segment_interval_mean: dict[tuple[str, str], float]
    predicted_interval_mean: dict[str, float]
    high400_mean: float
    high600_mean: float


def price_interval_label(price: float | int | None) -> str | None:
    if price is None or pd.isna(price):
        return None
    value = float(price)
    if value < 250:
        return "0-250"
    if value < 300:
        return "250-300"
    if value < 400:
        return "300-400"
    if value < 600:
        return "400-600"
    if value < 1000:
        return "600-1000"
    return "1000-1500"


def compute_error_metrics(
    frame: pd.DataFrame,
    *,
    actual_col: str = "actual",
    predicted_col: str = "predicted",
) -> dict[str, float | int]:
    values = frame[[actual_col, predicted_col]].apply(pd.to_numeric, errors="coerce").dropna()
    if values.empty:
        return {
            "rows": 0,
            "mae": math.nan,
            "rmse": math.nan,
            "bias": math.nan,
            "p90_abs_error": math.nan,
            "max_abs_error": math.nan,
            "over_rate": math.nan,
            "under_rate": math.nan,
        }

    error = values[predicted_col] - values[actual_col]
    abs_error = error.abs()
    return {
        "rows": int(len(values)),
        "mae": float(abs_error.mean()),
        "rmse": float(np.sqrt((error**2).mean())),
        "bias": float(error.mean()),
        "p90_abs_error": float(abs_error.quantile(0.9)),
        "max_abs_error": float(abs_error.max()),
        "over_rate": float((error > 0).mean() * 100),
        "under_rate": float((error < 0).mean() * 100),
    }


def _as_float_dict(series: pd.Series) -> dict:
    return {key: float(value) for key, value in series.dropna().items()}


def learn_residual_corrections(
    validation_frame: pd.DataFrame,
    *,
    actual_col: str = "actual",
    predicted_col: str = "predicted",
) -> ResidualCorrections:
    frame = validation_frame.copy()
    frame[actual_col] = pd.to_numeric(frame[actual_col], errors="coerce")
    frame[predicted_col] = pd.to_numeric(frame[predicted_col], errors="coerce")
    frame = frame.dropna(subset=[actual_col, predicted_col])
    if frame.empty:
        raise ValueError("validation_frame has no comparable actual/predicted rows")

    frame["residual"] = frame[actual_col] - frame[predicted_col]
    frame["predicted_interval_by_price"] = frame[predicted_col].map(price_interval_label)
    high400 = frame.loc[frame[actual_col] >= 400, "residual"]
    high600 = frame.loc[frame[actual_col] >= 600, "residual"]

    return ResidualCorrections(
        overall_mean=float(frame["residual"].mean()),
        overall_median=float(frame["residual"].median()),
        segment_mean=_as_float_dict(frame.groupby("segment")["residual"].mean()),
        segment_median=_as_float_dict(frame.groupby("segment")["residual"].median()),
        segment_interval_mean=_as_float_dict(frame.groupby(["segment", "predicted_interval_by_price"])["residual"].mean()),
        predicted_interval_mean=_as_float_dict(frame.groupby("predicted_interval_by_price")["residual"].mean()),
        high400_mean=float(high400.mean()) if not high400.empty else 0.0,
        high600_mean=float(high600.mean()) if not high600.empty else 0.0,
    )


def apply_residual_correction(
    frame: pd.DataFrame,
    corrections: ResidualCorrections,
    *,
    predicted_col: str = "predicted",
) -> pd.Series:
    def offset(row: pd.Series) -> float:
        interval = price_interval_label(row[predicted_col])
        specific = corrections.segment_interval_mean.get((str(row.get("segment")), str(interval)))
        if specific is not None:
            return specific
        segment_value = corrections.segment_mean.get(str(row.get("segment")))
        if segment_value is not None:
            return segment_value
        interval_value = corrections.predicted_interval_mean.get(str(interval))
        if interval_value is not None:
            return interval_value
        return corrections.overall_mean

    predicted = pd.to_numeric(frame[predicted_col], errors="coerce")
    return predicted + frame.apply(offset, axis=1)


def apply_late_peak_high_uplift(
    frame: pd.DataFrame,
    corrections: ResidualCorrections,
    *,
    predicted_col: str = "predicted",
    base_predictions: pd.Series | None = None,
    segment: str = "segment_5",
    threshold: float = 400.0,
    multiplier: float = 0.5,
    high_residual: str = "high600_mean",
) -> pd.Series:
    residual = getattr(corrections, high_residual)
    predicted = pd.to_numeric(frame[predicted_col], errors="coerce")
    base = pd.to_numeric(base_predictions, errors="coerce") if base_predictions is not None else predicted
    mask = (frame["segment"].astype(str) == segment) & (predicted >= threshold)
    return base + mask.astype(float) * residual * multiplier


def _net_load_similarity_series(
    frame: pd.DataFrame,
    *,
    predicted_col: str = "predicted",
    similarity_col: str = "net_load_only_similar_price",
) -> pd.Series | None:
    if similarity_col not in frame.columns:
        return None
    predicted = pd.to_numeric(frame[predicted_col], errors="coerce")
    similar = pd.to_numeric(frame[similarity_col], errors="coerce")
    return similar.where(similar.notna(), predicted)


def apply_fixed_similarity_blend(
    frame: pd.DataFrame,
    *,
    predicted_col: str = "predicted",
    similarity_col: str = "net_load_only_similar_price",
    similarity_weight: float = 0.5,
) -> pd.Series:
    predicted = pd.to_numeric(frame[predicted_col], errors="coerce")
    similar = _net_load_similarity_series(frame, predicted_col=predicted_col, similarity_col=similarity_col)
    if similar is None:
        return predicted
    weight = float(np.clip(similarity_weight, 0.0, 1.0))
    return predicted * (1.0 - weight) + similar * weight


def apply_scenario_similarity_blend(
    frame: pd.DataFrame,
    *,
    predicted_col: str = "predicted",
    similarity_col: str = "net_load_only_similar_price",
    min_downward_gap: float = 50.0,
) -> pd.Series:
    predicted = pd.to_numeric(frame[predicted_col], errors="coerce")
    similar = _net_load_similarity_series(frame, predicted_col=predicted_col, similarity_col=similarity_col)
    if similar is None:
        return predicted

    total_load = pd.to_numeric(frame.get("total_load"), errors="coerce")
    renewable_power = pd.to_numeric(frame.get("renewable_power"), errors="coerce")
    net_load = pd.to_numeric(frame.get("net_load"), errors="coerce")
    renewable_ratio = (renewable_power / total_load.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    renewable_trigger = pd.Series(False, index=frame.index)
    net_load_trigger = pd.Series(False, index=frame.index)
    groups = frame.groupby("forecast_date").groups if "forecast_date" in frame.columns else {None: frame.index}
    for index in groups.values():
        group_ratio = renewable_ratio.loc[index]
        group_net_load = net_load.loc[index]
        if group_ratio.notna().any():
            renewable_threshold = max(0.18, float(group_ratio.quantile(0.60)))
            renewable_trigger.loc[index] = group_ratio >= renewable_threshold
        if group_net_load.notna().any():
            net_load_trigger.loc[index] = group_net_load <= float(group_net_load.quantile(0.40))

    model_minus_similarity = predicted - similar
    downward_mask = (model_minus_similarity >= min_downward_gap) & renewable_trigger & (
        net_load_trigger | (renewable_ratio >= 0.25)
    )

    gap_weight = ((model_minus_similarity - min_downward_gap) / 200.0).clip(0.0, 0.25)
    similarity_weight = (0.45 + (renewable_ratio - 0.18).clip(lower=0.0) * 0.75 + gap_weight).clip(0.0, 0.85)
    similarity_weight = similarity_weight.where(downward_mask, 0.0)
    return predicted * (1.0 - similarity_weight) + similar * similarity_weight


def compare_strategies(
    test_frame: pd.DataFrame,
    validation_frame: pd.DataFrame,
    *,
    actual_col: str = "actual",
    predicted_col: str = "predicted",
) -> pd.DataFrame:
    strategies = build_strategy_predictions(test_frame, validation_frame, predicted_col=predicted_col)

    rows = []
    for name, predicted in strategies.items():
        scored = test_frame.copy()
        scored["_strategy_prediction"] = predicted
        overall = compute_error_metrics(scored, actual_col=actual_col, predicted_col="_strategy_prediction")
        high400 = compute_error_metrics(
            scored.loc[pd.to_numeric(scored[actual_col], errors="coerce") >= 400],
            actual_col=actual_col,
            predicted_col="_strategy_prediction",
        )
        high600 = compute_error_metrics(
            scored.loc[pd.to_numeric(scored[actual_col], errors="coerce") >= 600],
            actual_col=actual_col,
            predicted_col="_strategy_prediction",
        )
        rows.append(
            {
                "strategy": name,
                "rows": overall["rows"],
                "mae": overall["mae"],
                "rmse": overall["rmse"],
                "bias": overall["bias"],
                "p90_abs_error": overall["p90_abs_error"],
                "max_abs_error": overall["max_abs_error"],
                "high400_mae": high400["mae"],
                "high600_mae": high600["mae"],
                "high600_under_rate": high600["under_rate"],
            }
        )
    return pd.DataFrame(rows).sort_values("mae").reset_index(drop=True)


def _prepare_model_features(
    train_frame: pd.DataFrame,
    forecast_frame: pd.DataFrame,
    *,
    predicted_col: str = "predicted",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = train_frame.copy()
    forecast = forecast_frame.copy()
    for frame in (train, forecast):
        if predicted_col != "predicted":
            frame["predicted"] = pd.to_numeric(frame[predicted_col], errors="coerce")
        frame["predicted_interval_by_price"] = frame["predicted"].map(price_interval_label)

    for column in MODEL_NUMERIC_FEATURES:
        if column not in train.columns:
            train[column] = 0.0
        if column not in forecast.columns:
            forecast[column] = 0.0
        train[column] = pd.to_numeric(train[column], errors="coerce")
        forecast[column] = pd.to_numeric(forecast[column], errors="coerce")
        fill_value = float(train[column].median()) if train[column].notna().any() else 0.0
        train[column] = train[column].fillna(fill_value)
        forecast[column] = forecast[column].fillna(fill_value)

    for column in MODEL_CATEGORICAL_FEATURES:
        if column not in train.columns:
            train[column] = "unknown"
        if column not in forecast.columns:
            forecast[column] = "unknown"
        train[column] = train[column].astype(str).fillna("unknown")
        forecast[column] = forecast[column].astype(str).fillna("unknown")

    train_x = pd.get_dummies(train[list(MODEL_NUMERIC_FEATURES) + list(MODEL_CATEGORICAL_FEATURES)], dtype=float)
    forecast_x = pd.get_dummies(forecast[list(MODEL_NUMERIC_FEATURES) + list(MODEL_CATEGORICAL_FEATURES)], dtype=float)
    train_x, forecast_x = train_x.align(forecast_x, join="outer", axis=1, fill_value=0.0)
    return train_x, forecast_x


def predict_high_classifier_regressor(
    validation_frame: pd.DataFrame,
    forecast_frame: pd.DataFrame,
    *,
    actual_col: str = "actual",
    predicted_col: str = "predicted",
    high_threshold: float = 600.0,
    activation_probability: float = 0.35,
) -> pd.DataFrame:
    train = validation_frame.dropna(subset=[actual_col, predicted_col]).copy()
    if train.empty:
        raise ValueError("validation_frame has no comparable rows")
    forecast = forecast_frame.copy()
    if DecisionTreeClassifier is None or DecisionTreeRegressor is None:
        y_high = (pd.to_numeric(train[actual_col], errors="coerce") >= high_threshold).astype(int)
        segment_rate = y_high.groupby(train.get("segment", pd.Series("unknown", index=train.index)).astype(str)).mean()
        overall_rate = float(y_high.mean()) if len(y_high) else 0.0
        forecast_segment = forecast.get("segment", pd.Series("unknown", index=forecast.index)).astype(str)
        probability = forecast_segment.map(segment_rate).fillna(overall_rate).astype(float)

        high_rows = train.loc[y_high == 1].copy()
        baseline = pd.to_numeric(forecast[predicted_col], errors="coerce")
        if high_rows.empty:
            high_prediction = baseline
        else:
            segment_high_mean = pd.to_numeric(high_rows[actual_col], errors="coerce").groupby(high_rows["segment"].astype(str)).mean()
            overall_high_mean = float(pd.to_numeric(high_rows[actual_col], errors="coerce").mean())
            high_prediction = forecast_segment.map(segment_high_mean).fillna(overall_high_mean).astype(float)

        triggered = probability >= activation_probability
        prediction = baseline.where(~triggered, high_prediction)
        return pd.DataFrame({"prediction": prediction, "probability": probability, "triggered": triggered}, index=forecast.index)

    train_x, forecast_x = _prepare_model_features(train, forecast, predicted_col=predicted_col)

    y_high = (pd.to_numeric(train[actual_col], errors="coerce") >= high_threshold).astype(int)
    if y_high.nunique() == 1:
        probability = pd.Series(float(y_high.iloc[0]), index=forecast.index)
    else:
        classifier = DecisionTreeClassifier(max_depth=4, min_samples_leaf=1, random_state=7)
        classifier.fit(train_x, y_high)
        class_index = list(classifier.classes_).index(1)
        probability = pd.Series(classifier.predict_proba(forecast_x)[:, class_index], index=forecast.index)

    high_rows = train.loc[y_high == 1]
    if high_rows.empty:
        high_prediction = pd.to_numeric(forecast[predicted_col], errors="coerce")
    elif len(high_rows) == 1:
        high_prediction = pd.Series(float(high_rows[actual_col].iloc[0]), index=forecast.index)
    else:
        high_x, forecast_high_x = _prepare_model_features(high_rows, forecast, predicted_col=predicted_col)
        regressor = DecisionTreeRegressor(max_depth=4, min_samples_leaf=1, random_state=11)
        regressor.fit(high_x, pd.to_numeric(high_rows[actual_col], errors="coerce"))
        high_prediction = pd.Series(regressor.predict(forecast_high_x), index=forecast.index)

    baseline = pd.to_numeric(forecast[predicted_col], errors="coerce")
    triggered = probability >= activation_probability
    prediction = baseline.where(~triggered, high_prediction)
    return pd.DataFrame({"prediction": prediction, "probability": probability, "triggered": triggered}, index=forecast.index)


def _fallback_quantile_prediction(
    validation_frame: pd.DataFrame,
    forecast_frame: pd.DataFrame,
    *,
    actual_col: str,
    predicted_col: str,
    alpha: float,
) -> pd.Series:
    residual = pd.to_numeric(validation_frame[actual_col], errors="coerce") - pd.to_numeric(validation_frame[predicted_col], errors="coerce")
    offset = float(residual.dropna().quantile(alpha)) if residual.notna().any() else 0.0
    return pd.to_numeric(forecast_frame[predicted_col], errors="coerce") + offset


def predict_quantiles(
    validation_frame: pd.DataFrame,
    forecast_frame: pd.DataFrame,
    *,
    actual_col: str = "actual",
    predicted_col: str = "predicted",
) -> pd.DataFrame:
    train = validation_frame.dropna(subset=[actual_col, predicted_col]).copy()
    if train.empty:
        raise ValueError("validation_frame has no comparable rows")
    if GradientBoostingRegressor is None:
        result = pd.DataFrame(
            {
                label: _fallback_quantile_prediction(
                    train,
                    forecast_frame,
                    actual_col=actual_col,
                    predicted_col=predicted_col,
                    alpha=alpha,
                )
                for label, alpha in (("quantile_p50", 0.50), ("quantile_p90", 0.90), ("quantile_p95", 0.95))
            },
            index=forecast_frame.index,
        )
        result["quantile_p90"] = np.maximum(result["quantile_p90"], result["quantile_p50"])
        result["quantile_p95"] = np.maximum(result["quantile_p95"], result["quantile_p90"])
        return result[["quantile_p50", "quantile_p90", "quantile_p95"]]

    train_x, forecast_x = _prepare_model_features(train, forecast_frame, predicted_col=predicted_col)
    y = pd.to_numeric(train[actual_col], errors="coerce")

    predictions: dict[str, pd.Series] = {}
    for label, alpha in (("quantile_p50", 0.50), ("quantile_p90", 0.90), ("quantile_p95", 0.95)):
        try:
            model = GradientBoostingRegressor(
                loss="quantile",
                alpha=alpha,
                n_estimators=80,
                max_depth=2,
                min_samples_leaf=1,
                random_state=int(alpha * 1000),
            )
            model.fit(train_x, y)
            predictions[label] = pd.Series(model.predict(forecast_x), index=forecast_frame.index)
        except Exception:
            predictions[label] = _fallback_quantile_prediction(
                train,
                forecast_frame,
                actual_col=actual_col,
                predicted_col=predicted_col,
                alpha=alpha,
            )

    result = pd.DataFrame(predictions, index=forecast_frame.index)
    result["quantile_p90"] = np.maximum(result["quantile_p90"], result["quantile_p50"])
    result["quantile_p95"] = np.maximum(result["quantile_p95"], result["quantile_p90"])
    return result[["quantile_p50", "quantile_p90", "quantile_p95"]]


def build_strategy_predictions(
    test_frame: pd.DataFrame,
    validation_frame: pd.DataFrame,
    *,
    predicted_col: str = "predicted",
) -> dict[str, pd.Series]:
    corrections = learn_residual_corrections(validation_frame, predicted_col=predicted_col)
    segment_interval = apply_residual_correction(test_frame, corrections, predicted_col=predicted_col)
    high_model = predict_high_classifier_regressor(validation_frame, test_frame, predicted_col=predicted_col)
    quantiles = predict_quantiles(validation_frame, test_frame, predicted_col=predicted_col)
    strategies = {
        "baseline": pd.to_numeric(test_frame[predicted_col], errors="coerce"),
        "segment_interval_bias": segment_interval,
        "late_peak_high_uplift": apply_late_peak_high_uplift(test_frame, corrections, predicted_col=predicted_col),
        "segment_interval_plus_late_peak_uplift": apply_late_peak_high_uplift(
            test_frame,
            corrections,
            predicted_col=predicted_col,
            base_predictions=segment_interval,
            threshold=350.0,
        ),
        "high_classifier_regressor": high_model["prediction"],
        "quantile_p50": quantiles["quantile_p50"],
        "quantile_p90": quantiles["quantile_p90"],
        "quantile_p95": quantiles["quantile_p95"],
    }
    net_load_similarity = _net_load_similarity_series(test_frame, predicted_col=predicted_col)
    if net_load_similarity is not None:
        strategies.update(
            {
                "net_load_similarity": net_load_similarity,
                "fixed_similarity_blend_50": apply_fixed_similarity_blend(test_frame, predicted_col=predicted_col),
                "scenario_similarity_blend": apply_scenario_similarity_blend(test_frame, predicted_col=predicted_col),
            }
        )
    return strategies


def _metrics_row(
    scope: str,
    strategy: str,
    frame: pd.DataFrame,
    predicted: pd.Series,
    *,
    actual_col: str = "actual",
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    scored = frame.copy()
    scored["_strategy_prediction"] = predicted
    metrics = compute_error_metrics(scored, actual_col=actual_col, predicted_col="_strategy_prediction")
    row: dict[str, object] = {"scope": scope, "strategy": strategy}
    if extra:
        row.update(extra)
    row.update(metrics)
    return row


def _threshold_row(
    strategy: str,
    frame: pd.DataFrame,
    predicted: pd.Series,
    threshold: float,
    *,
    actual_col: str = "actual",
) -> dict[str, object]:
    actual = pd.to_numeric(frame[actual_col], errors="coerce")
    strategy_prediction = pd.to_numeric(predicted, errors="coerce")
    subset = frame.loc[actual >= threshold].copy()
    subset_prediction = strategy_prediction.loc[subset.index]
    row = _metrics_row(
        "high_threshold",
        strategy,
        subset,
        subset_prediction,
        actual_col=actual_col,
        extra={"threshold": threshold},
    )
    if subset.empty:
        row["recall_rate"] = math.nan
        row["trigger_rate"] = float((strategy_prediction >= threshold).mean() * 100)
        return row
    row["recall_rate"] = float((subset_prediction >= threshold).mean() * 100)
    row["trigger_rate"] = float((strategy_prediction >= threshold).mean() * 100)
    return row


def build_detailed_report(
    test_frame: pd.DataFrame,
    validation_frame: pd.DataFrame,
    *,
    thresholds: Iterable[float] = (400.0, 600.0, 1000.0),
) -> dict[str, pd.DataFrame]:
    predictions = build_strategy_predictions(test_frame, validation_frame)

    overall_rows = []
    by_date_rows = []
    by_segment_rows = []
    high_rows = []
    for strategy, predicted in predictions.items():
        predicted = pd.Series(predicted, index=test_frame.index)
        overall_rows.append(_metrics_row("overall", strategy, test_frame, predicted))
        if "forecast_date" in test_frame.columns:
            for date, group in test_frame.groupby("forecast_date"):
                by_date_rows.append(
                    _metrics_row("date", strategy, group, predicted.loc[group.index], extra={"forecast_date": date})
                )
        if "segment" in test_frame.columns:
            for segment, group in test_frame.groupby("segment"):
                by_segment_rows.append(
                    _metrics_row("segment", strategy, group, predicted.loc[group.index], extra={"segment": segment})
                )
        for threshold in thresholds:
            high_rows.append(_threshold_row(strategy, test_frame, predicted, float(threshold)))

    sort_columns = ["mae", "strategy"]
    return {
        "overall": pd.DataFrame(overall_rows).sort_values(sort_columns).reset_index(drop=True),
        "by_date": pd.DataFrame(by_date_rows).sort_values(["forecast_date", "mae", "strategy"]).reset_index(drop=True),
        "by_segment": pd.DataFrame(by_segment_rows).sort_values(["segment", "mae", "strategy"]).reset_index(drop=True),
        "by_high_threshold": pd.DataFrame(high_rows).sort_values(["threshold", "mae", "strategy"]).reset_index(drop=True),
    }


def _renewable_ratio(frame: pd.DataFrame) -> pd.Series:
    total_load = pd.to_numeric(frame.get("total_load"), errors="coerce")
    renewable_power = pd.to_numeric(frame.get("renewable_power"), errors="coerce")
    return (renewable_power / total_load.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def build_focus_subset_report(
    test_frame: pd.DataFrame,
    predictions: dict[str, pd.Series],
    *,
    actual_col: str = "actual",
) -> pd.DataFrame:
    predicted = pd.to_numeric(test_frame.get("predicted"), errors="coerce")
    similar = pd.to_numeric(test_frame.get("net_load_only_similar_price"), errors="coerce")
    renewable_ratio = _renewable_ratio(test_frame)
    net_load = pd.to_numeric(test_frame.get("net_load"), errors="coerce")

    renewable_high = renewable_ratio >= max(0.18, float(renewable_ratio.quantile(0.60))) if renewable_ratio.notna().any() else pd.Series(False, index=test_frame.index)
    net_load_low = net_load <= float(net_load.quantile(0.40)) if net_load.notna().any() else pd.Series(False, index=test_frame.index)
    model_over_similarity = predicted - similar >= 50.0

    subsets = {
        "model_over_similarity_gap50": model_over_similarity,
        "renewable_high_gap50_low_netload": model_over_similarity & renewable_high & net_load_low,
        "segment_3_midday": test_frame.get("segment", pd.Series("", index=test_frame.index)).astype(str).eq("segment_3"),
        "segment_5_evening_high_risk": test_frame.get("segment", pd.Series("", index=test_frame.index)).astype(str).eq("segment_5"),
    }

    rows = []
    for scenario, mask in subsets.items():
        subset = test_frame.loc[mask].copy()
        for strategy, strategy_prediction in predictions.items():
            prediction = pd.Series(strategy_prediction, index=test_frame.index)
            rows.append(
                _metrics_row(
                    "focus_subset",
                    strategy,
                    subset,
                    prediction.loc[subset.index],
                    actual_col=actual_col,
                    extra={"scenario": scenario},
                )
            )
    return pd.DataFrame(rows).sort_values(["scenario", "mae", "strategy"]).reset_index(drop=True)


def load_selected_validation_predictions(root: Path) -> pd.DataFrame:
    metadata = json.loads((root / "models" / "current" / "metadata.json").read_text(encoding="utf-8"))
    selected = metadata.get("selected_segment_price_models", {})
    records = [
        json.loads(line)
        for line in (root / "models" / "current" / "validation_predictions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    frame = pd.DataFrame(records)
    if not selected:
        return frame.rename(columns={"predicted": "predicted"})
    parts = []
    for segment, model_key in selected.items():
        parts.append(frame[(frame["segment"] == segment) & (frame["model_key"] == model_key)].copy())
    return pd.concat(parts, ignore_index=True)


def load_actual_prices(root: Path) -> dict[str, pd.Series]:
    actual_by_date: dict[str, pd.Series] = {}
    for workbook in root.rglob("*.xlsx"):
        if any(part in workbook.parts for part in (".test_tmp", "node_modules", ".venv")):
            continue
        try:
            excel = pd.ExcelFile(workbook)
        except Exception:
            continue
        for sheet in excel.sheet_names:
            numbers = re.findall(r"\d+", sheet)
            if len(numbers) < 3 or numbers[0] != "2026":
                continue
            try:
                header = pd.read_excel(workbook, sheet_name=sheet, nrows=0)
            except Exception:
                continue
            if ACTUAL_PRICE_COLUMN not in list(header.columns):
                continue
            values = pd.to_numeric(
                pd.read_excel(workbook, sheet_name=sheet, usecols=[ACTUAL_PRICE_COLUMN], nrows=96)[ACTUAL_PRICE_COLUMN],
                errors="coerce",
            )
            if values.notna().sum() >= 80:
                date = f"{int(numbers[0]):04d}-{int(numbers[1]):02d}-{int(numbers[2]):02d}"
                actual_by_date[date] = values.reset_index(drop=True)
    return actual_by_date


def _latest_archive_by_date(root: Path) -> dict[str, Path]:
    latest: dict[str, tuple[float, Path]] = {}
    for archive in (root / "output" / "prediction_archive").glob("*/*.json"):
        try:
            payload = json.loads(archive.read_text(encoding="utf-8"))
        except Exception:
            continue
        forecast_date = payload.get("forecast_date") or archive.parent.name
        modified = archive.stat().st_mtime
        if forecast_date not in latest or modified > latest[forecast_date][0]:
            latest[forecast_date] = (modified, archive)
    return {date: item[1] for date, item in latest.items()}


def available_backtest_dates(actuals: dict[str, pd.Series], archives: dict[str, Path]) -> list[str]:
    return sorted(set(actuals).intersection(archives))


def discover_backtest_dates(root: Path) -> list[str]:
    return available_backtest_dates(load_actual_prices(root), _latest_archive_by_date(root))


def load_archive_predictions_with_actuals(root: Path, dates: Iterable[str]) -> pd.DataFrame:
    actuals = load_actual_prices(root)
    latest = _latest_archive_by_date(root)
    frames = []
    for date in dates:
        if date not in latest or date not in actuals:
            continue
        payload = json.loads(latest[date].read_text(encoding="utf-8"))
        rows = payload.get("rows", [])
        if not isinstance(rows, list):
            continue
        frame = pd.DataFrame(rows).sort_values("period").iloc[:96].copy()
        price_col = "high_price_adjusted_price" if "high_price_adjusted_price" in frame.columns else "predicted_price"
        frame["predicted"] = pd.to_numeric(frame[price_col], errors="coerce")
        frame["actual"] = actuals[date].values[: len(frame)]
        frame["forecast_date"] = date
        frame["archive_file"] = str(latest[date])
        frames.append(frame)
    if not frames:
        raise ValueError("No archive predictions with actual prices found for requested dates")
    return pd.concat(frames, ignore_index=True)


def _format_metric_row(metrics: dict[str, float | int]) -> str:
    return (
        f"rows={metrics['rows']} MAE={metrics['mae']:.2f} RMSE={metrics['rmse']:.2f} "
        f"bias={metrics['bias']:.2f} p90={metrics['p90_abs_error']:.2f} "
        f"max={metrics['max_abs_error']:.2f} under={metrics['under_rate']:.1f}%"
    )


def run_offline_experiment(root: Path, dates: Iterable[str]) -> None:
    validation = load_selected_validation_predictions(root)
    selected_dates = list(dates)
    if not selected_dates:
        raise ValueError("No forecast dates selected for offline experiment")
    test = load_archive_predictions_with_actuals(root, selected_dates)
    predictions = build_strategy_predictions(test, validation)
    report = build_detailed_report(test, validation)
    focus_report = build_focus_subset_report(test, predictions)

    print("Validation selected hybrid")
    print(_format_metric_row(compute_error_metrics(validation)))
    print()
    print("Archive dates")
    print(", ".join(sorted(str(date) for date in test["forecast_date"].dropna().unique())))
    print()
    print("Archive test baseline")
    print(_format_metric_row(compute_error_metrics(test)))
    print()
    print("Strategy comparison - overall")
    print(report["overall"].to_string(index=False, float_format=lambda value: f"{value:.2f}"))
    print()
    print("Strategy comparison - by date")
    print(report["by_date"].to_string(index=False, float_format=lambda value: f"{value:.2f}"))
    print()
    print("Strategy comparison - by segment")
    print(report["by_segment"].to_string(index=False, float_format=lambda value: f"{value:.2f}"))
    print()
    print("Strategy comparison - high thresholds")
    print(report["by_high_threshold"].to_string(index=False, float_format=lambda value: f"{value:.2f}"))
    print()
    print("Strategy comparison - focus subsets")
    print(focus_report.to_string(index=False, float_format=lambda value: f"{value:.2f}"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline price prediction correction experiments.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root.")
    parser.add_argument("--dates", nargs="*", default=list(DEFAULT_TARGET_DATES), help="Forecast dates to compare.")
    parser.add_argument("--all-dates", action="store_true", help="Scan archives and actual workbooks, then backtest every matched date.")
    args = parser.parse_args()
    root = args.root.resolve()
    dates = discover_backtest_dates(root) if args.all_dates else args.dates
    if args.all_dates:
        print(f"Discovered {len(dates)} backtest date(s).")
    run_offline_experiment(root, dates)


if __name__ == "__main__":
    main()
