import json
from pathlib import Path

import pandas as pd
import pytest

from research.abnb.pipeline.daily_features import FEATURE_COLUMNS
from research.abnb.pipeline.final_evaluation import (
    AUTHORIZATION_PHRASE,
    _classify_primary_finding,
    _source_inventory,
    load_final_evaluation_inputs,
    run_final_evaluation,
)
from research.abnb.pipeline.targets import TARGET_COLUMN, TARGET_STATUS_COLUMN


def _fixture_files(tmp_path: Path):
    sessions = pd.date_range("2024-01-31", periods=6, freq="ME")
    issued = pd.to_datetime(sessions + pd.Timedelta(days=1), utc=True)
    features = pd.DataFrame({"reference_session": sessions, "issued_at_utc": issued})
    for number, feature in enumerate(FEATURE_COLUMNS, 1):
        features[feature] = number / 10
        features[f"{feature}_STATUS"] = "VALID"
    targets = pd.DataFrame(
        {
            "reference_session": sessions,
            "issued_at_utc": issued,
            "label_available_at": pd.to_datetime(
                sessions + pd.offsets.MonthEnd(3), utc=True
            ),
            TARGET_COLUMN: 0.01,
            TARGET_STATUS_COLUMN: "VALID",
            "evaluation_partition": [
                "DEVELOPMENT",
                "DEVELOPMENT",
                "DEVELOPMENT",
                "DEVELOPMENT",
                "FINAL_TEST",
                "FINAL_TEST",
            ],
        }
    )
    feature_path = tmp_path / "features.parquet"
    target_path = tmp_path / "targets.parquet"
    protocol_path = tmp_path / "protocol.json"
    features.to_parquet(feature_path, index=False)
    targets.to_parquet(target_path, index=False)
    protocol = {
        "periods": {
            "final_test_origin_end": str(sessions[-1].date()),
            "final_test_origin_count": 2,
            "final_test_reference_sessions": [
                str(sessions[-2].date()),
                str(sessions[-1].date()),
            ],
        },
        "eligibility": {"required_feature_names": list(FEATURE_COLUMNS)},
    }
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    return feature_path, target_path, protocol_path


def test_final_loader_admits_exact_frozen_block_and_excludes_later_rows(tmp_path):
    feature_path, target_path, protocol_path = _fixture_files(tmp_path)

    loaded, protocol = load_final_evaluation_inputs(
        feature_path=feature_path,
        target_path=target_path,
        protocol_path=protocol_path,
    )

    assert len(loaded) == 6
    assert loaded["reference_session"].max() == pd.Timestamp(
        protocol["periods"]["final_test_origin_end"]
    )
    assert loaded["evaluation_partition"].value_counts().to_dict() == {
        "DEVELOPMENT": 4,
        "FINAL_TEST": 2,
    }


def test_final_runner_requires_exact_authorization_before_any_output(tmp_path):
    output_dir = tmp_path / "final"

    with pytest.raises(PermissionError, match="authorization phrase"):
        run_final_evaluation(authorization="yes", output_dir=output_dir)

    assert not output_dir.exists()
    assert AUTHORIZATION_PHRASE == "I AUTHORIZE THE FROZEN FINAL TEST"


@pytest.mark.parametrize(
    ("interval", "p_value", "expected"),
    [
        ((-0.3, -0.1), 0.01, "POSITIVE"),
        ((0.1, 0.3), 0.01, "NEGATIVE"),
        ((-0.1, 0.2), 0.8, "INCONCLUSIVE"),
    ],
)
def test_primary_finding_rule_is_fixed_before_access(interval, p_value, expected):
    results = {
        "paired_comparisons": {
            "ridge_minus_expanding_average_squared_error": {
                "primary_block_bootstrap_95_interval": interval,
                "p_value": p_value,
            }
        }
    }

    assert _classify_primary_finding(results)["label"] == expected


def test_source_inventory_records_every_source_and_manifest_hash(tmp_path):
    files = {
        "Dataset1/ABNB_daily.csv": b"abnb",
        "Dataset1/manifest.json": b"manifest1",
        "Dataset2/BKNG_daily.csv": b"bkng",
        "Dataset2/EXPE_daily.csv": b"expe",
        "Dataset2/SPY_daily.csv": b"spy",
        "Dataset2/manifest.json": b"manifest2",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    inventory = _source_inventory(tmp_path)

    assert set(inventory) == {
        "SRC-ABNB-001",
        "SRC-BKNG-001",
        "SRC-EXPE-001",
        "SRC-SPY-001",
        "Dataset1 manifest",
        "Dataset2 manifest",
    }
    assert all(len(item["sha256"]) == 64 for item in inventory.values())
