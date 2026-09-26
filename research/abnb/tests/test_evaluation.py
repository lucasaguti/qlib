import json

import numpy as np
import pandas as pd
import pytest

from research.abnb.pipeline.daily_features import FEATURE_COLUMNS
from research.abnb.pipeline.evaluation import (
    MODEL_COLUMNS,
    _fit_scaled_ridge,
    circular_moving_block_indices,
    evaluate_forecasts,
    hac_mean_test,
    holm_adjust,
    load_development_evaluation_inputs,
    select_ridge_alpha,
    walk_forward_forecasts,
)
from research.abnb.pipeline.targets import TARGET_COLUMN, TARGET_STATUS_COLUMN


def _protocol(replications=200):
    return {
        "periods": {"development_origin_end": "2024-12-31"},
        "eligibility": {"required_feature_names": list(FEATURE_COLUMNS)},
        "training": {
            "minimum_eligible_matured_observations": 24,
            "minimum_inner_validation_predictions": 6,
        },
        "ridge": {"alpha_grid": [0.0001, 0.01, 1.0, 100.0, 10000.0]},
        "uncertainty": {
            "block_length_months": 3,
            "replications": replications,
            "seed": 20260925,
            "confidence_level": 0.95,
            "dependence_sensitivity_block_lengths_months": [2, 4, 6],
        },
        "feature_tests": {"familywise_alpha": 0.05},
    }


def _monthly_table(periods=52):
    sessions = pd.date_range("2020-01-31", periods=periods, freq="ME")
    table = pd.DataFrame({"reference_session": sessions})
    table["issued_at_utc"] = pd.to_datetime(sessions + pd.Timedelta(days=1), utc=True)
    table["label_available_at"] = pd.to_datetime(
        sessions + pd.offsets.MonthEnd(3), utc=True
    )
    index = np.arange(periods, dtype=float)
    for number, feature in enumerate(FEATURE_COLUMNS, 1):
        table[feature] = np.sin(index / (number + 1)) + index * number / 100.0
        table[f"{feature}_STATUS"] = "VALID"
    table[TARGET_COLUMN] = 0.02 + 0.01 * np.sin(index / 3) + 0.001 * index
    table[TARGET_STATUS_COLUMN] = "VALID"
    table["evaluation_partition"] = "DEVELOPMENT"
    return table


def test_development_loader_filters_before_materializing_final_rows(tmp_path):
    table = _monthly_table(6)
    features = table[[
        "reference_session",
        "issued_at_utc",
        *FEATURE_COLUMNS,
        *(f"{name}_STATUS" for name in FEATURE_COLUMNS),
    ]]
    targets = table[[
        "reference_session",
        "issued_at_utc",
        "label_available_at",
        TARGET_COLUMN,
        TARGET_STATUS_COLUMN,
        "evaluation_partition",
    ]].copy()
    targets.loc[4:, "evaluation_partition"] = "FINAL_TEST"
    feature_path = tmp_path / "features.parquet"
    target_path = tmp_path / "targets.parquet"
    protocol_path = tmp_path / "protocol.json"
    features.to_parquet(feature_path, index=False)
    targets.to_parquet(target_path, index=False)
    protocol = _protocol()
    protocol["periods"]["development_origin_end"] = str(
        table.loc[3, "reference_session"].date()
    )
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")

    loaded, _ = load_development_evaluation_inputs(
        feature_path, target_path, protocol_path
    )

    assert len(loaded) == 4
    assert loaded["reference_session"].max() == table.loc[3, "reference_session"]
    assert loaded["evaluation_partition"].eq("DEVELOPMENT").all()


def test_walk_forward_uses_only_labels_matured_at_issuance():
    table = _monthly_table()
    origin = table.iloc[-1]

    forecasts = walk_forward_forecasts(
        table,
        _protocol(),
        forecast_sessions=[origin["reference_session"]],
        include_ablations=False,
    )

    expected = table.loc[
        table["label_available_at"].le(origin["issued_at_utc"])
        & table["reference_session"].lt(origin["reference_session"])
    ]
    result = forecasts.iloc[0]
    assert result["matured_mean_train_count"] == len(expected)
    assert result["ridge_train_count"] == len(expected)
    assert result[MODEL_COLUMNS["expanding_average"]] == pytest.approx(
        expected[TARGET_COLUMN].mean()
    )
    assert result["forecast_status"] == "ELIGIBLE"


def test_alpha_tie_break_chooses_largest_with_equal_inner_mse():
    table = _monthly_table()
    for feature in FEATURE_COLUMNS:
        table[feature] = 1.0
    table[TARGET_COLUMN] = 0.25
    origin = table.iloc[-1]

    alpha, count, scores = select_ridge_alpha(
        table,
        origin,
        model_features=FEATURE_COLUMNS,
        eligibility_features=FEATURE_COLUMNS,
        alpha_grid=[0.001, 1.0, 1000.0],
        minimum_history=24,
        minimum_predictions=6,
        tie_tolerance=1e-12,
    )

    assert count >= 6
    assert len(set(scores.values())) == 1
    assert alpha == 1000.0


def test_future_rows_cannot_change_an_earlier_forecast_or_selected_alpha():
    table = _monthly_table(56)
    forecast_session = table.iloc[48]["reference_session"]
    first = walk_forward_forecasts(
        table,
        _protocol(),
        forecast_sessions=[forecast_session],
        include_ablations=False,
    ).iloc[0]
    changed = table.copy()
    future = changed["reference_session"].gt(forecast_session)
    changed.loc[future, list(FEATURE_COLUMNS)] = 1_000_000.0
    changed.loc[future, TARGET_COLUMN] = -1_000_000.0
    second = walk_forward_forecasts(
        changed,
        _protocol(),
        forecast_sessions=[forecast_session],
        include_ablations=False,
    ).iloc[0]

    assert second["ridge_alpha"] == first["ridge_alpha"]
    assert second[MODEL_COLUMNS["ridge"]] == pytest.approx(
        first[MODEL_COLUMNS["ridge"]]
    )


def test_scaling_is_fitted_from_training_fold_only():
    table = _monthly_table(30)
    train = table.iloc[:24]
    forecast = table.iloc[24].copy()
    prediction = _fit_scaled_ridge(train, forecast, FEATURE_COLUMNS, 1.0)
    changed_forecast = forecast.copy()
    changed_forecast.loc[list(FEATURE_COLUMNS)] += 1000.0
    changed_prediction = _fit_scaled_ridge(
        train, changed_forecast, FEATURE_COLUMNS, 1.0
    )

    assert np.isfinite(prediction)
    assert changed_prediction != pytest.approx(prediction)
    pd.testing.assert_frame_equal(train, table.iloc[:24])


def test_circular_blocks_are_consecutive_and_reproducible():
    first = circular_moving_block_indices(5, 3, 20, np.random.default_rng(7))
    second = circular_moving_block_indices(5, 3, 20, np.random.default_rng(7))

    np.testing.assert_array_equal(first, second)
    assert first.shape == (20, 5)
    assert np.all((first[:, 1:3] - first[:, :2]) % 5 == 1)


def test_holm_adjustment_preserves_original_order_and_monotonicity():
    adjusted = holm_adjust([0.04, 0.001, 0.02, 0.5])

    assert adjusted == pytest.approx([0.08, 0.004, 0.06, 0.5])
    assert hac_mean_test([1.0, 2.0, 3.0, 4.0])["estimate"] == pytest.approx(2.5)


def test_metrics_bootstrap_temporal_stability_and_holm_family_are_reported():
    actual = np.array([0.1, -0.1, 0.2, -0.2, 0.15, -0.05, 0.12, -0.08])
    forecasts = pd.DataFrame(
        {
            "reference_session": pd.date_range("2024-01-31", periods=8, freq="ME"),
            "forecast_status": "ELIGIBLE",
            "actual": actual,
            MODEL_COLUMNS["zero_return"]: 0.0,
            MODEL_COLUMNS["expanding_average"]: 0.03,
            MODEL_COLUMNS["ridge"]: actual * 0.8,
        }
    )
    for number, feature in enumerate(FEATURE_COLUMNS, 1):
        forecasts[f"forecast_without_{feature}"] = actual * (0.8 - number / 100)

    result = evaluate_forecasts(forecasts, _protocol(replications=100))

    ridge = result["models"]["ridge"]
    assert ridge["estimates"]["mae"] == pytest.approx(np.mean(np.abs(actual * 0.2)))
    assert ridge["estimates"]["directional_accuracy"] == 1.0
    assert len(ridge["temporal_stability"]["halves"]) == 2
    assert len(ridge["primary_block_bootstrap_95_intervals"]["rmse"]) == 2
    comparison = result["paired_comparisons"][
        "ridge_minus_expanding_average_squared_error"
    ]
    assert comparison["estimate"] < 0
    assert set(comparison["sensitivity_block_bootstrap_95_intervals"]) == {
        "2",
        "4",
        "6",
    }
    ablations = result["leave_one_feature_out_diagnostics"]
    assert ablations["family_size"] == 8
    assert all("holm_adjusted_p_value" in item for item in ablations["results"])


def test_zero_forecast_is_neutral_not_an_automatic_positive_direction():
    actual = np.array([0.1, -0.1, 0.2, -0.2, 0.3, -0.3])
    forecasts = pd.DataFrame(
        {
            "reference_session": pd.date_range("2024-01-31", periods=6, freq="ME"),
            "forecast_status": "ELIGIBLE",
            "actual": actual,
            MODEL_COLUMNS["zero_return"]: 0.0,
            MODEL_COLUMNS["expanding_average"]: 0.01,
            MODEL_COLUMNS["ridge"]: actual,
        }
    )
    for feature in FEATURE_COLUMNS:
        forecasts[f"forecast_without_{feature}"] = actual * 0.9

    result = evaluate_forecasts(forecasts, _protocol(replications=50))

    assert result["models"]["zero_return"]["estimates"]["directional_accuracy"] == 0.0
    assert result["models"]["ridge"]["estimates"]["directional_accuracy"] == 1.0
    assert result["models"]["ridge"]["estimates"][
        "directional_class_frequency_baseline"
    ] == 0.5
