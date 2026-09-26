from pathlib import Path

import pandas as pd
import pytest

from research.abnb.pipeline.panel import INVALID_PRICE, MISSING_SOURCE, VALID
from research.abnb.pipeline.targets import (
    IMMATURE,
    MATURITY_PRICE_COLUMN,
    MATURITY_MISSING_SOURCE,
    REFERENCE_PRICE_COLUMN,
    TARGET_COLUMN,
    TARGET_STATUS_COLUMN,
    TARGET_VALID,
    WITHHELD_BY_PROTOCOL,
    build_monthly_target_table,
    construct_three_month_targets,
    select_matured_training_targets,
    write_monthly_target_table,
)


def _origins(rows):
    return pd.DataFrame(rows)


def _origin(reference, issuance, maturity, available):
    return {
        "reference_session": pd.Timestamp(reference),
        "issued_at_utc": pd.Timestamp(issuance),
        "maturity_session": pd.Timestamp(maturity),
        "label_available_at": pd.Timestamp(available),
    }


def _prices(rows):
    return pd.DataFrame(
        {
            "adjusted_close": pd.array([row[1] for row in rows], dtype="Float64"),
            "status": [row[2] for row in rows],
        },
        index=pd.DatetimeIndex([row[0] for row in rows], name="session_date"),
    )


def test_uses_exact_reference_and_final_maturity_session_prices():
    origins = _origins(
        [
            _origin(
                "2024-11-29",
                "2024-12-02 14:30:00+00:00",
                "2025-02-28",
                "2025-02-28 21:00:00+00:00",
            )
        ]
    )
    prices = _prices(
        [
            ("2024-11-29", 100.0, VALID),
            ("2025-02-27", 500.0, VALID),
            ("2025-02-28", 125.0, VALID),
            ("2025-03-03", 700.0, VALID),
        ]
    )

    result = construct_three_month_targets(
        origins, prices, observed_as_of_utc="2025-03-01 00:00:00+00:00"
    ).iloc[0]

    assert result[REFERENCE_PRICE_COLUMN] == 100.0
    assert result[MATURITY_PRICE_COLUMN] == 125.0
    assert result[TARGET_COLUMN] == pytest.approx(0.25)
    assert result[TARGET_STATUS_COLUMN] == TARGET_VALID


@pytest.mark.parametrize(
    ("reference", "maturity"),
    [
        ("2021-05-28", "2021-08-31"),
        ("2021-11-30", "2022-02-28"),
        ("2024-11-29", "2025-02-28"),
    ],
)
def test_handles_month_length_weekend_holiday_and_year_boundaries(
    reference, maturity
):
    origins = _origins(
        [
            _origin(
                reference,
                (
                    f"{pd.Timestamp(reference) + pd.Timedelta(days=4):%Y-%m-%d} "
                    "14:30:00+00:00"
                ),
                maturity,
                f"{maturity} 21:00:00+00:00",
            )
        ]
    )
    prices = _prices([(reference, 80.0, VALID), (maturity, 100.0, VALID)])

    result = construct_three_month_targets(
        origins, prices, observed_as_of_utc="2025-12-31 23:00:00+00:00"
    ).iloc[0]

    assert result[MATURITY_PRICE_COLUMN] == 100.0
    assert result[TARGET_COLUMN] == pytest.approx(0.25)


def test_adjusted_prices_produce_total_return_across_split_and_dividend():
    origins = _origins(
        [
            _origin(
                "2024-01-31",
                "2024-02-01 14:30:00+00:00",
                "2024-04-30",
                "2024-04-30 20:00:00+00:00",
            )
        ]
    )
    # Raw prices could fall from 200 to 110 after a 2:1 split and dividend.
    # The target contract consumes the adjusted series, where 100 -> 110 is +10%.
    adjusted = _prices(
        [("2024-01-31", 100.0, VALID), ("2024-04-30", 110.0, VALID)]
    )
    adjusted["raw_close"] = [200.0, 110.0]

    result = construct_three_month_targets(
        origins, adjusted, observed_as_of_utc="2024-05-01 00:00:00+00:00"
    ).iloc[0]

    assert result[TARGET_COLUMN] == pytest.approx(0.10)
    assert "raw_close" not in result.index


def test_immature_origin_is_retained_with_unavailable_label():
    origins = _origins(
        [
            _origin(
                "2026-06-30",
                "2026-07-01 13:30:00+00:00",
                "2026-09-30",
                "2026-09-30 20:00:00+00:00",
            )
        ]
    )
    prices = _prices([("2026-06-30", 140.0, VALID)])

    result = construct_three_month_targets(
        origins, prices, observed_as_of_utc="2026-09-23 20:00:00+00:00"
    )

    assert len(result) == 1
    assert result.iloc[0][TARGET_STATUS_COLUMN] == IMMATURE
    assert pd.isna(result.iloc[0][TARGET_COLUMN])
    assert pd.isna(result.iloc[0][MATURITY_PRICE_COLUMN])


def test_missing_or_invalid_exact_prices_fail_closed():
    origins = _origins(
        [
            _origin(
                "2024-01-31",
                "2024-02-01 14:30:00+00:00",
                "2024-04-30",
                "2024-04-30 20:00:00+00:00",
            )
        ]
    )
    missing_maturity = _prices([("2024-01-31", 100.0, VALID)])
    result = construct_three_month_targets(
        origins,
        missing_maturity,
        observed_as_of_utc="2024-05-01 00:00:00+00:00",
    ).iloc[0]
    assert result[TARGET_STATUS_COLUMN] == MATURITY_MISSING_SOURCE
    assert pd.isna(result[TARGET_COLUMN])

    invalid_reference = _prices(
        [("2024-01-31", 100.0, INVALID_PRICE), ("2024-04-30", 120.0, VALID)]
    )
    result = construct_three_month_targets(
        origins,
        invalid_reference,
        observed_as_of_utc="2024-05-01 00:00:00+00:00",
    ).iloc[0]
    assert result[TARGET_STATUS_COLUMN] == "REFERENCE_INVALID_PRICE"


def test_walk_forward_training_excludes_labels_not_matured_by_issuance():
    targets = pd.DataFrame(
        {
            "reference_session": pd.to_datetime(
                ["2024-01-31", "2024-02-29", "2024-03-28"]
            ),
            "label_available_at": pd.to_datetime(
                [
                    "2024-04-30 20:00:00+00:00",
                    "2024-05-31 20:00:00+00:00",
                    "2024-06-28 20:00:00+00:00",
                ],
                utc=True,
            ),
            TARGET_COLUMN: pd.array([0.1, 0.2, 0.3], dtype="Float64"),
            TARGET_STATUS_COLUMN: [TARGET_VALID, TARGET_VALID, TARGET_VALID],
            "sentinel_feature": [10.0, 20.0, 30.0],
        }
    )

    selected = select_matured_training_targets(
        targets, issued_at_utc="2024-05-31 20:00:00+00:00"
    )

    assert selected["reference_session"].tolist() == [
        pd.Timestamp("2024-01-31"),
        pd.Timestamp("2024-02-29"),
    ]
    assert selected["sentinel_feature"].tolist() == [10.0, 20.0]


def test_future_prices_and_unrelated_columns_cannot_change_an_earlier_target():
    origins = _origins(
        [
            _origin(
                "2024-01-31",
                "2024-02-01 14:30:00+00:00",
                "2024-04-30",
                "2024-04-30 20:00:00+00:00",
            )
        ]
    )
    prices = _prices(
        [
            ("2024-01-31", 100.0, VALID),
            ("2024-04-30", 120.0, VALID),
            ("2024-05-31", 130.0, VALID),
        ]
    )
    prices["future_fitted_scaler_mean"] = [999.0, 999.0, 999.0]
    first = construct_three_month_targets(
        origins, prices, observed_as_of_utc="2024-05-01 00:00:00+00:00"
    )
    mutated = prices.copy()
    mutated.loc[pd.Timestamp("2024-05-31"), "adjusted_close"] = 1_000_000.0
    mutated["future_fitted_scaler_mean"] = -1_000_000.0
    second = construct_three_month_targets(
        origins, mutated, observed_as_of_utc="2024-05-01 00:00:00+00:00"
    )

    assert first.iloc[0][TARGET_COLUMN] == second.iloc[0][TARGET_COLUMN]
    assert "future_fitted_scaler_mean" not in first.columns


def test_withheld_origin_does_not_require_or_expose_prices():
    origin = _origin(
        "2025-06-30",
        "2025-07-01 13:30:00+00:00",
        "2025-09-30",
        "2025-09-30 20:00:00+00:00",
    )
    result = construct_three_month_targets(
        _origins([origin]),
        _prices([("2024-01-02", 1.0, MISSING_SOURCE)]),
        observed_as_of_utc="2026-09-23 20:00:00+00:00",
        withheld_reference_sessions=["2025-06-30"],
    ).iloc[0]

    assert result[TARGET_STATUS_COLUMN] == WITHHELD_BY_PROTOCOL
    assert pd.isna(result[REFERENCE_PRICE_COLUMN])
    assert pd.isna(result[MATURITY_PRICE_COLUMN])
    assert pd.isna(result[TARGET_COLUMN])


def test_registered_build_withholds_final_test_and_retains_immature_origins(tmp_path):
    table = build_monthly_target_table()
    final_test = table.loc[table["evaluation_partition"].eq("FINAL_TEST")]
    post_test = table.loc[
        table["evaluation_partition"].eq("POST_TEST_QUARANTINE")
    ]

    assert len(final_test) == 12
    assert set(final_test[TARGET_STATUS_COLUMN].astype("string")) == {
        WITHHELD_BY_PROTOCOL
    }
    assert final_test[TARGET_COLUMN].isna().all()
    assert post_test["reference_session"].tolist() == list(
        pd.to_datetime(["2026-06-30", "2026-07-31", "2026-08-31"])
    )
    assert set(post_test[TARGET_STATUS_COLUMN].astype("string")) == {IMMATURE}
    assert post_test[TARGET_COLUMN].isna().all()

    output = write_monthly_target_table(table, tmp_path / "monthly_targets.parquet")
    restored = pd.read_parquet(output, engine="pyarrow")
    pd.testing.assert_frame_equal(restored, table)
    assert restored.attrs["schema_version"] == 1
    assert restored.attrs["final_test_access"].startswith("WITHHELD")
