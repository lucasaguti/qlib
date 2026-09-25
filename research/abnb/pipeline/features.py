"""Daily feature functions for the locked ABNB forecasting predictors.

Each public function consumes adjusted closes ordered from oldest to newest and
returns a :class:`FeatureResult` for the final supplied session.  Inputs must
already be rows on the common daily XNYS session grid; these functions neither
resample data nor know about monthly forecast origins or model fitting.

When statuses are omitted, missing values are treated as ``MISSING_SOURCE`` and
nonfinite or nonpositive values as ``INVALID_PRICE``.  Passing statuses from the
canonical panel is preferred because it preserves cutoff and source semantics.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, NamedTuple, Sequence

import numpy as np
import pandas as pd

from research.abnb.pipeline.panel import (
    INVALID_PRICE,
    MISSING_SOURCE,
    UNAVAILABLE_BY_CUTOFF,
    VALID,
)

INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
FEATURE_STATUSES = (
    VALID,
    INSUFFICIENT_HISTORY,
    MISSING_SOURCE,
    INVALID_PRICE,
    UNAVAILABLE_BY_CUTOFF,
)

_FAILURE_PRIORITY = {
    MISSING_SOURCE: 0,
    INVALID_PRICE: 1,
    UNAVAILABLE_BY_CUTOFF: 2,
}


class FeatureResult(NamedTuple):
    """A nullable feature value and its indicator-specific status."""

    value: float | None
    status: str


class _PriceHistory(NamedTuple):
    values: tuple[float | None, ...]
    statuses: tuple[str, ...]
    index: pd.Index | None


def _as_items(
    values: Sequence[Any] | pd.Series, name: str
) -> tuple[list[Any], pd.Index | None]:
    if isinstance(values, pd.Series):
        return values.tolist(), values.index
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be a one-dimensional sequence, not text")
    try:
        return list(values), None
    except TypeError as exc:
        raise TypeError(f"{name} must be a one-dimensional sequence") from exc


def _coerce_history(
    closes: Sequence[Any] | pd.Series,
    statuses: Sequence[Any] | pd.Series | None,
    *,
    name: str,
) -> _PriceHistory:
    raw_closes, close_index = _as_items(closes, name)
    if statuses is None:
        raw_statuses = [None] * len(raw_closes)
        status_index = None
    else:
        raw_statuses, status_index = _as_items(statuses, f"{name}_statuses")
        if len(raw_statuses) != len(raw_closes):
            raise ValueError(f"{name} and its statuses must have equal lengths")
        if (
            close_index is not None
            and status_index is not None
            and not close_index.equals(status_index)
        ):
            raise ValueError(
                f"{name} and its statuses must have identical session indexes"
            )

    values: list[float | None] = []
    normalized_statuses: list[str] = []
    for raw_value, supplied_status in zip(raw_closes, raw_statuses):
        missing = pd.isna(raw_value)
        if not isinstance(missing, (bool, np.bool_)):
            raise TypeError(f"{name} must contain scalar close values")

        if missing:
            value = None
            derived_status = MISSING_SOURCE
        else:
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise TypeError(f"{name} must contain numeric close values") from exc
            derived_status = (
                VALID if math.isfinite(value) and value > 0 else INVALID_PRICE
            )

        if supplied_status is None or pd.isna(supplied_status):
            status = derived_status
        else:
            status = str(supplied_status)
            if status not in (
                VALID,
                MISSING_SOURCE,
                INVALID_PRICE,
                UNAVAILABLE_BY_CUTOFF,
            ):
                raise ValueError(f"Unrecognized source status for {name}: {status!r}")
            if status == VALID and derived_status != VALID:
                status = derived_status

        values.append(value if derived_status == VALID else None)
        normalized_statuses.append(status)

    return _PriceHistory(tuple(values), tuple(normalized_statuses), close_index)


def _failure_status(history: _PriceHistory, required: int) -> str | None:
    """Return the controlling failure in the final required-session window."""

    failures = {
        status for status in history.statuses[-required:] if status != VALID
    }
    if not failures:
        return None
    return min(failures, key=_FAILURE_PRIORITY.__getitem__)


def _fixed_window(
    closes: Sequence[Any] | pd.Series,
    statuses: Sequence[Any] | pd.Series | None,
    required: int,
    *,
    name: str,
) -> tuple[_PriceHistory, FeatureResult | None]:
    history = _coerce_history(closes, statuses, name=name)
    if len(history.values) < required:
        return history, FeatureResult(None, INSUFFICIENT_HISTORY)
    failure = _failure_status(history, required)
    if failure is not None:
        return history, FeatureResult(None, failure)
    return history, None


def abnb_mom_12_2(
    closes: Sequence[Any] | pd.Series,
    statuses: Sequence[Any] | pd.Series | None = None,
) -> FeatureResult:
    """Return ``close[t-21] / close[t-252] - 1`` from 253 sessions."""

    history, failure = _fixed_window(closes, statuses, 253, name="abnb_closes")
    if failure:
        return failure
    window = history.values[-253:]
    return FeatureResult(window[-22] / window[0] - 1.0, VALID)  # type: ignore[operator]


def abnb_ret_21d(
    closes: Sequence[Any] | pd.Series,
    statuses: Sequence[Any] | pd.Series | None = None,
) -> FeatureResult:
    """Return ``close[t] / close[t-21] - 1`` from 22 sessions."""

    history, failure = _fixed_window(closes, statuses, 22, name="abnb_closes")
    if failure:
        return failure
    window = history.values[-22:]
    return FeatureResult(window[-1] / window[0] - 1.0, VALID)  # type: ignore[operator]


def _latest_valid_segment(
    history: _PriceHistory, required: int
) -> tuple[list[float], FeatureResult | None]:
    if len(history.values) < required:
        return [], FeatureResult(None, INSUFFICIENT_HISTORY)
    failure = _failure_status(history, required)
    if failure is not None:
        return [], FeatureResult(None, failure)

    last_failure = -1
    for position, status in enumerate(history.statuses):
        if status != VALID:
            last_failure = position
    segment = history.values[last_failure + 1 :]
    return [value for value in segment if value is not None], None


def abnb_rsi_14(
    closes: Sequence[Any] | pd.Series,
    statuses: Sequence[Any] | pd.Series | None = None,
) -> FeatureResult:
    """Return 14-change Wilder RSI, resetting after an unusable close."""

    history = _coerce_history(closes, statuses, name="abnb_closes")
    segment, failure = _latest_valid_segment(history, 15)
    if failure:
        return failure

    changes = [current - previous for previous, current in zip(segment, segment[1:])]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    average_gain = sum(gains[:14]) / 14.0
    average_loss = sum(losses[:14]) / 14.0
    for gain, loss in zip(gains[14:], losses[14:]):
        average_gain = (13.0 * average_gain + gain) / 14.0
        average_loss = (13.0 * average_loss + loss) / 14.0

    if average_gain == 0.0 and average_loss == 0.0:
        value = 50.0
    elif average_loss == 0.0:
        value = 100.0
    elif average_gain == 0.0:
        value = 0.0
    else:
        value = 100.0 - 100.0 / (1.0 + average_gain / average_loss)
    return FeatureResult(value, VALID)


def _seeded_ema(values: Sequence[float], span: int) -> float:
    ema = sum(values[:span]) / span
    alpha = 2.0 / (span + 1.0)
    for value in values[span:]:
        ema = alpha * value + (1.0 - alpha) * ema
    return ema


def abnb_ema_gap_20(
    closes: Sequence[Any] | pd.Series,
    statuses: Sequence[Any] | pd.Series | None = None,
) -> FeatureResult:
    """Return adjusted close relative to its SMA-seeded 20-session EMA."""

    history = _coerce_history(closes, statuses, name="abnb_closes")
    segment, failure = _latest_valid_segment(history, 20)
    if failure:
        return failure
    ema = _seeded_ema(segment, 20)
    return FeatureResult(segment[-1] / ema - 1.0, VALID)


def abnb_macd_hist_norm(
    closes: Sequence[Any] | pd.Series,
    statuses: Sequence[Any] | pd.Series | None = None,
) -> FeatureResult:
    """Return the SMA-seeded 12/26/9 MACD histogram divided by close."""

    history = _coerce_history(closes, statuses, name="abnb_closes")
    segment, failure = _latest_valid_segment(history, 34)
    if failure:
        return failure

    ema12 = sum(segment[:12]) / 12.0
    alpha12 = 2.0 / 13.0
    ema26 = sum(segment[:26]) / 26.0
    alpha26 = 2.0 / 27.0

    # Advance EMA12 through close 26 to create the first aligned MACD value.
    for close in segment[12:26]:
        ema12 = alpha12 * close + (1.0 - alpha12) * ema12
    macd_values = [ema12 - ema26]
    for close in segment[26:]:
        ema12 = alpha12 * close + (1.0 - alpha12) * ema12
        ema26 = alpha26 * close + (1.0 - alpha26) * ema26
        macd_values.append(ema12 - ema26)

    signal = _seeded_ema(macd_values, 9)
    histogram = macd_values[-1] - signal
    return FeatureResult(histogram / segment[-1], VALID)


def spy_ret_5d(
    closes: Sequence[Any] | pd.Series,
    statuses: Sequence[Any] | pd.Series | None = None,
) -> FeatureResult:
    """Return SPY's five-session adjusted-close return."""

    history, failure = _fixed_window(closes, statuses, 6, name="spy_closes")
    if failure:
        return failure
    window = history.values[-6:]
    return FeatureResult(window[-1] / window[0] - 1.0, VALID)  # type: ignore[operator]


def peer_ret_5d(
    expe_closes: Sequence[Any] | pd.Series,
    bkng_closes: Sequence[Any] | pd.Series,
    expe_statuses: Sequence[Any] | pd.Series | None = None,
    bkng_statuses: Sequence[Any] | pd.Series | None = None,
) -> FeatureResult:
    """Return the equal-weight EXPE/BKNG five-session return.

    Pandas inputs must have identical indexes, which makes the exact-date join
    requirement explicit.  Other sequences must already be identically aligned.
    """

    expe = _coerce_history(expe_closes, expe_statuses, name="expe_closes")
    bkng = _coerce_history(bkng_closes, bkng_statuses, name="bkng_closes")
    if len(expe.values) != len(bkng.values):
        raise ValueError("EXPE and BKNG histories must have equal lengths")
    if (
        expe.index is not None
        and bkng.index is not None
        and not expe.index.equals(bkng.index)
    ):
        raise ValueError("EXPE and BKNG histories must have identical session indexes")
    if len(expe.values) < 6:
        return FeatureResult(None, INSUFFICIENT_HISTORY)

    failures = [
        status
        for history in (expe, bkng)
        if (status := _failure_status(history, 6))
    ]
    if failures:
        return FeatureResult(None, min(failures, key=_FAILURE_PRIORITY.__getitem__))

    expe_window = expe.values[-6:]
    bkng_window = bkng.values[-6:]
    expe_return = expe_window[-1] / expe_window[0] - 1.0  # type: ignore[operator]
    bkng_return = bkng_window[-1] / bkng_window[0] - 1.0  # type: ignore[operator]
    return FeatureResult((expe_return + bkng_return) / 2.0, VALID)


def spy_rvol_20d(
    closes: Sequence[Any] | pd.Series,
    statuses: Sequence[Any] | pd.Series | None = None,
) -> FeatureResult:
    """Return annualized sample volatility of SPY's latest 20 log returns."""

    history, failure = _fixed_window(closes, statuses, 21, name="spy_closes")
    if failure:
        return failure
    window = history.values[-21:]
    log_returns = [
        math.log(current / previous)  # type: ignore[operator]
        for previous, current in zip(window, window[1:])
    ]
    return FeatureResult(math.sqrt(252.0) * statistics.stdev(log_returns), VALID)
