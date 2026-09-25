# ABNB Equity Forecasting Research Charter

> **Innate document — research contract.** This file captures the stable project intent and methodology. Agents must not edit it unless the user explicitly changes the research charter. Implementation progress belongs in the dynamic project documents.

## Purpose and boundaries

This academic project asks whether information demonstrably available at a historical forecast date can improve out-of-sample forecasts of Airbnb, Inc. (`NASDAQ: ABNB`) returns over simple benchmarks.

- The project does not presume that ABNB is predictable.
- It produces research forecasts, not investment advice, and must never execute live trades.
- Negative and inconclusive results are valid outcomes.
- Forecast accuracy is evaluated independently of any later hypothetical signal analysis.

Secondary questions concern the incremental value and stability of ABNB price history, broad-market conditions, and travel-peer performance, plus sensitivity to limited history, overlapping outcomes, and repeated model searches.

## Forecast contract

One forecast origin is created from the final ABNB trading session of each calendar month.

The primary target is split- and cash-dividend-adjusted total return through the final trading session of the calendar month three months later:

`R(t,t+3m) = P(maturity) / P(reference) - 1`

Three calendar months must not be represented as 63 trading sessions. Implementations must distinguish and persist:

1. month-end reference close;
2. information cutoff;
3. forecast issuance time—the next regular XNYS session open;
4. target maturity time; and
5. any later executable price.

The primary output is expected three-month percentage return. An unadjusted future share-price target is a separate extension because corporate actions can make it differ from an adjusted-return forecast.

## Initial comparison

All eligible methods use identical forecast origins:

1. **Zero-return benchmark:** always predicts `0`.
2. **Expanding historical-average benchmark:** averages only forward returns that have matured by the current issuance time.
3. **Ridge regression:** a transparent regularized baseline using only the predefined predictors below.

More complex models require a separately specified experiment and cannot replace this confirmatory comparison merely because of better retrospective performance.

## Locked initial predictors

Calculate indicators on daily adjusted-price histories, then sample at month-end. Session offsets are positions on the shared XNYS regular-session calendar.

| Feature | Definition |
|---|---|
| `ABNB_MOM_12_2` | `ABNB[t-21] / ABNB[t-252] - 1` |
| `ABNB_RET_21D` | `ABNB[t] / ABNB[t-21] - 1` |
| `ABNB_RSI_14` | Wilder RSI over 14 price changes, with explicit rising, falling, and flat cases |
| `ABNB_EMA_GAP_20` | Adjusted close relative to its 20-session EMA |
| `ABNB_MACD_HIST_NORM` | 12/26/9 MACD histogram divided by adjusted close |
| `SPY_RET_5D` | `SPY[t] / SPY[t-5] - 1` |
| `PEER_RET_5D` | Equal-weight mean of five-session EXPE and BKNG returns |
| `SPY_RVOL_20D` | Annualized sample volatility of the latest 20 SPY log returns |

MAR, HLT, fundamentals, operating metrics, macro series, industry data, analyst estimates, and volume are excluded from the initial feature set. They are possible predefined extensions only.

## Data and feature contract

- Align ABNB, SPY, EXPE, and BKNG to an exact, versioned XNYS regular-session calendar.
- Use finite, positive USD closing prices with one consistent split-and-cash-dividend adjustment convention.
- Never silently substitute raw close for adjusted close.
- Require exact cross-security session-date matches; do not fill, interpolate, or shorten windows.
- Never replace a missing peer with the other peer or alter equal weights.
- Reset and reseed RSI, EMA, and MACD after a missing or invalid price.
- Preserve a status for every nullable feature: insufficient history, missing source observation, invalid price, unavailable by cutoff, or valid.

An observation is admissible only when both its exact price version and embedded corporate-action state were available by forecast issuance:

`max(price_available_at, adjustment_state_available_at) <= forecast_issued_at`

Retain provider and instrument IDs, source field and observation time, currency and units, adjustment convention, corporate-action version/effective semantics, both availability timestamps and evidence, retrieval time, dataset version and checksums, calendar identity/version, and usage restrictions. Revisions create new immutable source versions; later changes must never rewrite the historical information set.

Keep four data layers distinct: immutable raw extraction, source-faithful standardized interim data, modeling-ready processed data, and versioned experimental snapshots. Use institutional or licensed sources only when extraction, retention, ML, backup, and processing rights are verified.

## Validation and inference contract

Use expanding-window walk-forward evaluation, never a random split. At each origin:

1. admit only information available by issuance;
2. train only on labels whose three-month outcomes have matured;
3. fit imputation, scaling, feature selection, and all learned transforms inside that training fold;
4. tune hyperparameters with chronology-respecting inner validation; and
5. produce one out-of-sample forecast before advancing.

Select and freeze the final test period before final evaluation. Keep it isolated from feature design, preprocessing, model selection, and tuning; log every authorized access.

Monthly three-month outcomes overlap. Uncertainty, comparisons, direction tests, and effective sample size must account for serial dependence. Label exploratory work clearly, control for repeated searches, and do not treat a favorable isolated window as confirmation.

## Evaluation and success criteria

Report MAE, RMSE, benchmark-relative out-of-sample R-squared, directional accuracy against class-frequency baselines, temporal stability, dependence-aware uncertainty, and sensitivity to reasonable choices. Price-target error is allowed only under a separately defined price convention.

No single metric, in-sample fit, profitable hypothetical signal, or isolated interval establishes success. Success also requires correct contracts, complete lineage, reproducible data/features/config/code, disclosed assumptions and limitations, and candid reporting.

## Controlled extensions

Buy/sell/hold analysis requires separate authorization and thresholds fixed before evaluation. It must define executable prices, costs, turnover, exposure/risk, uncertainty, and passive comparators. It remains downstream of forecast evaluation and must never connect to live brokerage execution.
