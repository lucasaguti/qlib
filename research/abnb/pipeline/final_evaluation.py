"""Authorization-gated single-pass evaluation of the frozen ABNB final test."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import exchange_calendars as xcals
import pandas as pd
import pyarrow.dataset as ds

from research.abnb.pipeline.daily_features import FEATURE_COLUMNS, _repository_state, _sha256
from research.abnb.pipeline.evaluation import (
    _json_value,
    _write_report,
    evaluate_forecasts,
    walk_forward_forecasts,
)
from research.abnb.pipeline.panel import CALENDAR_NAME, build_daily_panel
from research.abnb.pipeline.targets import (
    TARGET_COLUMN,
    TARGET_STATUS_COLUMN,
    _protocol_partitions,
    _scheduled_origins,
    construct_three_month_targets,
    write_monthly_target_table,
)

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FEATURE_PATH = ROOT / "data" / "interim" / "monthly_features.parquet"
DEFAULT_DAILY_FEATURE_PATH = ROOT / "data" / "interim" / "daily_features.parquet"
DEFAULT_PROTOCOL_PATH = ROOT / "config" / "evaluation_protocol.json"
DEFAULT_RAW_ROOT = ROOT / "data" / "raw"
DEFAULT_TARGET_PATH = ROOT / "data" / "snapshots" / "final_test_targets.parquet"
DEFAULT_OUTPUT_DIR = ROOT / "evaluation" / "final_test"
AUTHORIZATION_PHRASE = "I AUTHORIZE THE FROZEN FINAL TEST"


def _session_set(values: Iterable[Any]) -> set[pd.Timestamp]:
    return {pd.Timestamp(value).tz_localize(None).normalize() for value in values}


def build_final_target_snapshot(
    *,
    raw_root: Path,
    protocol_path: Path,
    output_path: Path,
) -> Path:
    """Construct development plus frozen-final targets, excluding quarantine rows."""

    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    development_end, final_sessions = _protocol_partitions(protocol)
    configured_final = _session_set(protocol["periods"]["final_test_reference_sessions"])
    if final_sessions != configured_final:
        raise ValueError("final-test session parsing is inconsistent")
    if len(final_sessions) != int(protocol["periods"]["final_test_origin_count"]):
        raise ValueError("final-test session count differs from the frozen protocol")

    manifest_path = raw_root / "Dataset1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_origins = _scheduled_origins(
        manifest["first_observation"], manifest["last_observation"]
    )
    final_end = pd.Timestamp(protocol["periods"]["final_test_origin_end"])
    origins = all_origins.loc[all_origins["reference_session"].le(final_end)].copy()
    actual_final = set(
        origins.loc[
            origins["reference_session"].gt(development_end), "reference_session"
        ]
    )
    if actual_final != final_sessions:
        raise ValueError("calendar-derived final-test sessions differ from the protocol")

    panel = build_daily_panel(
        raw_root,
        start=origins["reference_session"].min(),
        end=origins["maturity_session"].max(),
    )
    calendar = xcals.get_calendar(CALENDAR_NAME)
    observed_as_of = calendar.session_close(
        pd.Timestamp(manifest["last_observation"])
    ).tz_convert("UTC")
    targets = construct_three_month_targets(
        origins,
        panel,
        observed_as_of_utc=observed_as_of,
    )
    targets["evaluation_partition"] = "DEVELOPMENT"
    targets.loc[
        targets["reference_session"].isin(final_sessions), "evaluation_partition"
    ] = "FINAL_TEST"
    targets["research_readiness"] = (
        "USER_AUTHORIZED_FINAL_USE_WITH_UNRESOLVED_SOURCE_LIMITATIONS"
    )
    targets["evaluation_protocol_sha256"] = _sha256(protocol_path)
    targets["parent_abnb_sha256"] = manifest["sha256"]
    targets["final_test_access"] = "AUTHORIZED_SINGLE_PASS"
    return write_monthly_target_table(targets, output_path)


def load_final_evaluation_inputs(
    *,
    feature_path: Path,
    target_path: Path,
    protocol_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load exactly development plus the frozen final block and validate the join."""

    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if tuple(protocol["eligibility"]["required_feature_names"]) != FEATURE_COLUMNS:
        raise ValueError("protocol feature order differs from the locked feature set")
    final_sessions = _session_set(protocol["periods"]["final_test_reference_sessions"])
    final_end = pd.Timestamp(protocol["periods"]["final_test_origin_end"])
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
    features = ds.dataset(feature_path, format="parquet").to_table(
        columns=feature_columns,
        filter=ds.field("reference_session") <= final_end.to_datetime64(),
    ).to_pandas()
    targets = ds.dataset(target_path, format="parquet").to_table(
        columns=target_columns,
        filter=ds.field("reference_session") <= final_end.to_datetime64(),
    ).to_pandas()
    for frame, name in ((features, "features"), (targets, "targets")):
        frame["reference_session"] = pd.to_datetime(
            frame["reference_session"], errors="raise"
        ).dt.normalize()
        if frame["reference_session"].duplicated().any():
            raise ValueError(f"{name} contain duplicate reference sessions")
    if set(targets["evaluation_partition"].unique()) != {"DEVELOPMENT", "FINAL_TEST"}:
        raise ValueError("target snapshot contains an unexpected partition")
    if set(
        targets.loc[
            targets["evaluation_partition"].eq("FINAL_TEST"), "reference_session"
        ]
    ) != final_sessions:
        raise ValueError("target snapshot does not contain the exact frozen final block")
    table = features.merge(
        targets,
        on="reference_session",
        how="inner",
        validate="one_to_one",
        suffixes=("_feature", "_target"),
    )
    if len(table) != len(features) or len(table) != len(targets):
        raise ValueError("feature and target origins do not match")
    feature_issuance = pd.to_datetime(table.pop("issued_at_utc_feature"), utc=True)
    target_issuance = pd.to_datetime(table.pop("issued_at_utc_target"), utc=True)
    if not feature_issuance.equals(target_issuance):
        raise ValueError("feature and target issuance times do not match")
    table.insert(1, "issued_at_utc", feature_issuance)
    table["label_available_at"] = pd.to_datetime(
        table["label_available_at"], errors="raise", utc=True
    )
    return table.sort_values("reference_session").reset_index(drop=True), protocol


def _source_inventory(raw_root: Path) -> dict[str, dict[str, Any]]:
    files = {
        "SRC-ABNB-001": raw_root / "Dataset1" / "ABNB_daily.csv",
        "SRC-BKNG-001": raw_root / "Dataset2" / "BKNG_daily.csv",
        "SRC-EXPE-001": raw_root / "Dataset2" / "EXPE_daily.csv",
        "SRC-SPY-001": raw_root / "Dataset2" / "SPY_daily.csv",
        "Dataset1 manifest": raw_root / "Dataset1" / "manifest.json",
        "Dataset2 manifest": raw_root / "Dataset2" / "manifest.json",
    }
    return {
        name: {"path": path, "sha256": _sha256(path), "bytes": path.stat().st_size}
        for name, path in files.items()
    }


def _classify_primary_finding(results: dict[str, Any]) -> dict[str, str]:
    """Apply a conservative result label fixed before final-test access."""

    primary = results["paired_comparisons"][
        "ridge_minus_expanding_average_squared_error"
    ]
    lower, upper = primary["primary_block_bootstrap_95_interval"]
    p_value = primary["p_value"]
    if upper < 0 and p_value < 0.05:
        label = "POSITIVE"
        rationale = "Ridge has lower squared error by both the 95% block interval and HAC(2) test."
    elif lower > 0 and p_value < 0.05:
        label = "NEGATIVE"
        rationale = "Ridge has higher squared error by both the 95% block interval and HAC(2) test."
    else:
        label = "INCONCLUSIVE"
        rationale = "The 95% block interval or HAC(2) test does not establish a directional difference."
    return {"label": label, "rule": rationale}


def run_final_evaluation(
    *,
    authorization: str,
    feature_path: Path | str = DEFAULT_FEATURE_PATH,
    daily_feature_path: Path | str = DEFAULT_DAILY_FEATURE_PATH,
    protocol_path: Path | str = DEFAULT_PROTOCOL_PATH,
    raw_root: Path | str = DEFAULT_RAW_ROOT,
    target_path: Path | str = DEFAULT_TARGET_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> dict[str, Path]:
    if authorization != AUTHORIZATION_PHRASE:
        raise PermissionError("exact final-test authorization phrase is required")

    feature_path = Path(feature_path).resolve()
    daily_feature_path = Path(daily_feature_path).resolve()
    protocol_path = Path(protocol_path).resolve()
    raw_root = Path(raw_root).resolve()
    target_path = Path(target_path).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("final-test output directory is not empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    access_started_at = datetime.now(timezone.utc)

    build_final_target_snapshot(
        raw_root=raw_root,
        protocol_path=protocol_path,
        output_path=target_path,
    )
    table, protocol = load_final_evaluation_inputs(
        feature_path=feature_path,
        target_path=target_path,
        protocol_path=protocol_path,
    )
    final_sessions = protocol["periods"]["final_test_reference_sessions"]
    forecasts = walk_forward_forecasts(
        table,
        protocol,
        forecast_sessions=final_sessions,
        include_ablations=True,
    )
    if set(forecasts["reference_session"]) != _session_set(final_sessions):
        raise ValueError("forecast output differs from the frozen final-test sessions")
    results = evaluate_forecasts(forecasts, protocol)
    finding = _classify_primary_finding(results)
    revision, dirty = _repository_state()
    code_files = [
        REPOSITORY_ROOT / "research" / "abnb" / "pipeline" / name
        for name in ("final_evaluation.py", "evaluation.py", "targets.py")
    ]
    artifact = _json_value(
        {
            "artifact_id": "EVAL-FINAL-001",
            "schema_version": 1,
            "scope": "FROZEN_CONFIRMATORY_FINAL_TEST",
            "authorization": {
                "actor": "user",
                "received_in_session": True,
                "phrase": AUTHORIZATION_PHRASE,
            },
            "access_started_at_utc": access_started_at,
            "results": results,
            "finding_classification": finding,
            "inputs": {
                "source_files": _source_inventory(raw_root),
                "monthly_features": {
                    "path": feature_path,
                    "sha256": _sha256(feature_path),
                },
                "daily_features": {
                    "path": daily_feature_path,
                    "sha256": _sha256(daily_feature_path),
                },
                "final_targets": {
                    "path": target_path,
                    "sha256": _sha256(target_path),
                },
                "evaluation_protocol": {
                    "path": protocol_path,
                    "sha256": _sha256(protocol_path),
                },
            },
            "provenance": {
                "built_at_utc": datetime.now(timezone.utc),
                "code_revision": revision,
                "code_dirty": dirty,
                "code_sha256": {
                    path.relative_to(REPOSITORY_ROOT).as_posix(): _sha256(path)
                    for path in code_files
                },
                "source_limitations": (
                    "User-authorized execution; provider rights and historical point-in-time "
                    "price/adjustment availability evidence remain unresolved."
                ),
            },
        }
    )

    results_path = output_dir / "final_test_evaluation.json"
    results_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    report_path = output_dir / "FINAL_TEST_EVALUATION.md"
    _write_report(
        report_path,
        artifact,
        title="Frozen Final-Test Expanding-Window Forecast Evaluation",
        notice=(
            "This is the single authorized evaluation of EVAL-PROTOCOL-001's frozen",
            "12-origin final block. The methodology was not changed after access.",
            "Provider-rights and historical point-in-time evidence remain unresolved limitations.",
        ),
        interpretation=(
            "Interpret the statistical result together with the 12-origin sample size,",
            "overlapping three-month outcomes, and the unresolved source-provenance",
            "limitations. No feature, model, threshold, or preprocessing redesign follows",
            "from this final-test result.",
        ),
    )
    report_text = report_path.read_text(encoding="utf-8")
    report_text = report_text.replace(
        "Scored origins:",
        f"Primary finding: **{finding['label']}** — {finding['rule']}\n\nScored origins:",
        1,
    )
    report_path.write_text(report_text, encoding="utf-8")
    predictions_path = output_dir / "final_test_predictions.csv"
    forecasts.to_csv(predictions_path, index=False)
    manifest = {
        "artifact_id": artifact["artifact_id"],
        "created_at_utc": artifact["provenance"]["built_at_utc"],
        "files": {
            (
                path.relative_to(output_dir).as_posix()
                if path.is_relative_to(output_dir)
                else path.relative_to(REPOSITORY_ROOT).as_posix()
            ): {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in (results_path, report_path, predictions_path, target_path)
        },
    }
    manifest_path = output_dir / "artifact_manifest.json"
    manifest_path.write_text(
        json.dumps(_json_value(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "report": report_path,
        "results": results_path,
        "predictions": predictions_path,
        "targets": target_path,
        "manifest": manifest_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--daily-features", type=Path, default=DEFAULT_DAILY_FEATURE_PATH)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGET_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()
    outputs = run_final_evaluation(
        authorization=arguments.authorization,
        feature_path=arguments.features,
        daily_feature_path=arguments.daily_features,
        protocol_path=arguments.protocol,
        raw_root=arguments.raw_root,
        target_path=arguments.targets,
        output_dir=arguments.output_dir,
    )
    for path in outputs.values():
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
