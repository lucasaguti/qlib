import copy
import math
from pathlib import Path

import exchange_calendars as xcals
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
    build_daily_panel,
)

RAW_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"


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
    for length in range(required):
        result = function([100.0] * length)
        assert result == FeatureResult(None, INSUFFICIENT_HISTORY)


@pytest.mark.parametrize(
    ("function", "closes"),
    [
        (abnb_mom_12_2, [100.0] * 253),
        (abnb_ret_21d, [100.0] * 22),
        (abnb_rsi_14, [100.0] * 15),
        (abnb_ema_gap_20, [100.0] * 20),
        (abnb_macd_hist_norm, [100.0] * 34),
        (spy_ret_5d, [100.0] * 6),
        (spy_rvol_20d, [100.0] * 21),
    ],
)
def test_first_valid_output_is_exactly_at_documented_boundary(function, closes):
    assert function(closes).status == VALID


def test_peer_first_valid_output_is_on_sixth_exact_session():
    for length in range(6):
        assert peer_ret_5d([100.0] * length, [100.0] * length) == FeatureResult(
            None, INSUFFICIENT_HISTORY
        )
    assert peer_ret_5d([100.0] * 6, [100.0] * 6) == FeatureResult(0.0, VALID)


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


def test_session_offsets_follow_xnys_positions_not_calendar_days():
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2025-11-21", "2025-12-01")
    assert len(sessions) == 6
    assert (sessions[-1] - sessions[0]).days == 10

    closes = pd.Series([100.0, 102.0, 104.0, 106.0, 108.0, 110.0], index=sessions)
    result = spy_ret_5d(closes, anchor_date=sessions[-1])

    assert result.status == VALID
    assert result.value == pytest.approx(0.1)


def test_spy_requires_an_exact_anchor_date_and_does_not_use_previous_session():
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2026-01-02", "2026-01-12")
    anchor = sessions[-1]
    closes_without_anchor = pd.Series([100.0] * 6, index=sessions[-7:-1])

    with pytest.raises(ValueError, match="must end on anchor date"):
        spy_ret_5d(closes_without_anchor, anchor_date=anchor)

    closes_on_grid = pd.Series([100.0] * 6, index=sessions[-6:])
    statuses = pd.Series(
        [VALID] * 5 + [MISSING_SOURCE], index=sessions[-6:]
    )
    assert spy_ret_5d(
        closes_on_grid, statuses, anchor_date=anchor
    ) == FeatureResult(None, MISSING_SOURCE)


@pytest.mark.parametrize(
    ("unavailable_peer", "expected_status"),
    [("EXPE", MISSING_SOURCE), ("BKNG", UNAVAILABLE_BY_CUTOFF)],
)
def test_peer_return_is_null_if_either_peer_is_unavailable(
    unavailable_peer, expected_status
):
    dates = xcals.get_calendar("XNYS").sessions_in_range(
        "2026-01-02", "2026-01-09"
    )
    expe_statuses = pd.Series([VALID] * 6, index=dates)
    bkng_statuses = pd.Series([VALID] * 6, index=dates)
    if unavailable_peer == "EXPE":
        expe_statuses.iloc[-1] = MISSING_SOURCE
    else:
        bkng_statuses.iloc[-1] = UNAVAILABLE_BY_CUTOFF

    result = peer_ret_5d(
        pd.Series([100.0] * 6, index=dates),
        pd.Series([200.0] * 6, index=dates),
        expe_statuses,
        bkng_statuses,
        anchor_date=dates[-1],
    )

    assert result == FeatureResult(None, expected_status)


def test_peer_histories_must_both_end_on_the_exact_anchor_date():
    dates = xcals.get_calendar("XNYS").sessions_in_range(
        "2026-01-02", "2026-01-12"
    )
    anchor = dates[-1]
    prior_dates = dates[-7:-1]

    with pytest.raises(ValueError, match="must end on anchor date"):
        peer_ret_5d(
            pd.Series([100.0] * 6, index=prior_dates),
            pd.Series([200.0] * 6, index=prior_dates),
            anchor_date=anchor,
        )


@pytest.mark.parametrize(
    ("function", "required", "fresh_segment"),
    [
        (abnb_rsi_14, 15, [100.0 + value * value for value in range(15)]),
        (abnb_ema_gap_20, 20, [100.0 + value * value for value in range(20)]),
        (
            abnb_macd_hist_norm,
            34,
            [100.0 + value * value for value in range(34)],
        ),
    ],
)
def test_recursive_indicators_restart_seed_after_gap(
    function, required, fresh_segment
):
    old_segment = [500.0 - value for value in range(40)]
    closes = old_segment + [None] + fresh_segment[:-1]
    statuses = [VALID] * len(old_segment) + [MISSING_SOURCE] + [VALID] * (
        required - 1
    )

    assert function(closes, statuses) == FeatureResult(None, MISSING_SOURCE)

    closes.append(fresh_segment[-1])
    statuses.append(VALID)
    restarted = function(closes, statuses)
    freshly_seeded = function(fresh_segment)
    assert restarted.status == VALID
    assert restarted.value == pytest.approx(freshly_seeded.value)


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
def test_single_security_functions_do_not_mutate_inputs(function, required):
    closes = [100.0 + value for value in range(required)]
    statuses = [VALID] * required
    original_closes = copy.deepcopy(closes)
    original_statuses = copy.deepcopy(statuses)

    function(closes, statuses)

    assert closes == original_closes
    assert statuses == original_statuses


def test_peer_function_does_not_mutate_inputs():
    expe = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    bkng = [200.0, 201.0, 202.0, 203.0, 204.0, 205.0]
    expe_statuses = [VALID] * 6
    bkng_statuses = [VALID] * 6
    originals = copy.deepcopy((expe, bkng, expe_statuses, bkng_statuses))

    peer_ret_5d(expe, bkng, expe_statuses, bkng_statuses)

    assert (expe, bkng, expe_statuses, bkng_statuses) == originals


def _panel_history(panel, security, anchor):
    history = panel.xs(security, level="security").loc[:anchor]
    return history["adjusted_close"], history["status"]


@pytest.mark.parametrize("anchor", ["2026-09-22", "2026-09-23"])
def test_real_gap_invalidates_abnb_recursive_segments_and_peer_window(anchor):
    panel = build_daily_panel(RAW_ROOT, end="2026-09-23")
    anchor_date = pd.Timestamp(anchor)

    if anchor == "2026-09-22":
        prior_anchor = pd.Timestamp("2026-09-21")
        prior_abnb = _panel_history(panel, "ABNB", prior_anchor)
        for function in (abnb_rsi_14, abnb_ema_gap_20, abnb_macd_hist_norm):
            assert function(*prior_abnb).status == VALID
        prior_expe = _panel_history(panel, "EXPE", prior_anchor)
        prior_bkng = _panel_history(panel, "BKNG", prior_anchor)
        assert peer_ret_5d(
            prior_expe[0],
            prior_bkng[0],
            prior_expe[1],
            prior_bkng[1],
            anchor_date=prior_anchor,
        ).status == VALID

    abnb_closes, abnb_statuses = _panel_history(panel, "ABNB", anchor_date)

    for function in (abnb_rsi_14, abnb_ema_gap_20, abnb_macd_hist_norm):
        assert function(abnb_closes, abnb_statuses) == FeatureResult(
            None, MISSING_SOURCE
        )

    expe_closes, expe_statuses = _panel_history(panel, "EXPE", anchor_date)
    bkng_closes, bkng_statuses = _panel_history(panel, "BKNG", anchor_date)
    assert peer_ret_5d(
        expe_closes,
        bkng_closes,
        expe_statuses,
        bkng_statuses,
        anchor_date=anchor_date,
    ) == FeatureResult(None, MISSING_SOURCE)
