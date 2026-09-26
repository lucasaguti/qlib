"""Construct point-in-time three-calendar-month ABNB return targets."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import exchange_calendars as xcals
import pandas as pd

from research.abnb.pipeline.daily_features import (
    _canonical_json,
    _repository_state,
    _sha256,
)
from research.abnb.pipeline.monthly_features import _temporal_contract
from research.abnb.pipeline.panel import (
    CALENDAR_LIBRARY,
    CALENDAR_NAME,
    CALENDAR_VERSION,
    INVALID_PRICE,
    MISSING_SOURCE,
    UNAVAILABLE_BY_CUTOFF,
    VALID,
    build_daily_panel,
)

TARGET_COLUMN = "ABNB_RETURN_3M"
TARGET_STATUS_COLUMN = f"{TARGET_COLUMN}_STATUS"
REFERENCE_PRICE_COLUMN = "reference_adjusted_close"
MATURITY_PRICE_COLUMN = "maturity_adjusted_close"

TARGET_VALID = VALID
IMMATURE = "IMMATURE"
WITHHELD_BY_PROTOCOL = "WITHHELD_BY_PROTOCOL"
REFERENCE_MISSING_SOURCE = "REFERENCE_MISSING_SOURCE"
REFERENCE_INVALID_PRICE = "REFERENCE_INVALID_PRICE"
REFERENCE_UNAVAILABLE_BY_CUTOFF = "REFERENCE_UNAVAILABLE_BY_CUTOFF"
MATURITY_MISSING_SOURCE = "MATURITY_MISSING_SOURCE"
MATURITY_INVALID_PRICE = "MATURITY_INVALID_PRICE"
MATURITY_UNAVAILABLE_BY_CUTOFF = "MATURITY_UNAVAILABLE_BY_CUTOFF"

TARGET_STATUSES = (
    TARGET_VALID,
    IMMATURE,
    WITHHELD_BY_PROTOCOL,
    REFERENCE_MISSING_SOURCE,
    REFERENCE_INVALID_PRICE,
    REFERENCE_UNAVAILABLE_BY_CUTOFF,
    MATURITY_MISSING_SOURCE,
    MATURITY_INVALID_PRICE,
    MATURITY_UNAVAILABLE_BY_CUTOFF,
)

DEFAULT_PROTOCOL_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "evaluation_protocol.json"
)
DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "interim" / "monthly_targets.parquet"
)
DEFAULT_RAW_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"


def _utc_timestamp(value: Any, name: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError(f"{name} must be a timezone-aware timestamp")
    return timestamp.tz_convert("UTC")


def _session_index(values: Iterable[Any], name: str) -> pd.DatetimeIndex:
    parsed = pd.to_datetime(list(values), errors="coerce")
    if parsed.isna().any():
        raise ValueError(f"{name} contains an invalid session")
    sessions = pd.DatetimeIndex(parsed)
    if sessions.tz is not None:
        sessions = sessions.tz_convert("UTC").tz_localize(None)
    return sessions.normalize()


def _validate_origins(origins: pd.DataFrame) -> pd.DataFrame:
    required = {
        "reference_session",
        "issued_at_utc",
        "maturity_session",
        "label_available_at",
    }
    missing = sorted(required.difference(origins.columns))
    if missing:
        raise ValueError(f"origins are missing columns: {missing}")

    result = origins.copy().reset_index(drop=True)
    result["reference_session"] = _session_index(
        result["reference_session"], "reference_session"
    )
    result["maturity_session"] = _session_index(
        result["maturity_session"], "maturity_session"
    )
    for column in ("issued_at_utc", "label_available_at"):
        values = pd.to_datetime(result[column], errors="coerce", utc=True)
        if values.isna().any():
            raise ValueError(f"{column} contains an invalid timestamp")
        result[column] = values

    if result["reference_session"].duplicated().any():
        raise ValueError("reference sessions must be unique")
    if not result["reference_session"].is_monotonic_increasing:
        raise ValueError("reference sessions must be increasing")
    if (result["maturity_session"] <= result["reference_session"]).any():
        raise ValueError("every maturity session must follow its reference session")
    return result


def _validate_abnb_prices(prices: pd.DataFrame) -> pd.DataFrame:
    required = {"adjusted_close", "status"}
    missing = sorted(required.difference(prices.columns))
    if missing:
        raise ValueError(f"ABNB prices are missing columns: {missing}")
    if isinstance(prices.index, pd.MultiIndex):
        if prices.index.names != ["session_date", "security"]:
            raise ValueError(
                "price panel must use a (session_date, security) MultiIndex"
            )
        securities = prices.index.get_level_values("security").unique()
        if "ABNB" not in securities:
            raise ValueError("price panel does not contain ABNB")
        prices = prices.xs("ABNB", level="security")
    result = prices.copy()
    result.index = _session_index(result.index, "ABNB price index")
    if result.index.has_duplicates or not result.index.is_monotonic_increasing:
        raise ValueError("ABNB price sessions must be unique and increasing")
    return result


def _unavailable_status(prefix: str, source_status: Any) -> str:
    mapping = {
        MISSING_SOURCE: f"{prefix}_MISSING_SOURCE",
        INVALID_PRICE: f"{prefix}_INVALID_PRICE",
        UNAVAILABLE_BY_CUTOFF: f"{prefix}_UNAVAILABLE_BY_CUTOFF",
    }
    return mapping.get(str(source_status), f"{prefix}_INVALID_PRICE")


def construct_three_month_targets(
    origins: pd.DataFrame,
    abnb_prices: pd.DataFrame,
    *,
    observed_as_of_utc: Any,
    withheld_reference_sessions: Iterable[Any] = (),
) -> pd.DataFrame:
    """Attach adjusted-return labels without exposing immature/withheld outcomes.

    The function reads only the exact reference and maturity sessions needed by
    each unprotected, mature origin. It never fills a missing price or changes
    the calendar-derived maturity.
    """

    table = _validate_origins(origins)
    prices = _validate_abnb_prices(abnb_prices)
    observed_as_of = _utc_timestamp(observed_as_of_utc, "observed_as_of_utc")
    withheld = set(
        _session_index(withheld_reference_sessions, "withheld_reference_sessions")
    )

    reference_prices: list[float | None] = []
    maturity_prices: list[float | None] = []
    targets: list[float | None] = []
    statuses: list[str] = []

    for row in table.itertuples(index=False):
        reference_session = row.reference_session
        maturity_session = row.maturity_session
        label_available_at = row.label_available_at

        if reference_session in withheld:
            reference_prices.append(None)
            maturity_prices.append(None)
            targets.append(None)
            statuses.append(WITHHELD_BY_PROTOCOL)
            continue

        reference = (
            prices.loc[reference_session]
            if reference_session in prices.index
            else None
        )
        reference_price = None if reference is None else reference["adjusted_close"]
        reference_prices.append(
            float(reference_price)
            if pd.notna(reference_price) and math.isfinite(float(reference_price))
            else None
        )

        if reference is None:
            maturity_prices.append(None)
            targets.append(None)
            statuses.append(REFERENCE_MISSING_SOURCE)
            continue
        if str(reference["status"]) != VALID:
            maturity_prices.append(None)
            targets.append(None)
            statuses.append(_unavailable_status("REFERENCE", reference["status"]))
            continue

        if label_available_at > observed_as_of:
            maturity_prices.append(None)
            targets.append(None)
            statuses.append(IMMATURE)
            continue

        maturity = (
            prices.loc[maturity_session]
            if maturity_session in prices.index
            else None
        )
        maturity_price = None if maturity is None else maturity["adjusted_close"]
        maturity_prices.append(
            float(maturity_price)
            if pd.notna(maturity_price) and math.isfinite(float(maturity_price))
            else None
        )
        if maturity is None:
            targets.append(None)
            statuses.append(MATURITY_MISSING_SOURCE)
            continue
        if str(maturity["status"]) != VALID:
            targets.append(None)
            statuses.append(_unavailable_status("MATURITY", maturity["status"]))
            continue

        reference_value = float(reference["adjusted_close"])
        maturity_value = float(maturity["adjusted_close"])
        if not math.isfinite(reference_value) or reference_value <= 0:
            targets.append(None)
            statuses.append(REFERENCE_INVALID_PRICE)
            continue
        if not math.isfinite(maturity_value) or maturity_value <= 0:
            targets.append(None)
            statuses.append(MATURITY_INVALID_PRICE)
            continue
        targets.append(maturity_value / reference_value - 1.0)
        statuses.append(TARGET_VALID)

    table[REFERENCE_PRICE_COLUMN] = pd.array(reference_prices, dtype="Float64")
    table[MATURITY_PRICE_COLUMN] = pd.array(maturity_prices, dtype="Float64")
    table[TARGET_COLUMN] = pd.array(targets, dtype="Float64")
    table[TARGET_STATUS_COLUMN] = pd.Categorical(
        statuses, categories=TARGET_STATUSES
    )
    table["target_observed_as_of_utc"] = observed_as_of
    table.attrs = {
        "schema_version": 1,
        "target": TARGET_COLUMN,
        "formula": "maturity_adjusted_close / reference_adjusted_close - 1",
        "horizon": "three calendar months; final XNYS session",
        "price_field": "adjusted_close",
        "target_statuses": list(TARGET_STATUSES),
        "target_observed_as_of_utc": observed_as_of.isoformat(),
    }
    return table


def select_matured_training_targets(
    targets: pd.DataFrame, *, issued_at_utc: Any
) -> pd.DataFrame:
    """Return only valid labels available by one walk-forward issuance time."""

    issuance = _utc_timestamp(issued_at_utc, "issued_at_utc")
    required = {"label_available_at", TARGET_COLUMN, TARGET_STATUS_COLUMN}
    missing = sorted(required.difference(targets.columns))
    if missing:
        raise ValueError(f"target table is missing columns: {missing}")
    availability = pd.to_datetime(
        targets["label_available_at"], errors="coerce", utc=True
    )
    if availability.isna().any():
        raise ValueError("target table contains an invalid label_available_at")
    values = pd.to_numeric(targets[TARGET_COLUMN], errors="coerce")
    finite = values.map(lambda value: pd.notna(value) and math.isfinite(value))
    eligible = (
        availability.le(issuance)
        & targets[TARGET_STATUS_COLUMN].astype("string").eq(TARGET_VALID)
        & finite
    )
    return targets.loc[eligible].copy()


def _protocol_partitions(
    protocol: dict[str, Any],
) -> tuple[pd.Timestamp, set[pd.Timestamp]]:
    periods = protocol["periods"]
    development_end = pd.Timestamp(periods["development_origin_end"])
    final_sessions = set(
        _session_index(
            periods["final_test_reference_sessions"],
            "final_test_reference_sessions",
        )
    )
    return development_end, final_sessions


def _scheduled_origins(first_observation: Any, last_observation: Any) -> pd.DataFrame:
    calendar = xcals.get_calendar(CALENDAR_NAME)
    first_session = pd.Timestamp(first_observation).normalize()
    last_session = pd.Timestamp(last_observation).normalize()
    periods = pd.period_range(
        first_session.to_period("M"), last_session.to_period("M"), freq="M"
    )
    reference_sessions: list[pd.Timestamp] = []
    for period in periods:
        sessions = calendar.sessions_in_range(
            period.start_time, period.end_time.normalize()
        )
        month_end = pd.Timestamp(sessions[-1]).tz_localize(None)
        if month_end <= last_session:
            reference_sessions.append(month_end)
    timing = _temporal_contract(pd.DatetimeIndex(reference_sessions), calendar)
    timing.insert(0, "calendar_month", timing["reference_session"].dt.strftime("%Y-%m"))
    return timing


def build_monthly_target_table(
    *,
    raw_root: Path | str = DEFAULT_RAW_ROOT,
    protocol_path: Path | str = DEFAULT_PROTOCOL_PATH,
) -> pd.DataFrame:
    """Build development labels while leaving the frozen final test unread."""

    raw_root = Path(raw_root).resolve()
    protocol_path = Path(protocol_path).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    development_end, final_sessions = _protocol_partitions(protocol)

    manifest_path = raw_root / "Dataset1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    origins = _scheduled_origins(
        manifest["first_observation"], manifest["last_observation"]
    )
    development = origins.loc[origins["reference_session"].le(development_end)]
    development_price_end = development["maturity_session"].max()
    panel = build_daily_panel(
        raw_root,
        start=origins["reference_session"].min(),
        end=development_price_end,
    )

    calendar = xcals.get_calendar(CALENDAR_NAME)
    observed_as_of = calendar.session_close(
        pd.Timestamp(manifest["last_observation"])
    ).tz_convert("UTC")
    protected = set(
        origins.loc[
            origins["reference_session"].gt(development_end), "reference_session"
        ]
    )
    table = construct_three_month_targets(
        origins,
        panel,
        observed_as_of_utc=observed_as_of,
        withheld_reference_sessions=protected,
    )
    post_test_start = pd.Timestamp(
        protocol["periods"]["post_test_quarantine_origin_start"]
    )
    table["evaluation_partition"] = "DEVELOPMENT"
    table.loc[
        table["reference_session"].isin(final_sessions), "evaluation_partition"
    ] = "FINAL_TEST"
    table.loc[
        table["reference_session"].ge(post_test_start), "evaluation_partition"
    ] = "POST_TEST_QUARANTINE"
    # Post-test rows are unavailable on temporal grounds, not merely protected.
    post_test = table["evaluation_partition"].eq("POST_TEST_QUARANTINE")
    table.loc[post_test, TARGET_STATUS_COLUMN] = IMMATURE

    revision, dirty = _repository_state()
    provenance = {
        "research_readiness": "DEVELOPMENT_ONLY",
        "calendar_name": CALENDAR_NAME,
        "calendar_library": CALENDAR_LIBRARY,
        "calendar_version": CALENDAR_VERSION,
        "source_id": "SRC-ABNB-001",
        "parent_abnb_sha256": manifest["sha256"],
        "parent_manifest_sha256": _sha256(manifest_path),
        "evaluation_protocol_id": protocol["protocol_id"],
        "evaluation_protocol_version": protocol["version"],
        "evaluation_protocol_sha256": _sha256(protocol_path),
        "price_read_end_session": development_price_end.strftime("%Y-%m-%d"),
        "target_build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target_code_revision": revision,
        "target_code_dirty": dirty,
        "final_test_access": "WITHHELD; no final-test target prices read",
    }
    for column, value in provenance.items():
        table[column] = value
    table.attrs.update(provenance)
    table.attrs["withheld_final_test_reference_sessions"] = _canonical_json(
        sorted(session.strftime("%Y-%m-%d") for session in final_sessions)
    )
    return table


def write_monthly_target_table(
    table: pd.DataFrame, output_path: Path | str = DEFAULT_OUTPUT_PATH
) -> Path:
    """Atomically persist the target table."""

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        table.to_parquet(temporary, engine="pyarrow", index=False)
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def build_monthly_target_artifact(
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
    *,
    raw_root: Path | str = DEFAULT_RAW_ROOT,
    protocol_path: Path | str = DEFAULT_PROTOCOL_PATH,
) -> Path:
    table = build_monthly_target_table(
        raw_root=raw_root, protocol_path=protocol_path
    )
    return write_monthly_target_table(table, output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    arguments = parser.parse_args()
    output = build_monthly_target_artifact(
        arguments.output,
        raw_root=arguments.raw_root,
        protocol_path=arguments.protocol,
    )
    print(f"Wrote {output} ({_sha256(output)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
