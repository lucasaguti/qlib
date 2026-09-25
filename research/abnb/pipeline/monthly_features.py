"""Sample precomputed daily ABNB features at completed calendar month-ends."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pandas as pd

from research.abnb.pipeline.daily_features import (
    DEFAULT_OUTPUT_PATH as DEFAULT_DAILY_PATH,
)
from research.abnb.pipeline.daily_features import (
    FEATURE_COLUMNS,
    STATUS_COLUMNS,
    _repository_state,
    _sha256,
)

DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "interim"
    / "monthly_features.parquet"
)
SAMPLING_RULE = "final XNYS session of each completed calendar month"


def _single_value(table: pd.DataFrame, column: str) -> Any:
    if column not in table:
        raise ValueError(f"daily feature table is missing {column!r}")
    values = table[column].drop_duplicates()
    if len(values) != 1:
        raise ValueError(f"daily feature column {column!r} must be invariant")
    return values.iloc[0]


def _validated_sessions(table: pd.DataFrame) -> tuple[pd.DatetimeIndex, Any]:
    required = {"session_date", *FEATURE_COLUMNS, *STATUS_COLUMNS}
    missing = sorted(required.difference(table.columns))
    if missing:
        raise ValueError(f"daily feature table is missing columns: {missing}")

    parsed = pd.to_datetime(table["session_date"], errors="coerce")
    if parsed.isna().any():
        raise ValueError("daily feature table contains an invalid session_date")
    sessions = pd.DatetimeIndex(parsed)
    if sessions.tz is not None:
        sessions = sessions.tz_convert("UTC").tz_localize(None)
    sessions = sessions.normalize()
    if sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise ValueError("daily feature sessions must be unique and increasing")

    calendar_name = str(_single_value(table, "calendar_name"))
    calendar_library = str(_single_value(table, "calendar_library"))
    calendar_version = str(_single_value(table, "calendar_version"))
    if calendar_library != "exchange-calendars":
        raise ValueError(f"Unsupported calendar library: {calendar_library!r}")
    installed_version = version(calendar_library)
    if installed_version != calendar_version:
        raise RuntimeError(
            f"Monthly sampling requires {calendar_library}=={calendar_version}; "
            f"found {installed_version}"
        )
    calendar = xcals.get_calendar(calendar_name)
    expected = calendar.sessions_in_range(sessions[0], sessions[-1])
    expected = pd.DatetimeIndex(expected).tz_localize(None).normalize()
    if not sessions.equals(expected):
        raise ValueError(
            "daily feature table must contain every calendar session in its coverage"
        )
    return sessions, calendar


def sample_monthly_features(daily_features: pd.DataFrame) -> pd.DataFrame:
    """Select existing daily rows at completed XNYS month-ends.

    No feature is calculated here. A partial terminal month is excluded unless
    its actual final XNYS session is present in the daily table.
    """

    sessions, calendar = _validated_sessions(daily_features)
    selected_positions: list[int] = []
    periods = sessions.to_period("M")
    for period in periods.unique():
        month_sessions = calendar.sessions_in_range(
            period.start_time, period.end_time.normalize()
        )
        expected_month_end = pd.Timestamp(month_sessions[-1]).tz_localize(None)
        matches = sessions.get_indexer([expected_month_end])
        if matches[0] != -1:
            selected_positions.append(int(matches[0]))

    monthly = daily_features.iloc[selected_positions].copy().reset_index(drop=True)
    monthly.insert(
        1,
        "calendar_month",
        pd.DatetimeIndex(monthly["session_date"]).strftime("%Y-%m"),
    )
    monthly.attrs = {
        "schema_version": 1,
        "artifact_role": "development-only interim monthly feature table",
        "sampling_rule": SAMPLING_RULE,
        "feature_columns": list(FEATURE_COLUMNS),
        "status_columns": list(STATUS_COLUMNS),
    }
    return monthly


def build_monthly_feature_table(
    daily_path: Path | str = DEFAULT_DAILY_PATH,
) -> pd.DataFrame:
    """Read, hash, and sample the persisted daily feature artifact."""

    source = Path(daily_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Daily feature artifact not found: {source}")
    parent_hash = _sha256(source)
    daily = pd.read_parquet(source, engine="pyarrow")
    monthly = sample_monthly_features(daily)

    revision, dirty = _repository_state()
    provenance = {
        "parent_daily_features_sha256": parent_hash,
        "monthly_build_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "monthly_code_revision": revision,
        "monthly_code_dirty": dirty,
        "monthly_sampling_rule": SAMPLING_RULE,
    }
    for column, value in provenance.items():
        monthly[column] = value
    monthly.attrs.update(provenance)
    return monthly


def write_monthly_feature_table(
    table: pd.DataFrame, output_path: Path | str = DEFAULT_OUTPUT_PATH
) -> Path:
    """Atomically write a monthly feature table as Parquet."""

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


def build_monthly_feature_artifact(
    daily_path: Path | str = DEFAULT_DAILY_PATH,
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
) -> Path:
    """Sample and persist monthly rows from the daily feature artifact."""

    table = build_monthly_feature_table(daily_path)
    return write_monthly_feature_table(table, output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily", type=Path, default=DEFAULT_DAILY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    arguments = parser.parse_args()

    output = build_monthly_feature_artifact(arguments.daily, arguments.output)
    print(f"Wrote {output} ({_sha256(output)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
