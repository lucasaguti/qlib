"""Build the development-only daily feature artifact for the ABNB study."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from research.abnb.pipeline.features import (
    FEATURE_STATUSES,
    FeatureResult,
    abnb_ema_gap_20,
    abnb_macd_hist_norm,
    abnb_mom_12_2,
    abnb_ret_21d,
    abnb_rsi_14,
    peer_ret_5d,
    spy_ret_5d,
    spy_rvol_20d,
)
from research.abnb.pipeline.panel import SECURITIES, build_daily_panel

FEATURE_COLUMNS = (
    "ABNB_MOM_12_2",
    "ABNB_RET_21D",
    "ABNB_RSI_14",
    "ABNB_EMA_GAP_20",
    "ABNB_MACD_HIST_NORM",
    "SPY_RET_5D",
    "PEER_RET_5D",
    "SPY_RVOL_20D",
)
STATUS_COLUMNS = tuple(f"{name}_STATUS" for name in FEATURE_COLUMNS)
DEFAULT_OUTPUT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "interim" / "daily_features.parquet"
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_state() -> tuple[str, bool]:
    repository_root = Path(__file__).resolve().parents[3]
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        porcelain = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Unable to determine the Git code revision") from exc
    if len(revision) != 40:
        raise RuntimeError(f"Unexpected Git revision: {revision!r}")
    return revision, bool(porcelain.strip())


def _validate_panel(panel: pd.DataFrame) -> None:
    if not isinstance(panel.index, pd.MultiIndex) or panel.index.names != [
        "session_date",
        "security",
    ]:
        raise ValueError(
            "panel must use a (session_date, security) MultiIndex"
        )
    required_columns = {"adjusted_close", "status"}
    if not required_columns.issubset(panel.columns):
        raise ValueError(f"panel must contain {sorted(required_columns)}")

    sessions = panel.index.get_level_values("session_date").unique()
    expected_index = pd.MultiIndex.from_product(
        [sessions, SECURITIES], names=["session_date", "security"]
    )
    if not panel.index.equals(expected_index):
        raise ValueError(
            "panel must contain exactly one ordered row per session and security"
        )

    metadata = panel.attrs
    if not {"calendar", "sources"}.issubset(metadata):
        raise ValueError("panel is missing calendar or source lineage metadata")
    if set(metadata["sources"]) != set(SECURITIES):
        raise ValueError("panel source lineage must cover all required securities")


def _history(panel: pd.DataFrame, security: str) -> pd.DataFrame:
    return panel.xs(security, level="security")[["adjusted_close", "status"]]


def _evaluate_features(panel: pd.DataFrame) -> dict[str, list[FeatureResult]]:
    histories = {security: _history(panel, security) for security in SECURITIES}
    sessions = histories["ABNB"].index
    results = {name: [] for name in FEATURE_COLUMNS}

    single_security: tuple[
        tuple[str, str, Callable[..., FeatureResult]], ...
    ] = (
        ("ABNB_MOM_12_2", "ABNB", abnb_mom_12_2),
        ("ABNB_RET_21D", "ABNB", abnb_ret_21d),
        ("ABNB_RSI_14", "ABNB", abnb_rsi_14),
        ("ABNB_EMA_GAP_20", "ABNB", abnb_ema_gap_20),
        ("ABNB_MACD_HIST_NORM", "ABNB", abnb_macd_hist_norm),
    )
    for position, session in enumerate(sessions):
        stop = position + 1
        for feature_name, security, function in single_security:
            history = histories[security].iloc[:stop]
            results[feature_name].append(
                function(history["adjusted_close"], history["status"])
            )

        spy = histories["SPY"].iloc[:stop]
        results["SPY_RET_5D"].append(
            spy_ret_5d(
                spy["adjusted_close"], spy["status"], anchor_date=session
            )
        )
        expe = histories["EXPE"].iloc[:stop]
        bkng = histories["BKNG"].iloc[:stop]
        results["PEER_RET_5D"].append(
            peer_ret_5d(
                expe["adjusted_close"],
                bkng["adjusted_close"],
                expe["status"],
                bkng["status"],
                anchor_date=session,
            )
        )
        results["SPY_RVOL_20D"].append(
            spy_rvol_20d(
                spy["adjusted_close"], spy["status"], anchor_date=session
            )
        )
    return results


def build_daily_feature_table(
    raw_root: Path | str | None = None,
    *,
    start: Any | None = None,
    end: Any | None = None,
    information_cutoff: Any | None = None,
    panel: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return one status-bearing feature row for every canonical XNYS session.

    Supplying ``panel`` is intended for deterministic tests and composed pipeline
    calls. Otherwise the registered raw inputs are verified and loaded directly.
    """

    if panel is not None and any(
        value is not None for value in (raw_root, start, end, information_cutoff)
    ):
        raise ValueError("panel cannot be combined with raw-input build arguments")
    if panel is None:
        panel = build_daily_panel(
            raw_root,
            start=start,
            end=end,
            information_cutoff=information_cutoff,
        )
    _validate_panel(panel)

    results = _evaluate_features(panel)
    sessions = panel.index.get_level_values("session_date").unique()
    table = pd.DataFrame({"session_date": sessions})
    for feature_name in FEATURE_COLUMNS:
        table[feature_name] = pd.array(
            [result.value for result in results[feature_name]], dtype="Float64"
        )
        table[f"{feature_name}_STATUS"] = pd.Categorical(
            [result.status for result in results[feature_name]],
            categories=FEATURE_STATUSES,
        )

    calendar = panel.attrs["calendar"]
    sources = panel.attrs["sources"]
    source_versions = {
        ticker: {
            "source_id": source["source_id"],
            "dataset_id": source["dataset_id"],
            "extracted_at_utc": source.get("extracted_at_utc"),
        }
        for ticker, source in sources.items()
    }
    parent_dataset_hashes = {
        source["source_id"]: source["sha256"] for source in sources.values()
    }
    parent_manifest_hashes = {
        source["dataset_id"]: source["manifest_sha256"]
        for source in sources.values()
    }
    revision, dirty = _repository_state()
    build_timestamp = datetime.now(timezone.utc).isoformat()
    provenance = {
        "research_readiness": panel.attrs.get(
            "research_readiness", "DEVELOPMENT_ONLY"
        ),
        "calendar_name": calendar["name"],
        "calendar_library": calendar["library"],
        "calendar_version": calendar["library_version"],
        "source_versions": _canonical_json(source_versions),
        "parent_dataset_hashes": _canonical_json(parent_dataset_hashes),
        "parent_manifest_hashes": _canonical_json(parent_manifest_hashes),
        "build_timestamp_utc": build_timestamp,
        "code_revision": revision,
        "code_dirty": dirty,
    }
    for column, value in provenance.items():
        table[column] = value

    table.attrs = {
        "schema_version": 1,
        "artifact_role": "development-only interim daily feature table",
        "feature_columns": list(FEATURE_COLUMNS),
        "status_columns": list(STATUS_COLUMNS),
        **provenance,
    }
    return table


def write_daily_feature_table(
    table: pd.DataFrame, output_path: Path | str = DEFAULT_OUTPUT_PATH
) -> Path:
    """Atomically write a daily feature table as Parquet."""

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


def build_daily_feature_artifact(
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
    raw_root: Path | str | None = None,
    *,
    start: Any | None = None,
    end: Any | None = None,
    information_cutoff: Any | None = None,
) -> Path:
    """Build and persist the development-only daily feature artifact."""

    table = build_daily_feature_table(
        raw_root,
        start=start,
        end=end,
        information_cutoff=information_cutoff,
    )
    return write_daily_feature_table(table, output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--information-cutoff")
    arguments = parser.parse_args()

    output = build_daily_feature_artifact(
        arguments.output,
        arguments.raw_root,
        start=arguments.start,
        end=arguments.end,
        information_cutoff=arguments.information_cutoff,
    )
    print(f"Wrote {output} ({_sha256(output)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
