"""Run descriptive feature diagnostics on the frozen development period only.

The module deliberately does not test feature/target predictiveness.  It reads
only rows at or before the development cutoff through filtered Arrow scans and
uses target values solely to quantify the dependence induced by overlapping
three-calendar-month outcomes.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
from scipy import stats

from research.abnb.pipeline.daily_features import (
    FEATURE_COLUMNS,
    STATUS_COLUMNS,
    _repository_state,
    _sha256,
)
from research.abnb.pipeline.targets import TARGET_COLUMN, TARGET_STATUS_COLUMN

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEATURE_PATH = ROOT / "data" / "interim" / "monthly_features.parquet"
DEFAULT_TARGET_PATH = ROOT / "data" / "interim" / "monthly_targets.parquet"
DEFAULT_PROTOCOL_PATH = ROOT / "config" / "evaluation_protocol.json"
DEFAULT_RAW_ROOT = ROOT / "data" / "raw"
DEFAULT_OUTPUT_DIR = ROOT / "diagnostics" / "development_features"

SUBPERIOD_COUNT = 3
OVERLAP_HORIZON_MONTHS = 3
EXTREME_IQR_MULTIPLIER = 1.5

RAW_FILES = {
    "ABNB": Path("Dataset1/ABNB_daily.csv"),
    "BKNG": Path("Dataset2/BKNG_daily.csv"),
    "EXPE": Path("Dataset2/EXPE_daily.csv"),
    "SPY": Path("Dataset2/SPY_daily.csv"),
}

# The interval is inclusive of the origin and the session at the stated offset.
ACTION_WINDOWS = {
    "SPY_RET_5D": {"securities": ("SPY",), "session_offset": 5},
    "PEER_RET_5D": {"securities": ("EXPE", "BKNG"), "session_offset": 5},
    "SPY_RVOL_20D": {"securities": ("SPY",), "session_offset": 20},
}


def _json_value(value: Any) -> Any:
    """Convert numpy/pandas values into strict JSON-compatible values."""

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
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _filtered_parquet(
    path: Path, cutoff: pd.Timestamp, columns: Iterable[str]
) -> pd.DataFrame:
    """Materialize only rows through ``cutoff`` from a Parquet dataset."""

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
    if frame.empty or frame["reference_session"].max() > cutoff:
        raise RuntimeError("development-only Parquet filter was not enforced")
    return frame.sort_values("reference_session").reset_index(drop=True)


def load_development_inputs(
    feature_path: Path,
    target_path: Path,
    protocol_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], pd.Timestamp]:
    """Load the frozen development partition without materializing later rows."""

    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    cutoff = pd.Timestamp(protocol["periods"]["development_origin_end"])
    start = pd.Timestamp(protocol["periods"]["development_origin_start"])
    feature_columns = [
        "reference_session",
        *FEATURE_COLUMNS,
        *STATUS_COLUMNS,
    ]
    target_columns = [
        "reference_session",
        "maturity_session",
        TARGET_COLUMN,
        TARGET_STATUS_COLUMN,
        "evaluation_partition",
    ]
    features = _filtered_parquet(feature_path, cutoff, feature_columns)
    targets = _filtered_parquet(target_path, cutoff, target_columns)
    for name, frame in (("features", features), ("targets", targets)):
        if frame["reference_session"].min() < start:
            raise ValueError(f"{name} contains rows before the frozen development start")
        if frame["reference_session"].duplicated().any():
            raise ValueError(f"{name} contains duplicate reference sessions")
    if not targets["evaluation_partition"].eq("DEVELOPMENT").all():
        raise RuntimeError("non-development target row passed the filtered scan")
    return features, targets, protocol, cutoff


def assign_subperiods(sessions: pd.Series, count: int = SUBPERIOD_COUNT) -> pd.Series:
    """Assign contiguous, near-equal row-count subperiods without using values."""

    if count < 1 or len(sessions) < count:
        raise ValueError("subperiod count must be positive and no larger than rows")
    labels = np.empty(len(sessions), dtype=object)
    for index, positions in enumerate(np.array_split(np.arange(len(sessions)), count), 1):
        first = pd.Timestamp(sessions.iloc[int(positions[0])]).strftime("%Y-%m")
        last = pd.Timestamp(sessions.iloc[int(positions[-1])]).strftime("%Y-%m")
        labels[positions] = f"P{index}: {first} to {last}"
    return pd.Series(labels, index=sessions.index, dtype="string")


def status_diagnostics(features: pd.DataFrame) -> dict[str, Any]:
    records: dict[str, Any] = {}
    periods = ["ALL", *features["subperiod"].drop_duplicates().tolist()]
    for feature in FEATURE_COLUMNS:
        by_period: dict[str, Any] = {}
        for period in periods:
            rows = features if period == "ALL" else features.loc[features["subperiod"].eq(period)]
            counts = rows[f"{feature}_STATUS"].astype("string").value_counts(dropna=False)
            value_missing = int(pd.to_numeric(rows[feature], errors="coerce").isna().sum())
            by_period[period] = {
                "rows": len(rows),
                "value_missing": value_missing,
                "value_missing_rate": value_missing / len(rows),
                "status_counts": {str(key): int(value) for key, value in counts.items()},
            }
        records[feature] = by_period
    return records


def distribution_diagnostics(features: pd.DataFrame) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for feature in FEATURE_COLUMNS:
        status = features[f"{feature}_STATUS"].astype("string")
        values = pd.to_numeric(features[feature], errors="coerce")
        valid = values.loc[status.eq("VALID") & np.isfinite(values)].astype(float)
        q1, q3 = valid.quantile([0.25, 0.75])
        iqr = q3 - q1
        lower = q1 - EXTREME_IQR_MULTIPLIER * iqr
        upper = q3 + EXTREME_IQR_MULTIPLIER * iqr
        extreme_mask = valid.lt(lower) | valid.gt(upper)
        extremes = []
        for row_index, value in valid.loc[extreme_mask].sort_values().items():
            extremes.append(
                {
                    "reference_session": features.loc[row_index, "reference_session"],
                    "value": value,
                    "direction": "LOW" if value < lower else "HIGH",
                }
            )
        median = float(valid.median())
        output[feature] = {
            "n_valid": len(valid),
            "mean": valid.mean(),
            "standard_deviation": valid.std(ddof=1),
            "minimum": valid.min(),
            "p01": valid.quantile(0.01),
            "p05": valid.quantile(0.05),
            "p25": q1,
            "median": median,
            "p75": q3,
            "p95": valid.quantile(0.95),
            "p99": valid.quantile(0.99),
            "maximum": valid.max(),
            "median_absolute_deviation": np.median(np.abs(valid - median)),
            "skewness": stats.skew(valid, bias=False),
            "excess_kurtosis": stats.kurtosis(valid, bias=False),
            "tukey_lower_fence": lower,
            "tukey_upper_fence": upper,
            "tukey_extreme_count": int(extreme_mask.sum()),
            "tukey_extremes": extremes,
        }
    return output


def _valid_feature_frame(features: pd.DataFrame) -> pd.DataFrame:
    values = features.loc[:, FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    valid_status = pd.DataFrame(
        {
            feature: features[f"{feature}_STATUS"].astype("string").eq("VALID")
            for feature in FEATURE_COLUMNS
        }
    )
    return values.where(valid_status & np.isfinite(values)).astype(float)


def correlation_diagnostics(features: pd.DataFrame) -> dict[str, Any]:
    values = _valid_feature_frame(features)
    pearson = values.corr(method="pearson")
    spearman = values.corr(method="spearman")
    pair_n = values.notna().astype(int).T.dot(values.notna().astype(int))
    complete = values.dropna()
    standardized = (complete - complete.mean()) / complete.std(ddof=0)
    correlation = standardized.corr()
    inverse = np.linalg.pinv(correlation.to_numpy())
    vifs = dict(zip(FEATURE_COLUMNS, np.diag(inverse), strict=True))
    standardized_array = standardized.to_numpy(dtype=float)
    singular_values = np.linalg.svd(standardized_array, compute_uv=False)
    condition_indices = np.divide(
        singular_values.max(),
        singular_values,
        out=np.full_like(singular_values, np.inf),
        where=singular_values > np.finfo(float).eps,
    )
    pairs = []
    for left_index, left in enumerate(FEATURE_COLUMNS):
        for right in FEATURE_COLUMNS[left_index + 1 :]:
            pairs.append((abs(pearson.loc[left, right]), left, right))
    largest = max(pairs, default=(float("nan"), None, None))
    return {
        "pairwise_complete_observation_counts": pair_n.to_dict(),
        "pearson": pearson.to_dict(),
        "spearman": spearman.to_dict(),
        "largest_absolute_pearson_pair": {
            "left": largest[1],
            "right": largest[2],
            "absolute_correlation": largest[0],
            "correlation": pearson.loc[largest[1], largest[2]] if largest[1] else None,
        },
        "multicollinearity": {
            "complete_case_rows": len(complete),
            "vif": vifs,
            "maximum_vif": max(vifs.values()),
            "condition_number": np.linalg.cond(standardized_array),
            "condition_indices": condition_indices.tolist(),
            "note": "VIF uses the pseudoinverse of the complete-case correlation matrix.",
        },
    }


def stability_diagnostics(features: pd.DataFrame) -> dict[str, Any]:
    values = _valid_feature_frame(features)
    period_names = features["subperiod"].drop_duplicates().tolist()
    output: dict[str, Any] = {}
    for feature in FEATURE_COLUMNS:
        summaries: dict[str, Any] = {}
        period_values: dict[str, pd.Series] = {}
        for period in period_names:
            sample = values.loc[features["subperiod"].eq(period), feature].dropna()
            period_values[period] = sample
            summaries[period] = {
                "n": len(sample),
                "mean": sample.mean(),
                "standard_deviation": sample.std(ddof=1),
                "median": sample.median(),
                "p25": sample.quantile(0.25),
                "p75": sample.quantile(0.75),
            }
        first = period_values[period_names[0]]
        last = period_values[period_names[-1]]
        pooled_variance = (
            ((len(first) - 1) * first.var(ddof=1) + (len(last) - 1) * last.var(ddof=1))
            / max(len(first) + len(last) - 2, 1)
        )
        pooled_sd = math.sqrt(max(float(pooled_variance), 0.0))
        smd = (last.mean() - first.mean()) / pooled_sd if pooled_sd > 0 else None
        first_sd = first.std(ddof=1)
        last_sd = last.std(ddof=1)
        std_ratio = last_sd / first_sd if first_sd > 0 else None
        ks = stats.ks_2samp(first, last, method="auto") if len(first) and len(last) else None
        output[feature] = {
            "subperiods": summaries,
            "first_vs_last": {
                "standardized_mean_difference": smd,
                "standard_deviation_ratio": std_ratio,
                "kolmogorov_smirnov_statistic": None if ks is None else ks.statistic,
                "ks_p_value_descriptive_not_confirmatory": None if ks is None else ks.pvalue,
            },
        }
    return output


def _read_development_prices_and_actions(
    raw_root: Path, cutoff: pd.Timestamp
) -> tuple[dict[str, pd.DataFrame], dict[str, list[dict[str, Any]]]]:
    """Stream registered CSVs in date order and stop before later rows."""

    prices: dict[str, pd.DataFrame] = {}
    actions: dict[str, list[dict[str, Any]]] = {}
    for security, relative in RAW_FILES.items():
        path = raw_root / relative
        rows: list[dict[str, Any]] = []
        security_actions: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for raw in csv.DictReader(stream):
                session = pd.Timestamp(raw["Date"]).normalize()
                if session > cutoff:
                    break
                close = float(raw["Close"])
                adjusted_close = float(raw["Adj Close"])
                dividend = float(raw["Dividends"])
                split = float(raw["Stock Splits"])
                rows.append(
                    {
                        "session_date": session,
                        "close": close,
                        "adjusted_close": adjusted_close,
                    }
                )
                if dividend != 0 or split != 0:
                    security_actions.append(
                        {
                            "session_date": session,
                            "dividend": dividend,
                            "split_ratio": split,
                        }
                    )
        frame = pd.DataFrame(rows).set_index("session_date")
        if frame.empty or frame.index.max() > cutoff:
            raise RuntimeError(f"development-only raw read failed for {security}")
        prices[security] = frame
        actions[security] = security_actions
    return prices, actions


def _raw_close_proxy(
    feature: str,
    origin: pd.Timestamp,
    prices: dict[str, pd.DataFrame],
) -> float | None:
    spec = ACTION_WINDOWS[feature]
    offset = spec["session_offset"]
    try:
        if feature == "SPY_RET_5D":
            history = prices["SPY"].loc[:origin, "close"]
            return float(history.iloc[-1] / history.iloc[-1 - offset] - 1.0)
        if feature == "PEER_RET_5D":
            returns = []
            for security in ("EXPE", "BKNG"):
                history = prices[security].loc[:origin, "close"]
                returns.append(history.iloc[-1] / history.iloc[-1 - offset] - 1.0)
            return float(np.mean(returns))
        if feature == "SPY_RVOL_20D":
            history = prices["SPY"].loc[:origin, "close"]
            returns = np.diff(np.log(history.iloc[-1 - offset :].to_numpy(float)))
            return float(np.std(returns, ddof=1) * math.sqrt(252.0))
    except (IndexError, KeyError):
        return None
    raise KeyError(feature)


def corporate_action_diagnostics(
    features: pd.DataFrame,
    prices: dict[str, pd.DataFrame],
    actions: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Compare adjusted features with raw-close proxies near action dates."""

    output: dict[str, Any] = {
        "development_action_counts": {
            security: len(records) for security, records in actions.items()
        },
        "development_actions": actions,
        "features": {},
        "features_without_development_actions": [],
    }
    for feature in FEATURE_COLUMNS:
        if feature not in ACTION_WINDOWS:
            output["features_without_development_actions"].append(feature)
            continue
        spec = ACTION_WINDOWS[feature]
        records = []
        for row in features.itertuples(index=False):
            origin = pd.Timestamp(row.reference_session)
            session_history = prices[spec["securities"][0]].loc[:origin].index
            if len(session_history) <= spec["session_offset"]:
                continue
            window_start = session_history[-1 - spec["session_offset"]]
            relevant_actions = []
            for security in spec["securities"]:
                relevant_actions.extend(
                    {
                        "security": security,
                        **action,
                    }
                    for action in actions[security]
                    if window_start <= action["session_date"] <= origin
                )
            raw_proxy = _raw_close_proxy(feature, origin, prices)
            adjusted = getattr(row, feature)
            status = getattr(row, f"{feature}_STATUS")
            if status != "VALID" or pd.isna(adjusted) or raw_proxy is None:
                continue
            records.append(
                {
                    "reference_session": origin,
                    "action_exposed": bool(relevant_actions),
                    "actions": relevant_actions,
                    "adjusted_feature": float(adjusted),
                    "raw_close_proxy": raw_proxy,
                    "adjusted_minus_raw_proxy": float(adjusted) - raw_proxy,
                }
            )
        exposed = [record for record in records if record["action_exposed"]]
        unexposed = [record for record in records if not record["action_exposed"]]
        output["features"][feature] = {
            "session_offset": spec["session_offset"],
            "securities": spec["securities"],
            "valid_origins": len(records),
            "action_exposed_origins": len(exposed),
            "unexposed_origins": len(unexposed),
            "mean_absolute_adjusted_minus_raw_proxy_exposed": np.mean(
                [abs(record["adjusted_minus_raw_proxy"]) for record in exposed]
            )
            if exposed
            else None,
            "maximum_absolute_adjusted_minus_raw_proxy_exposed": max(
                (abs(record["adjusted_minus_raw_proxy"]) for record in exposed),
                default=None,
            ),
            "mean_absolute_adjusted_minus_raw_proxy_unexposed": np.mean(
                [abs(record["adjusted_minus_raw_proxy"]) for record in unexposed]
            )
            if unexposed
            else None,
            "exposed_origin_details": exposed,
        }
    return output


def _autocorrelation(values: np.ndarray, lag: int) -> float | None:
    if len(values) <= lag:
        return None
    left, right = values[:-lag], values[lag:]
    if np.std(left) == 0 or np.std(right) == 0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def _effective_sample_summary(values: pd.Series) -> dict[str, Any]:
    array = values.to_numpy(float)
    n = len(array)
    autocorrelations = {
        str(lag): _autocorrelation(array, lag)
        for lag in range(1, OVERLAP_HORIZON_MONTHS)
    }
    finite_rho = [rho for rho in autocorrelations.values() if rho is not None]
    denominator = 1.0 + 2.0 * sum(finite_rho)
    unweighted_ess = n / denominator if denominator > 0 else None
    centered = array - array.mean()
    gamma0 = float(np.dot(centered, centered) / n)
    long_run_variance = gamma0
    for lag in range(1, OVERLAP_HORIZON_MONTHS):
        gamma = float(np.dot(centered[lag:], centered[:-lag]) / n)
        weight = 1.0 - lag / OVERLAP_HORIZON_MONTHS
        long_run_variance += 2.0 * weight * gamma
    hac_ess = n * gamma0 / long_run_variance if long_run_variance > 0 else None
    return {
        "nominal_observations": n,
        "mechanical_nonoverlap_equivalent_n_over_3": n / OVERLAP_HORIZON_MONTHS,
        "nonoverlapping_phase_counts": [
            len(array[phase::OVERLAP_HORIZON_MONTHS])
            for phase in range(OVERLAP_HORIZON_MONTHS)
        ],
        "target_autocorrelation_lags_1_to_2": autocorrelations,
        "unweighted_lag_2_autocorrelation_effective_n": unweighted_ess,
        "bartlett_hac_lag_2_variance_equivalent_effective_n": hac_ess,
        "note": (
            "The N/3 quantity is the design-based overlap diagnostic. Empirical "
            "estimates are descriptive and unstable in this short sample."
        ),
    }


def effective_sample_diagnostics(
    features: pd.DataFrame, targets: pd.DataFrame
) -> dict[str, Any]:
    target_values = pd.to_numeric(targets[TARGET_COLUMN], errors="coerce")
    valid_target = targets[TARGET_STATUS_COLUMN].astype("string").eq("VALID") & np.isfinite(target_values)
    valid_targets = targets.loc[valid_target, ["reference_session"]].assign(
        target=target_values.loc[valid_target].astype(float)
    )
    complete_features = _valid_feature_frame(features).notna().all(axis=1)
    eligible_sessions = set(features.loc[complete_features, "reference_session"])
    eligible_targets = valid_targets.loc[
        valid_targets["reference_session"].isin(eligible_sessions)
    ]
    return {
        "all_valid_development_targets": _effective_sample_summary(valid_targets["target"]),
        "complete_feature_valid_development_targets": _effective_sample_summary(
            eligible_targets["target"]
        ),
        "complete_feature_eligibility_lost": len(valid_targets) - len(eligible_targets),
    }


def _write_figures(
    output_dir: Path,
    features: pd.DataFrame,
    correlations: dict[str, Any],
    stability: dict[str, Any],
    actions: dict[str, Any],
) -> list[Path]:
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "figure.dpi": 140})
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    values = _valid_feature_frame(features)
    sessions = features["reference_session"]
    period_names = features["subperiod"].drop_duplicates().tolist()
    boundaries = [
        sessions.iloc[index]
        for index in range(1, len(sessions))
        if features["subperiod"].iloc[index] != features["subperiod"].iloc[index - 1]
    ]
    written: list[Path] = []

    fig, axes = plt.subplots(2, 4, figsize=(13, 6.5), constrained_layout=True)
    for axis, feature in zip(axes.flat, FEATURE_COLUMNS, strict=True):
        valid = values[feature].dropna()
        axis.hist(valid, bins=min(12, max(5, len(valid) // 4)), color="#4472C4", alpha=0.8)
        axis.axvline(valid.median(), color="#222222", linestyle="--", linewidth=1, label="median")
        axis.set_title(feature)
        axis.set_ylabel("origins")
    fig.suptitle("Development-only feature distributions (valid values)", fontsize=12)
    path = figures_dir / "distributions.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    written.append(path)

    fig, axes = plt.subplots(4, 2, figsize=(13, 10), sharex=True, constrained_layout=True)
    for axis, feature in zip(axes.flat, FEATURE_COLUMNS, strict=True):
        valid = values[feature]
        scale = valid.std(ddof=0)
        standardized = (valid - valid.mean()) / scale if scale > 0 else valid * 0
        axis.plot(sessions, standardized, color="#4472C4", marker="o", markersize=2.5, linewidth=0.8)
        axis.plot(sessions, standardized.rolling(12, min_periods=6).mean(), color="#C44E52", linewidth=1.5, label="12-origin rolling mean")
        for boundary in boundaries:
            axis.axvline(boundary, color="#777777", linestyle=":", linewidth=0.8)
        axis.axhline(0, color="#222222", linewidth=0.5)
        axis.set_title(feature)
        axis.set_ylabel("diagnostic z-score")
    axes.flat[-1].set_xlabel("forecast origin")
    fig.suptitle("Temporal stability; full-development scaling is for display only", fontsize=12)
    path = figures_dir / "temporal_stability.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    written.append(path)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    for axis, method in zip(axes, ("pearson", "spearman"), strict=True):
        matrix = pd.DataFrame(correlations[method]).loc[FEATURE_COLUMNS, FEATURE_COLUMNS]
        image = axis.imshow(matrix, vmin=-1, vmax=1, cmap="coolwarm")
        axis.set_xticks(range(len(FEATURE_COLUMNS)), FEATURE_COLUMNS, rotation=55, ha="right")
        axis.set_yticks(range(len(FEATURE_COLUMNS)), FEATURE_COLUMNS)
        axis.set_title(method.title())
        for i in range(len(FEATURE_COLUMNS)):
            for j in range(len(FEATURE_COLUMNS)):
                axis.text(j, i, f"{matrix.iloc[i, j]:.2f}", ha="center", va="center", fontsize=6)
    fig.colorbar(image, ax=axes, shrink=0.75, label="correlation")
    fig.suptitle("Development-only pairwise correlations; pairwise valid observations", fontsize=12)
    path = figures_dir / "correlations.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    written.append(path)

    fig, axes = plt.subplots(2, 4, figsize=(14, 7), constrained_layout=True)
    for axis, feature in zip(axes.flat, FEATURE_COLUMNS, strict=True):
        samples = [
            values.loc[features["subperiod"].eq(period), feature].dropna().to_numpy()
            for period in period_names
        ]
        axis.boxplot(samples, tick_labels=[f"P{i}" for i in range(1, len(period_names) + 1)], showfliers=True)
        axis.set_title(feature)
    fig.suptitle("Feature stability across three pre-specified chronological subperiods", fontsize=12)
    path = figures_dir / "subperiod_stability.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    written.append(path)

    action_features = list(ACTION_WINDOWS)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for axis, feature in zip(axes, action_features, strict=True):
        details = actions["features"][feature]["exposed_origin_details"]
        if details:
            dates = [pd.Timestamp(record["reference_session"]) for record in details]
            differences = [record["adjusted_minus_raw_proxy"] for record in details]
            axis.axhline(0, color="#222222", linewidth=0.7)
            positions = np.arange(len(dates))
            axis.scatter(positions, differences, color="#C44E52", marker="D")
            label_step = max(1, math.ceil(len(dates) / 6))
            ticks = positions[::label_step]
            axis.set_xticks(
                ticks,
                [dates[position].strftime("%Y-%m") for position in ticks],
                rotation=45,
                ha="right",
            )
            axis.margins(x=0.12)
        else:
            axis.text(0.5, 0.5, "No exposed origins", ha="center", va="center", transform=axis.transAxes)
        axis.set_title(feature)
        axis.set_ylabel("adjusted − raw-close proxy")
    fig.suptitle("Corporate-action sensitivity at action-exposed development origins", fontsize=12)
    path = figures_dir / "corporate_action_sensitivity.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    written.append(path)
    return written


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def _format_number(value: Any, digits: int = 3) -> str:
    if value is None or not math.isfinite(float(value)):
        return "NA"
    return f"{float(value):.{digits}f}"


def _write_report(output_dir: Path, diagnostics: dict[str, Any]) -> Path:
    status_rows = []
    for feature in FEATURE_COLUMNS:
        all_period = diagnostics["missingness_and_status"][feature]["ALL"]
        status_rows.append(
            [
                feature,
                all_period["rows"],
                all_period["value_missing"],
                ", ".join(f"{key}={value}" for key, value in all_period["status_counts"].items()),
            ]
        )
    distribution_rows = []
    for feature in FEATURE_COLUMNS:
        item = diagnostics["distributions_and_extremes"][feature]
        distribution_rows.append(
            [
                feature,
                item["n_valid"],
                _format_number(item["median"]),
                f"[{_format_number(item['p05'])}, {_format_number(item['p95'])}]",
                item["tukey_extreme_count"],
            ]
        )
    stability_rows = []
    for feature in FEATURE_COLUMNS:
        item = diagnostics["subperiod_stability"][feature]["first_vs_last"]
        stability_rows.append(
            [
                feature,
                _format_number(item["standardized_mean_difference"]),
                _format_number(item["standard_deviation_ratio"]),
                _format_number(item["kolmogorov_smirnov_statistic"]),
            ]
        )
    action_rows = []
    for feature, item in diagnostics["corporate_action_sensitivity"]["features"].items():
        action_rows.append(
            [
                feature,
                item["action_exposed_origins"],
                item["valid_origins"],
                _format_number(item["mean_absolute_adjusted_minus_raw_proxy_exposed"], 6),
                _format_number(item["maximum_absolute_adjusted_minus_raw_proxy_exposed"], 6),
            ]
        )
    multicollinearity = diagnostics["correlations_and_multicollinearity"]["multicollinearity"]
    largest = diagnostics["correlations_and_multicollinearity"]["largest_absolute_pearson_pair"]
    ess_all = diagnostics["effective_sample_size"]["all_valid_development_targets"]
    ess_eligible = diagnostics["effective_sample_size"]["complete_feature_valid_development_targets"]
    report = f"""# Development-period feature diagnostics

**Scope:** {diagnostics['scope']['development_origin_start']} through {diagnostics['scope']['development_origin_end']} only ({diagnostics['scope']['origin_count']} monthly origins).  
**Interpretation:** implementation and stability diagnostics only. These checks do not establish feature predictiveness and were not used to alter the locked feature set or frozen evaluation protocol.

## Executive findings

- Missing values are status-bearing rather than silently filled. The complete eight-feature sample contains {multicollinearity['complete_case_rows']} of {diagnostics['scope']['origin_count']} origins; the loss is attributable to documented warm-up statuses.
- The largest absolute Pearson correlation is `{largest['left']}` versus `{largest['right']}` at {_format_number(largest['correlation'])}. The maximum VIF is {_format_number(multicollinearity['maximum_vif'])}, and the standardized complete-case condition number is {_format_number(multicollinearity['condition_number'])}.
- Across the frozen development targets, three-month overlap reduces the design-based non-overlap equivalent from {ess_all['nominal_observations']} to {_format_number(ess_all['mechanical_nonoverlap_equivalent_n_over_3'], 1)}. On the complete-feature subset it is {ess_eligible['nominal_observations']} to {_format_number(ess_eligible['mechanical_nonoverlap_equivalent_n_over_3'], 1)}.
- ABNB has no registered corporate action in development. The action-date sensitivity check therefore focuses on SPY and peer features and compares the locked adjusted-price feature with the same formula on raw closes; exposed-origin counts are small and descriptive.

## Missingness and statuses

{_markdown_table(['Feature', 'Rows', 'Missing', 'Status counts'], status_rows)}

Counts by each of the three fixed chronological subperiods are in `development_feature_diagnostics.json`.

## Distributions and extreme values

{_markdown_table(['Feature', 'Valid n', 'Median', '5th–95th percentile', 'Tukey extremes'], distribution_rows)}

Exact fences and dated extreme observations are in the JSON artifact. Tukey flags identify observations for implementation review; they are not deletion rules.

![Development-only feature distributions](figures/distributions.png)

## Temporal behavior and structural change

The temporal panels use full-development z-scores only for visual comparability; those scalers are not model inputs. Dashed vertical lines mark the fixed 18-origin subperiod boundaries, and the red line is a 12-origin rolling mean.

![Temporal stability](figures/temporal_stability.png)

{_markdown_table(['Feature', 'First-to-last SMD', 'SD ratio', 'KS statistic'], stability_rows)}

The JSON includes all subperiod means, standard deviations, medians, and interquartile ranges. KS p-values are retained only as descriptive diagnostics and are not predictive or confirmatory tests.

![Subperiod stability](figures/subperiod_stability.png)

## Correlations and multicollinearity

Pairwise Pearson and Spearman correlations use all jointly valid observations for each pair. VIF and condition indices use the {multicollinearity['complete_case_rows']} complete eight-feature rows. Pseudoinverse VIFs are reported so the diagnostic fails gracefully if exact singularity occurs.

![Correlation matrices](figures/correlations.png)

## Corporate-action sensitivity

{_markdown_table(['Feature', 'Exposed origins', 'Valid origins', 'Mean absolute difference', 'Max absolute difference'], action_rows)}

An origin is exposed when a registered action lies inside the exact session-offset window used by the feature. Raw-close proxies are sensitivity comparators, not candidate replacements.

![Corporate-action sensitivity](figures/corporate_action_sensitivity.png)

## Effective sample size under overlapping outcomes

| Sample | Nominal n | N/3 non-overlap equivalent | Phase counts | Lag-1 target autocorrelation | Lag-2 target autocorrelation | Bartlett HAC variance-equivalent n |
|---|---:|---:|---|---:|---:|---:|
| All valid development targets | {ess_all['nominal_observations']} | {_format_number(ess_all['mechanical_nonoverlap_equivalent_n_over_3'], 1)} | {ess_all['nonoverlapping_phase_counts']} | {_format_number(ess_all['target_autocorrelation_lags_1_to_2']['1'])} | {_format_number(ess_all['target_autocorrelation_lags_1_to_2']['2'])} | {_format_number(ess_all['bartlett_hac_lag_2_variance_equivalent_effective_n'])} |
| Complete-feature valid targets | {ess_eligible['nominal_observations']} | {_format_number(ess_eligible['mechanical_nonoverlap_equivalent_n_over_3'], 1)} | {ess_eligible['nonoverlapping_phase_counts']} | {_format_number(ess_eligible['target_autocorrelation_lags_1_to_2']['1'])} | {_format_number(ess_eligible['target_autocorrelation_lags_1_to_2']['2'])} | {_format_number(ess_eligible['bartlett_hac_lag_2_variance_equivalent_effective_n'])} |

The N/3 figure is the design-based headline. Empirical autocorrelation/HAC equivalents can move materially in short samples and are reported only as sensitivity diagnostics.

## Reproducibility and limitations

- Final-test and post-test rows were excluded in the Arrow scan before materialization. No final-test feature or target value was read into the diagnostic process.
- Corporate-action comparison uses only registered rows through the development cutoff and stops streaming each source at the first later date.
- Inputs remain development-only because point-in-time adjustment evidence and usage rights are unresolved. See `../../validation/DATA_LIMITATIONS.md`.
- Full numerical results, definitions, input hashes, code revision, and build metadata are in `development_feature_diagnostics.json` and `artifact_manifest.json`.
"""
    path = output_dir / "DEVELOPMENT_FEATURE_DIAGNOSTICS.md"
    path.write_text(report, encoding="utf-8")
    return path


def run_feature_diagnostics(
    *,
    feature_path: Path | str = DEFAULT_FEATURE_PATH,
    target_path: Path | str = DEFAULT_TARGET_PATH,
    protocol_path: Path | str = DEFAULT_PROTOCOL_PATH,
    raw_root: Path | str = DEFAULT_RAW_ROOT,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> dict[str, Path]:
    """Run and persist all development-only diagnostic outputs."""

    feature_path = Path(feature_path).resolve()
    target_path = Path(target_path).resolve()
    protocol_path = Path(protocol_path).resolve()
    raw_root = Path(raw_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    features, targets, protocol, cutoff = load_development_inputs(
        feature_path, target_path, protocol_path
    )
    features["subperiod"] = assign_subperiods(features["reference_session"])
    prices, actions = _read_development_prices_and_actions(raw_root, cutoff)
    correlations = correlation_diagnostics(features)
    stability = stability_diagnostics(features)
    action_results = corporate_action_diagnostics(features, prices, actions)
    revision, dirty = _repository_state()
    diagnostics = {
        "artifact_id": "DIAG-DEV-FEATURES-001",
        "schema_version": 1,
        "purpose": "implementation and stability diagnostics; not evidence of predictiveness",
        "scope": {
            "partition": "DEVELOPMENT",
            "development_origin_start": features["reference_session"].min(),
            "development_origin_end": features["reference_session"].max(),
            "origin_count": len(features),
            "final_test_rows_materialized": 0,
            "subperiod_rule": "three contiguous equal 18-origin blocks fixed before value inspection",
            "subperiods": features.groupby("subperiod", sort=False)["reference_session"]
            .agg(["min", "max", "count"])
            .reset_index()
            .to_dict(orient="records"),
        },
        "methodology": {
            "extremes": "Tukey 1.5 IQR fences on valid values",
            "correlations": "pairwise-valid Pearson and Spearman",
            "multicollinearity": "complete-case VIF and standardized condition indices",
            "structural_change": "fixed-subperiod summaries, first-vs-last SMD, SD ratio, and KS statistic",
            "corporate_actions": "exact feature lookback exposure plus adjusted-minus-raw-close formula proxy",
            "overlap": "N/3 design diagnostic and lag-2 empirical autocorrelation/HAC sensitivity",
        },
        "inputs": {
            "monthly_features": {"path": feature_path, "sha256": _sha256(feature_path)},
            "monthly_targets": {"path": target_path, "sha256": _sha256(target_path)},
            "evaluation_protocol": {"path": protocol_path, "sha256": _sha256(protocol_path)},
            "protocol_id": protocol["protocol_id"],
            "raw_source_hashes": {
                security: _sha256(raw_root / relative) for security, relative in RAW_FILES.items()
            },
        },
        "missingness_and_status": status_diagnostics(features),
        "distributions_and_extremes": distribution_diagnostics(features),
        "correlations_and_multicollinearity": correlations,
        "subperiod_stability": stability,
        "corporate_action_sensitivity": action_results,
        "effective_sample_size": effective_sample_diagnostics(features, targets),
        "provenance": {
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "code_revision": revision,
            "code_dirty": dirty,
            "development_cutoff_enforced": cutoff,
        },
    }
    diagnostics = _json_value(diagnostics)
    json_path = output_dir / "development_feature_diagnostics.json"
    json_path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    figures = _write_figures(output_dir, features, correlations, stability, action_results)
    report_path = _write_report(output_dir, diagnostics)
    output_files = [json_path, report_path, *figures]
    manifest = {
        "artifact_id": diagnostics["artifact_id"],
        "created_at_utc": diagnostics["provenance"]["built_at_utc"],
        "files": {
            path.relative_to(output_dir).as_posix(): {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in output_files
        },
    }
    manifest_path = output_dir / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "report": report_path,
        "diagnostics": json_path,
        "manifest": manifest_path,
        **{path.stem: path for path in figures},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGET_PATH)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()
    outputs = run_feature_diagnostics(
        feature_path=arguments.features,
        target_path=arguments.targets,
        protocol_path=arguments.protocol,
        raw_root=arguments.raw_root,
        output_dir=arguments.output_dir,
    )
    print(f"Wrote {outputs['report']}")
    print(f"Wrote {outputs['diagnostics']}")
    print(f"Wrote {outputs['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
