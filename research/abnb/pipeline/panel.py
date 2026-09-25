"""Build the development-only canonical daily price panel for the ABNB study.

The raw CSVs are immutable inputs.  This module verifies their registered
hashes, reads them, and expands every security onto the same XNYS session
calendar without filling absent or unusable observations.
"""

from __future__ import annotations

import hashlib
import json
import math
from importlib.metadata import version
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pandas as pd

CALENDAR_NAME = "XNYS"
CALENDAR_LIBRARY = "exchange-calendars"
CALENDAR_VERSION = "4.13.2"
SECURITIES = ("ABNB", "BKNG", "EXPE", "SPY")
SOURCE_IDS = {
    "ABNB": "SRC-ABNB-001",
    "BKNG": "SRC-BKNG-001",
    "EXPE": "SRC-EXPE-001",
    "SPY": "SRC-SPY-001",
}

VALID = "VALID"
MISSING_SOURCE = "MISSING_SOURCE"
INVALID_PRICE = "INVALID_PRICE"
UNAVAILABLE_BY_CUTOFF = "UNAVAILABLE_BY_CUTOFF"
STATUSES = (VALID, MISSING_SOURCE, INVALID_PRICE, UNAVAILABLE_BY_CUTOFF)

EXPECTED_COLUMNS = [
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Adj Close",
    "Volume",
    "Dividends",
    "Stock Splits",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _registered_sources(raw_root: Path) -> dict[str, dict[str, Any]]:
    """Load the two manifests and resolve their registered current CSVs."""

    manifest_paths = {
        "Dataset1": raw_root / "Dataset1" / "manifest.json",
        "Dataset2": raw_root / "Dataset2" / "manifest.json",
    }
    manifests = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in manifest_paths.items()
    }
    entries = [manifests["Dataset1"], *manifests["Dataset2"]["files"]]
    sources: dict[str, dict[str, Any]] = {}
    for entry in entries:
        ticker = entry["ticker"]
        dataset_id = "Dataset1" if ticker == "ABNB" else "Dataset2"
        sources[ticker] = {
            "entry": entry,
            "dataset_id": dataset_id,
            "manifest_path": manifest_paths[dataset_id],
            "path": raw_root / dataset_id / f"{ticker}_daily.csv",
        }

    if set(sources) != set(SECURITIES):
        raise ValueError(
            f"Registered securities must be exactly {SECURITIES}; found {tuple(sorted(sources))}"
        )
    return sources


def _load_source(source: dict[str, Any], calendar: Any) -> pd.DataFrame:
    """Verify and load one registered CSV without changing its bytes."""

    entry = source["entry"]
    path = source["path"]
    actual_hash = _sha256(path)
    if actual_hash != entry["sha256"]:
        raise ValueError(
            f"Registered hash mismatch for {entry['ticker']}: expected {entry['sha256']}, "
            f"found {actual_hash}"
        )

    frame = pd.read_csv(path)
    if (
        list(frame.columns) != EXPECTED_COLUMNS
        or list(frame.columns) != entry["columns"]
    ):
        raise ValueError(
            f"Unexpected schema for {entry['ticker']}: {list(frame.columns)}"
        )
    if len(frame) != int(entry["rows"]):
        raise ValueError(
            f"Row-count mismatch for {entry['ticker']}: expected {entry['rows']}, found {len(frame)}"
        )

    session_dates = pd.to_datetime(frame["Date"], format="%Y-%m-%d", errors="coerce")
    if session_dates.isna().any():
        raise ValueError(f"Invalid session date in {entry['ticker']}")
    if session_dates.duplicated().any() or not session_dates.is_monotonic_increasing:
        raise ValueError(
            f"Session dates for {entry['ticker']} must be unique and increasing"
        )

    observed = pd.DatetimeIndex(session_dates).normalize()
    non_sessions = observed.difference(
        calendar.sessions_in_range(observed.min(), observed.max())
    )
    if len(non_sessions):
        rendered = ", ".join(date.strftime("%Y-%m-%d") for date in non_sessions)
        raise ValueError(f"Non-XNYS dates for {entry['ticker']}: {rendered}")

    adjusted_close = pd.to_numeric(frame["Adj Close"], errors="coerce")
    return pd.DataFrame(
        {"source_adjusted_close": adjusted_close.to_numpy(dtype=float)}, index=observed
    )


def _normalize_session_bound(value: Any, name: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError(f"{name} must be a valid date")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize()


def _normalize_cutoff(value: Any, calendar: Any) -> pd.Timestamp | None:
    """Return a UTC cutoff; date-only inputs mean that XNYS session's close."""

    if value is None:
        return None
    cutoff = pd.Timestamp(value)
    if pd.isna(cutoff):
        raise ValueError("information_cutoff must be a valid timestamp")

    is_date_only = isinstance(value, str) and len(value.strip()) == 10
    if is_date_only:
        session = cutoff.normalize()
        if not calendar.is_session(session):
            raise ValueError("A date-only information_cutoff must be an XNYS session")
        return calendar.session_close(session).tz_convert("UTC")
    if cutoff.tzinfo is None:
        raise ValueError("A cutoff containing a time must include a timezone")
    return cutoff.tz_convert("UTC")


def build_daily_panel(
    raw_root: Path | str | None = None,
    *,
    start: Any | None = None,
    end: Any | None = None,
    information_cutoff: Any | None = None,
) -> pd.DataFrame:
    """Return the canonical XNYS-indexed adjusted-close panel.

    The result has a ``(session_date, security)`` MultiIndex.  ``adjusted_close``
    is populated only for ``VALID`` rows; ``source_adjusted_close`` retains the
    parsed source value for invalid and cutoff-masked rows.  Missing source rows
    remain null in both columns.

    ``information_cutoff`` may be a timezone-aware timestamp or an ISO date.  A
    date means the close of that XNYS session.  Cutoff classification is a
    development-only session-close proxy, not proof of point-in-time adjusted
    price or corporate-action availability.
    """

    installed_version = version(CALENDAR_LIBRARY)
    if installed_version != CALENDAR_VERSION:
        raise RuntimeError(
            f"Canonical panel requires {CALENDAR_LIBRARY}=={CALENDAR_VERSION}; "
            f"found {installed_version}"
        )
    calendar = xcals.get_calendar(CALENDAR_NAME)
    if raw_root is None:
        raw_root = Path(__file__).resolve().parents[1] / "data" / "raw"
    raw_root = Path(raw_root).resolve()

    registered = _registered_sources(raw_root)
    loaded = {
        ticker: _load_source(registered[ticker], calendar) for ticker in SECURITIES
    }
    first_dates = {ticker: frame.index.min() for ticker, frame in loaded.items()}
    last_dates = {ticker: frame.index.max() for ticker, frame in loaded.items()}

    panel_start = (
        max(first_dates.values())
        if start is None
        else _normalize_session_bound(start, "start")
    )
    panel_end = (
        max(last_dates.values())
        if end is None
        else _normalize_session_bound(end, "end")
    )
    if panel_start > panel_end:
        raise ValueError("start must be on or before end")
    sessions = calendar.sessions_in_range(panel_start, panel_end)
    if len(sessions) == 0:
        raise ValueError("Requested range contains no XNYS sessions")

    cutoff = _normalize_cutoff(information_cutoff, calendar)
    pieces: list[pd.DataFrame] = []
    for ticker in SECURITIES:
        source_frame = loaded[ticker].reindex(sessions)
        source_price = source_frame["source_adjusted_close"]
        present = source_frame.index.isin(loaded[ticker].index)
        finite_positive = source_price.map(
            lambda value: pd.notna(value) and math.isfinite(value) and value > 0
        )

        status = pd.Series(MISSING_SOURCE, index=sessions, dtype="string")
        status.loc[present & ~finite_positive] = INVALID_PRICE
        status.loc[present & finite_positive] = VALID
        if cutoff is not None:
            closes = pd.DatetimeIndex(
                [calendar.session_close(session) for session in sessions]
            )
            status.loc[present & finite_positive & (closes > cutoff)] = (
                UNAVAILABLE_BY_CUTOFF
            )

        piece = pd.DataFrame(
            {
                "security": ticker,
                "adjusted_close": source_price.where(status.eq(VALID)).astype(
                    "Float64"
                ),
                "source_adjusted_close": source_price.astype("Float64"),
                "status": pd.Categorical(status, categories=STATUSES),
                "source_id": SOURCE_IDS[ticker],
            },
            index=sessions,
        )
        piece.index.name = "session_date"
        pieces.append(piece.reset_index().set_index(["session_date", "security"]))

    panel = pd.concat(pieces).sort_index(level=["session_date", "security"])
    sources_metadata: dict[str, dict[str, Any]] = {}
    for ticker in SECURITIES:
        source = registered[ticker]
        entry = source["entry"]
        sources_metadata[ticker] = {
            "source_id": SOURCE_IDS[ticker],
            "dataset_id": source["dataset_id"],
            "path": source["path"].as_posix(),
            "sha256": entry["sha256"],
            "manifest_path": source["manifest_path"].as_posix(),
            "manifest_sha256": _sha256(source["manifest_path"]),
            "provider": entry.get("provider"),
            "extracted_at_utc": entry.get("extracted_at_utc"),
        }
    panel.attrs = {
        "schema_version": 1,
        "research_readiness": "DEVELOPMENT_ONLY",
        "calendar": {
            "name": CALENDAR_NAME,
            "library": CALENDAR_LIBRARY,
            "library_version": installed_version,
        },
        "coverage": {
            "start": sessions[0].strftime("%Y-%m-%d"),
            "end": sessions[-1].strftime("%Y-%m-%d"),
            "session_count": len(sessions),
        },
        "information_cutoff_utc": cutoff.isoformat() if cutoff is not None else None,
        "cutoff_basis": "XNYS regular-session close; corporate-action availability remains unverified",
        "sources": sources_metadata,
        "status_definitions": {
            VALID: "Source row exists, adjusted close is finite and positive, and it is within any cutoff.",
            MISSING_SOURCE: "No registered source row exists for the XNYS session.",
            INVALID_PRICE: "Source row exists but adjusted close is missing, nonfinite, or nonpositive.",
            UNAVAILABLE_BY_CUTOFF: "Valid source row's XNYS session close is after the requested cutoff.",
        },
    }
    return panel


# Short alias for callers that already identify the object as a daily panel.
build_panel = build_daily_panel
