import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

import pandas as pd
import pytest

from research.abnb.pipeline.panel import (
    INVALID_PRICE,
    MISSING_SOURCE,
    UNAVAILABLE_BY_CUTOFF,
    VALID,
    build_daily_panel,
)

RAW_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_panel_preserves_full_calendar_and_registered_missing_rows():
    panel = build_daily_panel(RAW_ROOT)

    sessions = panel.index.get_level_values("session_date").unique()
    assert len(panel) == len(sessions) * 4
    assert tuple(panel.index.get_level_values("security").unique()) == (
        "ABNB",
        "BKNG",
        "EXPE",
        "SPY",
    )

    missing_date = pd.Timestamp("2026-09-22")
    assert panel.loc[(missing_date, "ABNB"), "status"] == MISSING_SOURCE
    assert panel.loc[(missing_date, "EXPE"), "status"] == MISSING_SOURCE
    assert pd.isna(panel.loc[(missing_date, "ABNB"), "adjusted_close"])
    assert pd.isna(panel.loc[(missing_date, "EXPE"), "source_adjusted_close"])
    assert panel.loc[(missing_date, "BKNG"), "status"] == VALID
    assert panel.loc[(missing_date, "SPY"), "status"] == VALID


def test_cutoff_masks_future_prices_without_overriding_missing_status():
    panel = build_daily_panel(
        RAW_ROOT,
        start="2026-09-21",
        end="2026-09-23",
        information_cutoff="2026-09-22",
    )

    assert (
        panel.loc[(pd.Timestamp("2026-09-23"), "SPY"), "status"]
        == UNAVAILABLE_BY_CUTOFF
    )
    assert pd.isna(panel.loc[(pd.Timestamp("2026-09-23"), "SPY"), "adjusted_close"])
    assert pd.notna(
        panel.loc[(pd.Timestamp("2026-09-23"), "SPY"), "source_adjusted_close"]
    )
    assert panel.loc[(pd.Timestamp("2026-09-22"), "ABNB"), "status"] == MISSING_SOURCE


def test_metadata_retains_source_ids_hashes_and_exact_calendar_version():
    panel = build_daily_panel(RAW_ROOT, start="2026-09-23", end="2026-09-23")

    assert panel.attrs["calendar"] == {
        "name": "XNYS",
        "library": "exchange-calendars",
        "library_version": "4.13.2",
    }
    for ticker, metadata in panel.attrs["sources"].items():
        assert metadata["source_id"] == f"SRC-{ticker}-001"
        assert len(metadata["sha256"]) == 64
        assert len(metadata["manifest_sha256"]) == 64


@pytest.mark.parametrize("invalid_price", [0.0, -1.0, float("inf"), float("nan")])
def test_nonfinite_or_nonpositive_adjusted_close_is_invalid(tmp_path, invalid_price):
    copied_raw = tmp_path / "raw"
    shutil.copytree(RAW_ROOT, copied_raw)
    csv_path = copied_raw / "Dataset1" / "ABNB_daily.csv"
    manifest_path = copied_raw / "Dataset1" / "manifest.json"
    os.chmod(csv_path, os.stat(csv_path).st_mode | stat.S_IWRITE)
    os.chmod(manifest_path, os.stat(manifest_path).st_mode | stat.S_IWRITE)

    source = pd.read_csv(csv_path)
    source.loc[0, "Adj Close"] = invalid_price
    source.to_csv(csv_path, index=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = _sha256(csv_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    panel = build_daily_panel(copied_raw, start="2020-12-10", end="2020-12-10")
    row = panel.loc[(pd.Timestamp("2020-12-10"), "ABNB")]
    assert row["status"] == INVALID_PRICE
    assert pd.isna(row["adjusted_close"])
