"""Expanding-window forecast evaluation for the ABNB research study.

The default command is deliberately development-only.  It uses filtered
Parquet scans capped at the frozen development cutoff, so final-test feature
rows and targets are never materialized by this module's development runner.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
from sklearn.linear_model import Ridge
from statsmodels.regression.linear_model import OLS

from research.abnb.pipeline.daily_features import (
    FEATURE_COLUMNS,
    _repository_state,
    _sha256,
)
from research.abnb.pipeline.targets import TARGET_COLUMN, TARGET_STATUS_COLUMN

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEATURE_PATH = ROOT / "data" / "interim" / "monthly_features.parquet"
DEFAULT_TARGET_PATH = ROOT / "data" / "interim" / "monthly_targets.parquet"
DEFAULT_PROTOCOL_PATH = ROOT / "config" / "evaluation_protocol.json"
DEFAULT_OUTPUT_DIR = ROOT / "evaluation" / "development_oos"

MODEL_COLUMNS = {
    "zero_return": "forecast_zero_return",
    "expanding_average": "forecast_expanding_average",
    "ridge": "forecast_ridge",
}


def _json_value(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_value(item) for item in value]
    return value


def _filtered_parquet(
    path: Path, cutoff: pd.Timestamp, columns: Iterable[str]
) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    table = ds.dataset(path, format="parquet").to_table(
        columns=list(columns),
        filter=ds.field("reference_session") <= cutoff.to_datetime64(),
    )
    frame = table.to_pandas()
    frame["reference_session"] = pd.to_datetime(
        frame["reference_session"], errors="raise"
    ).dt.normalize()
    return frame.sort_values("reference_session").reset_index(drop=True)


def load_development_evaluation_inputs(
    feature_path: Path | str = DEFAULT_FEATURE_PATH,
    target_path: Path | str = DEFAULT_TARGET_PATH,
    protocol_path: Path | str = DEFAULT_PROTOCOL_PATH,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load only development rows and validate their joined contract."""

    feature_path = Path(feature_path).resolve()
    target_path = Path(target_path).resolve()
    protocol_path = Path(protocol_path).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    configured_features = tuple(protocol["eligibility"]["required_feature_names"])
    if configured_features != FEATURE_COLUMNS:
        raise ValueError("protocol feature order differs from the locked feature set")
    cutoff = pd.Timestamp(protocol["periods"]["development_origin_end"])
    feature_columns = [
        "reference_session",
        "issued_at_utc",
        *FEATURE_COLUMNS,
        *(f"{name}_STATUS" for name in FEATURE_COLUMNS),
    ]
    target_columns = [
        "reference_session",
        "issued_at_utc",
        "label_available_at",
        TARGET_COLUMN,
        TARGET_STATUS_COLUMN,
        "evaluation_partition",
    ]
    features = _filtered_parquet(feature_path, cutoff, feature_columns)
    targets = _filtered_parquet(target_path, cutoff, target_columns)
    if not targets["evaluation_partition"].eq("DEVELOPMENT").all():
        raise ValueError("development scan materialized a non-development target row")
    for frame, name in ((features, "features"), (targets, "targets")):
        if frame["reference_session"].duplicated().any():
            raise ValueError(f"{name} contain duplicate reference sessions")
    table = features.merge(
        targets,
        on="reference_session",
        how="inner",
        validate="one_to_one",
        suffixes=("_feature", "_target"),
    )
    if len(table) != len(features) or len(table) != len(targets):
        raise ValueError("development feature and target origins do not match")
    feature_issuance = pd.to_datetime(table.pop("issued_at_utc_feature"), utc=True)
    target_issuance = pd.to_datetime(table.pop("issued_at_utc_target"), utc=True)
    if not feature_issuance.equals(target_issuance):
        raise ValueError("feature and target issuance times do not match")
    table.insert(1, "issued_at_utc", feature_issuance)
    table["label_available_at"] = pd.to_datetime(
        table["label_available_at"], errors="raise", utc=True
    )
    table = table.sort_values("reference_session").reset_index(drop=True)
    return table, protocol


def _finite_numeric(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.map(lambda value: pd.notna(value) and math.isfinite(float(value)))


def _valid_targets(table: pd.DataFrame) -> pd.Series:
    return table[TARGET_STATUS_COLUMN].astype("string").eq("VALID") & _finite_numeric(
        table[TARGET_COLUMN]
    )


def _complete_features(table: pd.DataFrame, feature_names: Sequence[str]) -> pd.Series:
    result = pd.Series(True, index=table.index)
    for name in feature_names:
        result &= table[f"{name}_STATUS"].astype("string").eq("VALID")
        result &= _finite_numeric(table[name])
    return result


def _training_mask(
    table: pd.DataFrame,
    origin: pd.Series,
    *,
    require_complete_features: bool,
    eligibility_features: Sequence[str],
) -> pd.Series:
    mask = (
        table["reference_session"].lt(origin["reference_session"])
        & table["label_available_at"].le(origin["issued_at_utc"])
        & _valid_targets(table)
    )
    if require_complete_features:
        mask &= _complete_features(table, eligibility_features)
    return mask


def _fit_scaled_ridge(
    train: pd.DataFrame,
    forecast_row: pd.Series,
    feature_names: Sequence[str],
    alpha: float,
) -> float:
    x_train = train.loc[:, list(feature_names)].to_numpy(dtype=float)
    y_train = train[TARGET_COLUMN].to_numpy(dtype=float)
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0, ddof=0)
    scale[scale == 0.0] = 1.0
    model = Ridge(alpha=float(alpha), fit_intercept=True)
    model.fit((x_train - mean) / scale, y_train)
    x_forecast = forecast_row.loc[list(feature_names)].to_numpy(dtype=float)
    return float(model.predict(((x_forecast - mean) / scale).reshape(1, -1))[0])


def select_ridge_alpha(
    table: pd.DataFrame,
    outer_origin: pd.Series,
    *,
    model_features: Sequence[str],
    eligibility_features: Sequence[str],
    alpha_grid: Sequence[float],
    minimum_history: int,
    minimum_predictions: int,
    tie_tolerance: float,
) -> tuple[float | None, int, dict[str, float]]:
    """Chronological inner validation with a scaler refitted in every fold."""

    outer_train = table.loc[
        _training_mask(
            table,
            outer_origin,
            require_complete_features=True,
            eligibility_features=eligibility_features,
        )
    ].sort_values("reference_session")
    validation_rows: list[tuple[pd.Series, pd.DataFrame]] = []
    for _, validation in outer_train.iterrows():
        inner_train = table.loc[
            _training_mask(
                table,
                validation,
                require_complete_features=True,
                eligibility_features=eligibility_features,
            )
        ]
        if len(inner_train) >= minimum_history:
            validation_rows.append((validation, inner_train))
    if len(validation_rows) < minimum_predictions:
        return None, len(validation_rows), {}

    scores: dict[str, float] = {}
    for alpha in alpha_grid:
        errors = []
        for validation, inner_train in validation_rows:
            prediction = _fit_scaled_ridge(
                inner_train, validation, model_features, float(alpha)
            )
            errors.append((float(validation[TARGET_COLUMN]) - prediction) ** 2)
        scores[str(float(alpha))] = float(np.mean(errors))
    minimum = min(scores.values())
    eligible_alphas = [
        float(alpha)
        for alpha in alpha_grid
        if scores[str(float(alpha))] <= minimum + tie_tolerance
    ]
    return max(eligible_alphas), len(validation_rows), scores


def walk_forward_forecasts(
    table: pd.DataFrame,
    protocol: dict[str, Any],
    *,
    forecast_sessions: Iterable[Any] | None = None,
    include_ablations: bool = True,
) -> pd.DataFrame:
    """Produce expanding-window forecasts without relaxing any origin."""

    required = tuple(protocol["eligibility"]["required_feature_names"])
    training = protocol["training"]
    alphas = tuple(float(value) for value in protocol["ridge"]["alpha_grid"])
    minimum_history = int(training["minimum_eligible_matured_observations"])
    minimum_predictions = int(training["minimum_inner_validation_predictions"])
    if forecast_sessions is None:
        selected_sessions = set(table["reference_session"])
    else:
        selected_sessions = {
            pd.Timestamp(value).tz_localize(None).normalize()
            if pd.Timestamp(value).tzinfo is not None
            else pd.Timestamp(value).normalize()
            for value in forecast_sessions
        }
    rows: list[dict[str, Any]] = []
    complete = _complete_features(table, required)
    valid_target = _valid_targets(table)
    for index, origin in table.iterrows():
        if origin["reference_session"] not in selected_sessions:
            continue
        result: dict[str, Any] = {
            "reference_session": origin["reference_session"],
            "issued_at_utc": origin["issued_at_utc"],
            "actual": float(origin[TARGET_COLUMN]) if valid_target.loc[index] else np.nan,
            "forecast_status": "ELIGIBLE",
        }
        if not valid_target.loc[index]:
            result["forecast_status"] = "INVALID_TARGET"
            rows.append(result)
            continue
        if not complete.loc[index]:
            result["forecast_status"] = "INCOMPLETE_FEATURES"
            rows.append(result)
            continue
        mean_train = table.loc[
            _training_mask(
                table,
                origin,
                require_complete_features=False,
                eligibility_features=required,
            )
        ]
        ridge_train = table.loc[
            _training_mask(
                table,
                origin,
                require_complete_features=True,
                eligibility_features=required,
            )
        ]
        result["matured_mean_train_count"] = len(mean_train)
        result["ridge_train_count"] = len(ridge_train)
        result[MODEL_COLUMNS["zero_return"]] = 0.0
        result[MODEL_COLUMNS["expanding_average"]] = (
            float(mean_train[TARGET_COLUMN].astype(float).mean())
            if len(mean_train)
            else np.nan
        )
        if len(ridge_train) < minimum_history:
            result["forecast_status"] = "INSUFFICIENT_RIDGE_HISTORY"
            rows.append(result)
            continue
        alpha, inner_count, scores = select_ridge_alpha(
            table,
            origin,
            model_features=required,
            eligibility_features=required,
            alpha_grid=alphas,
            minimum_history=minimum_history,
            minimum_predictions=minimum_predictions,
            tie_tolerance=1e-12,
        )
        result["ridge_inner_validation_count"] = inner_count
        result["ridge_inner_mse_by_alpha"] = json.dumps(scores, sort_keys=True)
        if alpha is None:
            result["forecast_status"] = "INSUFFICIENT_INNER_VALIDATION"
            rows.append(result)
            continue
        result["ridge_alpha"] = alpha
        result[MODEL_COLUMNS["ridge"]] = _fit_scaled_ridge(
            ridge_train, origin, required, alpha
        )
        if include_ablations:
            for omitted in required:
                model_features = tuple(name for name in required if name != omitted)
                ablation_alpha, ablation_inner_count, _ = select_ridge_alpha(
                    table,
                    origin,
                    model_features=model_features,
                    eligibility_features=required,
                    alpha_grid=alphas,
                    minimum_history=minimum_history,
                    minimum_predictions=minimum_predictions,
                    tie_tolerance=1e-12,
                )
                if ablation_alpha is None:
                    raise RuntimeError("ablation inner validation diverged from full model")
                result[f"forecast_without_{omitted}"] = _fit_scaled_ridge(
                    ridge_train, origin, model_features, ablation_alpha
                )
                result[f"alpha_without_{omitted}"] = ablation_alpha
                result[f"inner_count_without_{omitted}"] = ablation_inner_count
        rows.append(result)
    return pd.DataFrame(rows).sort_values("reference_session").reset_index(drop=True)


def _direction_hit(actual: np.ndarray, forecast: np.ndarray) -> np.ndarray:
    return ((actual > 0) & (forecast > 0)) | ((actual < 0) & (forecast < 0)) | (
        (actual == 0) & (forecast == 0)
    )


def _metric_values(
    actual: np.ndarray,
    forecast: np.ndarray,
    zero: np.ndarray,
    expanding_average: np.ndarray,
) -> dict[str, float]:
    error = actual - forecast
    squared = error**2
    zero_sse = float(np.sum((actual - zero) ** 2))
    average_sse = float(np.sum((actual - expanding_average) ** 2))
    positives = int(np.sum(actual > 0))
    negatives = int(np.sum(actual < 0))
    zeros = len(actual) - positives - negatives
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(squared))),
        "r2_vs_zero": float(1.0 - np.sum(squared) / zero_sse)
        if zero_sse > 0
        else np.nan,
        "r2_vs_expanding_average": float(1.0 - np.sum(squared) / average_sse)
        if average_sse > 0
        else np.nan,
        "directional_accuracy": float(np.mean(_direction_hit(actual, forecast))),
        "directional_class_frequency_baseline": float(
            max(positives, negatives, zeros) / len(actual)
        ),
    }


def circular_moving_block_indices(
    observation_count: int,
    block_length: int,
    replications: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if observation_count < 1 or block_length < 1 or replications < 1:
        raise ValueError("bootstrap dimensions must be positive")
    block_count = math.ceil(observation_count / block_length)
    starts = rng.integers(0, observation_count, size=(replications, block_count))
    offsets = np.arange(block_length)
    indices = (starts[..., None] + offsets) % observation_count
    return indices.reshape(replications, -1)[:, :observation_count]


def _percentile_interval(values: np.ndarray, confidence: float) -> list[float]:
    finite = values[np.isfinite(values)]
    if not len(finite):
        return [np.nan, np.nan]
    tail = (1.0 - confidence) / 2.0
    return [
        float(np.quantile(finite, tail)),
        float(np.quantile(finite, 1.0 - tail)),
    ]


def hac_mean_test(values: Sequence[float], max_lag: int = 2) -> dict[str, float]:
    sample = np.asarray(values, dtype=float)
    sample = sample[np.isfinite(sample)]
    if len(sample) < 2:
        return {"estimate": float(np.mean(sample)) if len(sample) else np.nan,
                "standard_error": np.nan, "t_statistic": np.nan, "p_value": np.nan}
    fitted = OLS(sample, np.ones((len(sample), 1))).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": min(max_lag, len(sample) - 1), "use_correction": True},
        use_t=True,
    )
    estimate = float(fitted.params[0])
    standard_error = float(fitted.bse[0])
    if not math.isfinite(standard_error) or standard_error <= np.finfo(float).eps:
        t_statistic = (
            0.0
            if abs(estimate) <= np.finfo(float).eps
            else math.copysign(math.inf, estimate)
        )
        p_value = 1.0 if t_statistic == 0.0 else 0.0
    else:
        t_statistic = float(fitted.tvalues[0])
        p_value = float(fitted.pvalues[0])
    return {
        "estimate": estimate,
        "standard_error": standard_error,
        "t_statistic": t_statistic,
        "p_value": p_value,
    }


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    values = np.asarray(p_values, dtype=float)
    if np.any(~np.isfinite(values)) or np.any((values < 0) | (values > 1)):
        raise ValueError("Holm adjustment requires finite p-values in [0, 1]")
    order = np.argsort(values, kind="stable")
    adjusted = np.empty(len(values), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(values) - rank) * values[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def evaluate_forecasts(
    forecasts: pd.DataFrame,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Compute paired metrics, temporal stability, and dependence-aware inference."""

    required = tuple(protocol["eligibility"]["required_feature_names"])
    scored = forecasts.loc[forecasts["forecast_status"].eq("ELIGIBLE")].copy()
    score_columns = ["actual", *MODEL_COLUMNS.values()]
    if scored.empty or not np.isfinite(scored[score_columns].to_numpy(dtype=float)).all():
        raise ValueError("eligible forecast rows must contain all primary forecasts")
    if len(scored) < 2:
        raise ValueError("at least two eligible forecasts are required")
    actual = scored["actual"].to_numpy(dtype=float)
    zero = scored[MODEL_COLUMNS["zero_return"]].to_numpy(dtype=float)
    average = scored[MODEL_COLUMNS["expanding_average"]].to_numpy(dtype=float)
    uncertainty = protocol["uncertainty"]
    replications = int(uncertainty["replications"])
    confidence = float(uncertainty["confidence_level"])
    primary_block = int(uncertainty["block_length_months"])
    rng = np.random.default_rng(int(uncertainty["seed"]))
    bootstrap_indices = circular_moving_block_indices(
        len(scored), primary_block, replications, rng
    )

    model_results: dict[str, Any] = {}
    for model, column in MODEL_COLUMNS.items():
        prediction = scored[column].to_numpy(dtype=float)
        estimates = _metric_values(actual, prediction, zero, average)
        draws = {name: [] for name in estimates}
        for indices in bootstrap_indices:
            values = _metric_values(
                actual[indices], prediction[indices], zero[indices], average[indices]
            )
            for name, value in values.items():
                draws[name].append(value)
        midpoint = len(scored) // 2
        halves = []
        for label, positions in (
            ("first_half", np.arange(0, midpoint)),
            ("second_half", np.arange(midpoint, len(scored))),
        ):
            half_metrics = _metric_values(
                actual[positions], prediction[positions], zero[positions], average[positions]
            )
            halves.append(
                {
                    "period": label,
                    "start": scored.iloc[positions[0]]["reference_session"],
                    "end": scored.iloc[positions[-1]]["reference_session"],
                    "observations": len(positions),
                    "metrics": half_metrics,
                }
            )
        model_results[model] = {
            "estimates": estimates,
            "primary_block_bootstrap_95_intervals": {
                name: _percentile_interval(np.asarray(values), confidence)
                for name, values in draws.items()
            },
            "temporal_stability": {
                "rule": "fixed chronological halves; floor(N/2) in first half",
                "halves": halves,
                "mae_second_minus_first": (
                    halves[1]["metrics"]["mae"] - halves[0]["metrics"]["mae"]
                ),
                "rmse_second_minus_first": (
                    halves[1]["metrics"]["rmse"] - halves[0]["metrics"]["rmse"]
                ),
            },
        }

    comparisons: dict[str, Any] = {}
    squared_losses = {
        name: (actual - scored[column].to_numpy(dtype=float)) ** 2
        for name, column in MODEL_COLUMNS.items()
    }
    for benchmark in ("expanding_average", "zero_return"):
        paired = squared_losses["ridge"] - squared_losses[benchmark]
        draws = np.mean(paired[bootstrap_indices], axis=1)
        sensitivity = {}
        for block in uncertainty["dependence_sensitivity_block_lengths_months"]:
            indices = circular_moving_block_indices(
                len(scored), int(block), replications, rng
            )
            sensitivity[str(block)] = _percentile_interval(
                np.mean(paired[indices], axis=1), confidence
            )
        comparisons[f"ridge_minus_{benchmark}_squared_error"] = {
            **hac_mean_test(paired, max_lag=2),
            "primary_block_bootstrap_95_interval": _percentile_interval(draws, confidence),
            "sensitivity_block_bootstrap_95_intervals": sensitivity,
            "interpretation": "negative favors Ridge",
        }

    ablation_results = []
    raw_p_values = []
    for omitted in required:
        column = f"forecast_without_{omitted}"
        if column not in scored or not np.isfinite(scored[column].to_numpy(dtype=float)).all():
            raise ValueError(f"missing complete ablation forecasts for {omitted}")
        ablated_loss = (actual - scored[column].to_numpy(dtype=float)) ** 2
        paired = ablated_loss - squared_losses["ridge"]
        test = hac_mean_test(paired, max_lag=2)
        raw_p_values.append(test["p_value"])
        ablation_results.append(
            {
                "omitted_feature": omitted,
                **test,
                "primary_block_bootstrap_95_interval": _percentile_interval(
                    np.mean(paired[bootstrap_indices], axis=1), confidence
                ),
                "interpretation": "positive favors retaining the feature",
            }
        )
    adjusted = holm_adjust(raw_p_values)
    familywise_alpha = float(protocol["feature_tests"]["familywise_alpha"])
    for result, adjusted_p in zip(ablation_results, adjusted):
        result["holm_adjusted_p_value"] = adjusted_p
        result["holm_reject_at_0_05"] = adjusted_p <= familywise_alpha

    return _json_value(
        {
            "scored_origins": len(scored),
            "scheduled_origin_status_counts": forecasts["forecast_status"]
            .value_counts(dropna=False)
            .to_dict(),
            "scored_origin_start": scored["reference_session"].min(),
            "scored_origin_end": scored["reference_session"].max(),
            "models": model_results,
            "paired_comparisons": comparisons,
            "leave_one_feature_out_diagnostics": {
                "family_size": len(ablation_results),
                "multiple_testing": "Holm step-down, two-sided HAC p-values",
                "results": ablation_results,
            },
            "inference": {
                "bootstrap": "circular moving-block percentile",
                "primary_block_length_months": primary_block,
                "replications": replications,
                "seed": int(uncertainty["seed"]),
                "hac_max_lag": 2,
                "direction_rule": "prediction and actual must share a strict sign; exact zeros match only zeros",
            },
        }
    )


def _write_report(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# Development-Only Expanding-Window Forecast Evaluation",
        "",
        "> This is a development-period pseudo-out-of-sample diagnostic, not the frozen",
        "> confirmatory final-test result. Source rights and point-in-time adjustment",
        "> evidence remain unresolved, and no final-test row was read.",
        "",
        f"Scored origins: **{result['results']['scored_origins']}** "
        f"({result['results']['scored_origin_start'][:10]} through "
        f"{result['results']['scored_origin_end'][:10]}).",
        "",
        "## Primary metrics",
        "",
        "| Model | MAE [95% CI] | RMSE [95% CI] | R^2 vs zero [95% CI] | R^2 vs expanding mean [95% CI] | Directional accuracy [95% CI] | Class-frequency baseline |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "zero_return": "Zero return",
        "expanding_average": "Matured expanding average",
        "ridge": "Eight-feature Ridge",
    }
    for model, label in labels.items():
        metrics = result["results"]["models"][model]["estimates"]
        intervals = result["results"]["models"][model][
            "primary_block_bootstrap_95_intervals"
        ]

        def estimate_interval(name: str) -> str:
            return (
                f"{metrics[name]:.6f} "
                f"[{intervals[name][0]:.6f}, {intervals[name][1]:.6f}]"
            )

        lines.append(
            f"| {label} | {estimate_interval('mae')} | "
            f"{estimate_interval('rmse')} | {estimate_interval('r2_vs_zero')} | "
            f"{estimate_interval('r2_vs_expanding_average')} | "
            f"{estimate_interval('directional_accuracy')} | "
            f"{metrics['directional_class_frequency_baseline']:.3f} |"
        )
    primary = result["results"]["paired_comparisons"][
        "ridge_minus_expanding_average_squared_error"
    ]
    lines.extend(
        [
            "",
            "## Dependence-aware primary comparison",
            "",
            "The paired mean squared-error difference is Ridge minus the matured",
            "expanding-average benchmark, so negative values favor Ridge.",
            "",
            f"- Estimate: {primary['estimate']:.8f}",
            f"- Circular three-month block-bootstrap 95% interval: "
            f"[{primary['primary_block_bootstrap_95_interval'][0]:.8f}, "
            f"{primary['primary_block_bootstrap_95_interval'][1]:.8f}]",
            f"- Newey-West HAC(2) two-sided p-value: {primary['p_value']:.6f}",
            "",
            "## Temporal stability",
            "",
            "Temporal stability uses two fixed chronological halves:",
            "",
            "| Model | First-half MAE | Second-half MAE | First-half RMSE | Second-half RMSE |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for model, label in labels.items():
        halves = result["results"]["models"][model]["temporal_stability"]["halves"]
        lines.append(
            f"| {label} | {halves[0]['metrics']['mae']:.6f} | "
            f"{halves[1]['metrics']['mae']:.6f} | "
            f"{halves[0]['metrics']['rmse']:.6f} | "
            f"{halves[1]['metrics']['rmse']:.6f} |"
        )
    status_counts = result["results"]["scheduled_origin_status_counts"]
    lines.extend(
        [
            "",
            "## Eligibility accounting",
            "",
            *[f"- `{status}`: {count}" for status, count in status_counts.items()],
            "",
            "## Leave-one-feature-out diagnostics",
            "",
            "| Omitted feature | Ablated minus full MSE | HAC p-value | Holm-adjusted p-value |",
            "|---|---:|---:|---:|",
        ]
    )
    ablations = result["results"]["leave_one_feature_out_diagnostics"]["results"]
    for diagnostic in ablations:
        lines.append(
            f"| `{diagnostic['omitted_feature']}` | {diagnostic['estimate']:.8f} | "
            f"{diagnostic['p_value']:.6f} | "
            f"{diagnostic['holm_adjusted_p_value']:.6f} |"
        )
    lines.extend(
        [
            "",
            "Full block-length sensitivities and per-origin forecasts are in the JSON",
            "and CSV artifacts.",
            "",
            "## Interpretation boundary",
            "",
            "These results can validate the implementation and show development-period",
            "behavior. They cannot support the confirmatory research claim. The isolated",
            "12-origin final test remains unopened until the data blockers are resolved.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_development_evaluation(
    *,
    feature_path: Path | str = DEFAULT_FEATURE_PATH,
    target_path: Path | str = DEFAULT_TARGET_PATH,
    protocol_path: Path | str = DEFAULT_PROTOCOL_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> dict[str, Path]:
    feature_path = Path(feature_path).resolve()
    target_path = Path(target_path).resolve()
    protocol_path = Path(protocol_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    table, protocol = load_development_evaluation_inputs(
        feature_path, target_path, protocol_path
    )
    forecasts = walk_forward_forecasts(table, protocol, include_ablations=True)
    results = evaluate_forecasts(forecasts, protocol)
    revision, dirty = _repository_state()
    artifact = _json_value(
        {
            "artifact_id": "EVAL-DEV-OOS-001",
            "schema_version": 1,
            "scope": "DEVELOPMENT_ONLY_PSEUDO_OUT_OF_SAMPLE",
            "confirmatory_final_test_access": False,
            "results": results,
            "inputs": {
                "monthly_features": {"path": feature_path, "sha256": _sha256(feature_path)},
                "monthly_targets": {"path": target_path, "sha256": _sha256(target_path)},
                "evaluation_protocol": {"path": protocol_path, "sha256": _sha256(protocol_path)},
            },
            "provenance": {
                "built_at_utc": datetime.now(timezone.utc),
                "code_revision": revision,
                "code_dirty": dirty,
                "development_cutoff_enforced": protocol["periods"]["development_origin_end"],
            },
        }
    )
    json_path = output_dir / "development_oos_evaluation.json"
    json_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    report_path = output_dir / "DEVELOPMENT_OOS_EVALUATION.md"
    _write_report(report_path, artifact)
    prediction_path = output_dir / "development_oos_predictions.csv"
    forecasts.to_csv(prediction_path, index=False)
    manifest = {
        "artifact_id": artifact["artifact_id"],
        "created_at_utc": artifact["provenance"]["built_at_utc"],
        "files": {
            path.relative_to(output_dir).as_posix(): {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in (json_path, report_path, prediction_path)
        },
    }
    manifest_path = output_dir / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "report": report_path,
        "results": json_path,
        "predictions": prediction_path,
        "manifest": manifest_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGET_PATH)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()
    outputs = run_development_evaluation(
        feature_path=arguments.features,
        target_path=arguments.targets,
        protocol_path=arguments.protocol,
        output_dir=arguments.output_dir,
    )
    for path in outputs.values():
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
