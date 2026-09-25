import math

import pandas as pd
import pytest

from research.abnb.pipeline.features import (
    INSUFFICIENT_HISTORY,
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
from research.abnb.pipeline.panel import (
    INVALID_PRICE,
    MISSING_SOURCE,
    UNAVAILABLE_BY_CUTOFF,
    VALID,
)


def test_fixed_return_features_use_exact_required_session_offsets():
    closes = [100.0 + value for value in range(253)]

    assert abnb_mom_12_2(closes) == FeatureResult(331.0 / 100.0 - 1.0, VALID)
    assert abnb_ret_21d(closes) == FeatureResult(352.0 / 331.0 - 1.0, VALID)
    assert spy_ret_5d(closes) == FeatureResult(352.0 / 347.0 - 1.0, VALID)


@pytest.mark.parametrize(
    ("function", "required"),
    [
        (abnb_mom_12_2, 253),
        (abnb_ret_21d, 22),
        (abnb_rsi_14, 15),
        (abnb_ema_gap_20, 20),
        (abnb_macd_hist_norm, 34),
        (spy_ret_5d, 6),
        (spy_rvol_20d, 21),
    ],
)
def test_each_single_security_feature_enforces_minimum_history(function, required):
    result = function([100.0] * (required - 1))
    assert result == FeatureResult(None, INSUFFICIENT_HISTORY)


def test_momentum_requires_every_session_not_only_priced_endpoints():
    closes = [100.0] * 253
    statuses = [VALID] * 253
    closes[100] = None
    statuses[100] = MISSING_SOURCE

    assert abnb_mom_12_2(closes, statuses) == FeatureResult(None, MISSING_SOURCE)


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        ([float(value) for value in range(1, 16)], 100.0),
        ([float(value) for value in range(15, 0, -1)], 0.0),
        ([10.0] * 15, 50.0),
    ],
)
def test_rsi_explicit_rising_falling_and_flat_cases(closes, expected):
    assert abnb_rsi_14(closes) == FeatureResult(expected, VALID)


def test_rsi_uses_wilder_recursion_after_initial_simple_average():
    closes = [
        10.0,
        11.0,
        10.0,
        12.0,
        11.0,
        14.0,
        13.0,
        17.0,
        16.0,
        21.0,
        20.0,
        26.0,
        25.0,
        32.0,
        31.0,
        40.0,
    ]
    gains = [1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6, 0, 7, 0]
    losses = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
    average_gain = (13 * (sum(gains) / 14) + 9) / 14
    average_loss = (13 * (sum(losses) / 14)) / 14
    expected = 100 - 100 / (1 + average_gain / average_loss)

    assert abnb_rsi_14(closes).value == pytest.approx(expected)


def test_ema_gap_seeds_on_twentieth_close_then_recurses():
    closes = [float(value) for value in range(1, 22)]
    seed = sum(range(1, 21)) / 20
    ema = (2 / 21) * 21 + (19 / 21) * seed

    assert abnb_ema_gap_20(closes).value == pytest.approx(21 / ema - 1)


def test_macd_first_histogram_is_close_34_with_sma_seeds():
    closes = [float(value * value + 100) for value in range(1, 35)]
    alpha12, alpha26 = 2 / 13, 2 / 27
    ema12 = sum(closes[:12]) / 12
    ema26 = sum(closes[:26]) / 26
    for close in closes[12:26]:
        ema12 = alpha12 * close + (1 - alpha12) * ema12
    macd = [ema12 - ema26]
    for close in closes[26:]:
        ema12 = alpha12 * close + (1 - alpha12) * ema12
        ema26 = alpha26 * close + (1 - alpha26) * ema26
        macd.append(ema12 - ema26)
    expected = (macd[-1] - sum(macd) / 9) / closes[-1]

    assert len(macd) == 9
    assert abnb_macd_hist_norm(closes).value == pytest.approx(expected)


def test_recursive_feature_resets_and_reseeds_after_missing_close():
    closes = [100.0] * 20 + [None] + [200.0] * 19
    statuses = [VALID] * 20 + [MISSING_SOURCE] + [VALID] * 19
    assert abnb_ema_gap_20(closes, statuses) == FeatureResult(None, MISSING_SOURCE)

    closes.append(220.0)
    statuses.append(VALID)
    expected_ema = (19 * 200.0 + 220.0) / 20
    assert abnb_ema_gap_20(closes, statuses).value == pytest.approx(
        220 / expected_ema - 1
    )


def test_peer_return_requires_both_peers_on_identical_sessions():
    dates = pd.bdate_range("2026-01-02", periods=6)
    expe = pd.Series([100, 100, 100, 100, 100, 110], index=dates)
    bkng = pd.Series([200, 200, 200, 200, 200, 180], index=dates)
    assert peer_ret_5d(expe, bkng).value == pytest.approx(0.0)

    with pytest.raises(ValueError, match="identical session indexes"):
        peer_ret_5d(expe, bkng.set_axis(dates + pd.Timedelta(days=1)))


def test_peer_return_fails_whole_basket_when_one_peer_is_missing():
    expe = [100.0] * 6
    bkng = [200.0] * 6
    expe_statuses = [VALID] * 5 + [MISSING_SOURCE]

    assert peer_ret_5d(expe, bkng, expe_statuses) == FeatureResult(None, MISSING_SOURCE)


def test_realized_volatility_uses_20_log_returns_sample_sd_and_annualizes():
    log_returns = [0.01, -0.02, 0.03, -0.01, 0.0] * 4
    closes = [100.0]
    for log_return in log_returns:
        closes.append(closes[-1] * math.exp(log_return))
    mean = sum(log_returns) / 20
    sample_variance = sum((value - mean) ** 2 for value in log_returns) / 19
    expected = math.sqrt(252 * sample_variance)

    assert spy_rvol_20d(closes).value == pytest.approx(expected)


@pytest.mark.parametrize("bad_value", [0.0, -1.0, float("inf")])
def test_unusable_numeric_close_is_invalid_without_explicit_status(bad_value):
    closes = [100.0] * 6
    closes[-1] = bad_value
    assert spy_ret_5d(closes) == FeatureResult(None, INVALID_PRICE)


def test_explicit_cutoff_status_is_preserved():
    statuses = [VALID] * 5 + [UNAVAILABLE_BY_CUTOFF]
    assert spy_ret_5d([100.0] * 6, statuses) == FeatureResult(
        None, UNAVAILABLE_BY_CUTOFF
    )


def test_only_final_required_window_controls_nonrecursive_return():
    closes = [None] + [100.0] * 6
    statuses = [MISSING_SOURCE] + [VALID] * 6
    assert spy_ret_5d(closes, statuses) == FeatureResult(0.0, VALID)
