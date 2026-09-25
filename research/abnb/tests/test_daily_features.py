import json
from pathlib import Path

import pandas as pd
import pytest

from research.abnb.pipeline.daily_features import (
    FEATURE_COLUMNS,
    STATUS_COLUMNS,
    build_daily_feature_table,
    write_daily_feature_table,
)
from research.abnb.pipeline.features import INSUFFICIENT_HISTORY
from research.abnb.pipeline.panel import MISSING_SOURCE, VALID

RAW_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.fixture(scope="module")
def daily_features():
    return build_daily_feature_table(RAW_ROOT)


def test_table_has_one_row_per_session_and_all_status_bearing_features(
    daily_features,
):
    assert len(daily_features) == 1452
    assert daily_features["session_date"].is_unique
    assert daily_features["session_date"].is_monotonic_increasing
    assert set(FEATURE_COLUMNS).issubset(daily_features.columns)
    assert set(STATUS_COLUMNS).issubset(daily_features.columns)

    for feature_name in FEATURE_COLUMNS:
        valid = daily_features[f"{feature_name}_STATUS"].eq(VALID)
        assert daily_features.loc[valid, feature_name].notna().all()
        assert daily_features.loc[~valid, feature_name].isna().all()


def test_warmup_and_real_source_gap_statuses_are_preserved(daily_features):
    first = daily_features.iloc[0]
    for status_column in STATUS_COLUMNS:
        assert first[status_column] == INSUFFICIENT_HISTORY

    missing = daily_features.set_index("session_date").loc[pd.Timestamp("2026-09-22")]
    assert missing["ABNB_RET_21D_STATUS"] == MISSING_SOURCE
    assert missing["ABNB_RSI_14_STATUS"] == MISSING_SOURCE
    assert missing["PEER_RET_5D_STATUS"] == MISSING_SOURCE
    assert missing["SPY_RET_5D_STATUS"] == VALID
    assert missing["SPY_RVOL_20D_STATUS"] == VALID


def test_table_contains_complete_version_and_parent_hash_lineage(daily_features):
    assert daily_features["research_readiness"].unique().tolist() == [
        "DEVELOPMENT_ONLY"
    ]
    assert daily_features["calendar_name"].unique().tolist() == ["XNYS"]
    assert daily_features["calendar_library"].unique().tolist() == [
        "exchange-calendars"
    ]
    assert daily_features["calendar_version"].unique().tolist() == ["4.13.2"]
    assert daily_features["code_revision"].str.fullmatch(r"[0-9a-f]{40}").all()
    assert daily_features["build_timestamp_utc"].str.endswith("+00:00").all()

    source_versions = json.loads(daily_features["source_versions"].iloc[0])
    dataset_hashes = json.loads(daily_features["parent_dataset_hashes"].iloc[0])
    manifest_hashes = json.loads(daily_features["parent_manifest_hashes"].iloc[0])
    assert set(source_versions) == {"ABNB", "BKNG", "EXPE", "SPY"}
    assert set(dataset_hashes) == {
        "SRC-ABNB-001",
        "SRC-BKNG-001",
        "SRC-EXPE-001",
        "SRC-SPY-001",
    }
    assert all(len(value) == 64 for value in dataset_hashes.values())
    assert set(manifest_hashes) == {"Dataset1", "Dataset2"}
    assert all(len(value) == 64 for value in manifest_hashes.values())


def test_parquet_round_trip_retains_values_statuses_and_provenance(
    daily_features, tmp_path
):
    output = write_daily_feature_table(
        daily_features, tmp_path / "interim" / "daily_features.parquet"
    )
    restored = pd.read_parquet(output, engine="pyarrow")

    pd.testing.assert_frame_equal(restored, daily_features)
    assert restored.attrs["schema_version"] == 1
    assert restored.attrs["feature_columns"] == list(FEATURE_COLUMNS)
    assert restored.attrs["status_columns"] == list(STATUS_COLUMNS)


def test_rejects_panel_with_missing_security_row():
    from research.abnb.pipeline.panel import build_daily_panel

    panel = build_daily_panel(
        RAW_ROOT, start="2026-09-21", end="2026-09-23"
    ).drop(index=(pd.Timestamp("2026-09-23"), "SPY"))

    with pytest.raises(ValueError, match="exactly one ordered row"):
        build_daily_feature_table(panel=panel)
