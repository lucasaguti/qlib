"""Validate the registered ABNB research inputs without modifying source files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

import exchange_calendars as xcals
import pandas as pd


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
PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Adj Close"]
NUMERIC_COLUMNS = PRICE_COLUMNS + ["Volume", "Dividends", "Stock Splits"]
PIT_REQUIRED_EVIDENCE = [
    "provider_version",
    "timezone",
    "calendar_identity_and_version",
    "price_availability_timestamp_or_rule",
    "adjustment_state_availability_timestamp_or_rule",
    "corporate_action_version",
    "availability_evidence",
    "usage_and_retention_rights",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def session_dates(calendar: Any, start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    sessions = calendar.sessions_in_range(start, end)
    if sessions.tz is not None:
        sessions = sessions.tz_localize(None)
    return sessions.normalize()


def validate_csv(path: Path, entry: dict[str, Any], calendar: Any, repository_root: Path) -> dict[str, Any]:
    frame = pd.read_csv(path)
    result: dict[str, Any] = {
        "path": path.relative_to(repository_root).as_posix(),
        "sha256": sha256(path),
        "manifest_sha256": entry["sha256"],
        "hash_matches_manifest": False,
        "columns": list(frame.columns),
        "columns_match_manifest": list(frame.columns) == entry["columns"],
        "columns_match_contract": list(frame.columns) == EXPECTED_COLUMNS,
        "rows": int(len(frame)),
        "row_count_matches_manifest": int(len(frame)) == int(entry["rows"]),
    }
    result["hash_matches_manifest"] = result["sha256"] == result["manifest_sha256"]

    parsed_dates = pd.to_datetime(frame["Date"], format="%Y-%m-%d", errors="coerce")
    invalid_date_count = int(parsed_dates.isna().sum())
    result["invalid_date_count"] = invalid_date_count
    result["duplicate_date_count"] = int(parsed_dates.duplicated().sum())
    result["dates_strictly_increasing"] = bool(
        parsed_dates.is_monotonic_increasing and not parsed_dates.duplicated().any()
    )
    result["weekend_date_count"] = int((parsed_dates.dt.dayofweek >= 5).sum())
    result["first_observation"] = parsed_dates.min().strftime("%Y-%m-%d") if invalid_date_count < len(frame) else None
    result["last_observation"] = parsed_dates.max().strftime("%Y-%m-%d") if invalid_date_count < len(frame) else None
    result["coverage_matches_manifest"] = (
        result["first_observation"] == entry["first_observation"]
        and result["last_observation"] == entry["last_observation"]
    )

    numeric = frame[NUMERIC_COLUMNS].apply(pd.to_numeric, errors="coerce")
    result["non_numeric_or_missing_counts"] = {column: int(numeric[column].isna().sum()) for column in NUMERIC_COLUMNS}
    result["nonfinite_counts"] = {
        column: int((~numeric[column].map(math.isfinite)).sum()) for column in NUMERIC_COLUMNS
    }
    result["nonpositive_price_counts"] = {column: int((numeric[column] <= 0).sum()) for column in PRICE_COLUMNS}
    result["negative_volume_count"] = int((numeric["Volume"] < 0).sum())
    result["noninteger_volume_count"] = int(((numeric["Volume"] % 1) != 0).sum())
    result["negative_dividend_count"] = int((numeric["Dividends"] < 0).sum())
    result["negative_split_count"] = int((numeric["Stock Splits"] < 0).sum())

    tolerance = 1e-7
    result["high_below_ohlc_count"] = int(
        (numeric["High"] + tolerance < numeric[["Open", "Low", "Close"]].max(axis=1)).sum()
    )
    result["low_above_ohlc_count"] = int(
        (numeric["Low"] - tolerance > numeric[["Open", "High", "Close"]].min(axis=1)).sum()
    )

    actions = frame.loc[(numeric["Dividends"] != 0) | (numeric["Stock Splits"] != 0), EXPECTED_COLUMNS]
    result["action_rows"] = [
        {
            "date": str(row["Date"]),
            "dividend": float(row["Dividends"]),
            "stock_split": float(row["Stock Splits"]),
        }
        for _, row in actions.iterrows()
    ]
    result["dividend_event_count"] = int((numeric["Dividends"] != 0).sum())
    result["split_event_count"] = int((numeric["Stock Splits"] != 0).sum())

    if invalid_date_count == 0 and len(frame):
        expected = session_dates(calendar, parsed_dates.min(), parsed_dates.max())
        observed = pd.DatetimeIndex(parsed_dates).normalize()
        missing = expected.difference(observed)
        extras = observed.difference(expected)
        result["expected_xnys_sessions"] = int(len(expected))
        result["missing_xnys_sessions"] = [date.strftime("%Y-%m-%d") for date in missing]
        result["non_xnys_dates"] = [date.strftime("%Y-%m-%d") for date in extras]
    else:
        result["expected_xnys_sessions"] = None
        result["missing_xnys_sessions"] = []
        result["non_xnys_dates"] = []

    result["structural_checks_pass"] = all(
        [
            result["hash_matches_manifest"],
            result["columns_match_manifest"],
            result["columns_match_contract"],
            result["row_count_matches_manifest"],
            result["invalid_date_count"] == 0,
            result["duplicate_date_count"] == 0,
            result["dates_strictly_increasing"],
            result["weekend_date_count"] == 0,
            result["coverage_matches_manifest"],
            all(count == 0 for count in result["non_numeric_or_missing_counts"].values()),
            all(count == 0 for count in result["nonfinite_counts"].values()),
            all(count == 0 for count in result["nonpositive_price_counts"].values()),
            result["negative_volume_count"] == 0,
            result["noninteger_volume_count"] == 0,
            result["negative_dividend_count"] == 0,
            result["negative_split_count"] == 0,
            result["high_below_ohlc_count"] == 0,
            result["low_above_ohlc_count"] == 0,
            len(result["non_xnys_dates"]) == 0,
        ]
    )
    return result


def load_entries(raw_root: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    manifest_paths = {
        "Dataset1": raw_root / "Dataset1" / "manifest.json",
        "Dataset2": raw_root / "Dataset2" / "manifest.json",
    }
    manifests = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in manifest_paths.items()}
    first = manifests["Dataset1"]
    entries = [
        {
            **first,
            "dataset_id": "Dataset1",
            "local_current": raw_root / "Dataset1" / "ABNB_daily.csv",
            "local_archive": raw_root / "Dataset1" / "versions" / Path(first["archived_file"]).name,
        }
    ]
    for item in manifests["Dataset2"]["files"]:
        entries.append(
            {
                **item,
                "dataset_id": "Dataset2",
                "local_current": raw_root / "Dataset2" / f"{item['ticker']}_daily.csv",
                "local_archive": raw_root / "Dataset2" / "versions" / Path(item["archived_file"]).name,
            }
        )
    return entries, {name: sha256(path) for name, path in manifest_paths.items()}


def run(raw_root: Path) -> dict[str, Any]:
    calendar = xcals.get_calendar("XNYS")
    repository_root = raw_root.parents[3]
    entries, manifest_hashes = load_entries(raw_root)
    securities: dict[str, Any] = {}
    date_sets: dict[str, set[str]] = {}
    structural_errors: list[str] = []
    session_warnings: list[str] = []

    for entry in entries:
        ticker = entry["ticker"]
        current_path = Path(entry["local_current"])
        archive_path = Path(entry["local_archive"])
        current = validate_csv(current_path, entry, calendar, repository_root)
        archive_hash = sha256(archive_path)
        current["archive_path"] = archive_path.relative_to(repository_root).as_posix()
        current["archive_sha256"] = archive_hash
        current["archive_matches_current"] = archive_hash == current["sha256"]
        current["manifest_point_in_time_vintage_verified"] = bool(entry.get("point_in_time_vintage_verified"))
        current["point_in_time_evidence_status"] = "UNCONFIRMED"
        current["missing_point_in_time_evidence"] = PIT_REQUIRED_EVIDENCE
        securities[ticker] = current
        date_sets[ticker] = set(pd.read_csv(current_path, usecols=["Date"])["Date"])

        if not current["structural_checks_pass"] or not current["archive_matches_current"]:
            structural_errors.append(f"{ticker}: one or more structural, hash, value, or archive checks failed")
        if current["missing_xnys_sessions"]:
            session_warnings.append(f"{ticker}: missing XNYS sessions {current['missing_xnys_sessions']}")

    study_start = min(date_sets["ABNB"])
    study_date_sets = {ticker: {date for date in dates if date >= study_start} for ticker, dates in date_sets.items()}
    union_dates = set.union(*study_date_sets.values())
    cross_security = {
        ticker: {
            "dates_absent_relative_to_union": sorted(union_dates - dates),
            "study_period_date_count": len(dates),
        }
        for ticker, dates in study_date_sets.items()
    }
    common_dates = set.intersection(*study_date_sets.values())

    pdf_path = raw_root / "specifications" / "ABNB_predictive_indicators1.pdf"
    report = {
        "report_version": 1,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_root": raw_root.relative_to(repository_root).as_posix(),
        "calendar": {
            "name": "XNYS",
            "library": "exchange-calendars",
            "library_version": version("exchange-calendars"),
        },
        "manifest_sha256": manifest_hashes,
        "indicator_specification": {
            "path": pdf_path.relative_to(repository_root).as_posix(),
            "sha256": sha256(pdf_path),
        },
        "securities": securities,
        "cross_security_alignment": {
            "study_start": study_start,
            "union_date_count": len(union_dates),
            "common_date_count": len(common_dates),
            "by_security": cross_security,
        },
        "issues": {
            "structural_errors": structural_errors,
            "session_warnings": session_warnings,
            "provenance_blockers": [
                "The manifests assert point_in_time_vintage_verified=true but do not include the required "
                "price-version and adjustment-state availability evidence.",
                "Provider/package version, source timezone, and calendar identity/version are absent from "
                "the source manifests.",
                "Usage, retention, machine-learning, backup, and processing rights are not documented.",
            ],
        },
        "status": {
            "byte_integrity": "PASS" if not structural_errors else "FAIL",
            "xnys_session_coverage": "WARNING" if session_warnings else "PASS",
            "point_in_time_provenance": "BLOCKED",
            "usage_rights": "UNKNOWN",
            "research_readiness": "DEVELOPMENT_ONLY",
        },
    }
    return report


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=project_root / "data" / "raw")
    parser.add_argument("--output", type=Path, default=project_root / "validation" / "data_validation.json")
    args = parser.parse_args()
    report = run(args.raw_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["status"], indent=2))
    for category, issues in report["issues"].items():
        for issue in issues:
            print(f"{category}: {issue}")
    return 1 if report["status"]["byte_integrity"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
