# Frozen Final-Test Expanding-Window Forecast Evaluation

> This is the single authorized evaluation of EVAL-PROTOCOL-001's frozen
> 12-origin final block. The methodology was not changed after access.
> Provider-rights and historical point-in-time evidence remain unresolved limitations.

Primary finding: **INCONCLUSIVE** — The 95% block interval or HAC(2) test does not establish a directional difference.

Scored origins: **12** (2025-06-30 through 2026-05-29).

## Primary metrics

| Model | MAE [95% CI] | RMSE [95% CI] | R^2 vs zero [95% CI] | R^2 vs expanding mean [95% CI] | Directional accuracy [95% CI] | Class-frequency baseline |
|---|---:|---:|---:|---:|---:|---:|
| Zero return | 0.106710 [0.072433, 0.157049] | 0.139749 [0.082967, 0.203115] | 0.000000 [0.000000, 0.000000] | 0.008834 [-0.005317, 0.045805] | 0.000000 [0.000000, 0.000000] | 0.583 |
| Matured expanding average | 0.107233 [0.072584, 0.156831] | 0.140370 [0.083056, 0.203106] | -0.008913 [-0.048004, 0.005289] | 0.000000 [0.000000, 0.000000] | 0.500000 [0.250000, 0.750000] | 0.583 |
| Eight-feature Ridge | 0.106599 [0.072608, 0.155762] | 0.138438 [0.083394, 0.199932] | 0.018669 [-0.018989, 0.031123] | 0.027338 [-0.009855, 0.040234] | 0.416667 [0.250000, 0.583333] | 0.583 |

## Dependence-aware primary comparison

The paired mean squared-error difference is Ridge minus the matured
expanding-average benchmark, so negative values favor Ridge.

- Estimate: -0.00053867
- Circular three-month block-bootstrap 95% interval: [-0.00130234, 0.00007841]
- Newey-West HAC(2) two-sided p-value: 0.264871

## Temporal stability

Temporal stability uses two fixed chronological halves:

| Model | First-half MAE | Second-half MAE | First-half RMSE | Second-half RMSE |
|---|---:|---:|---:|---:|
| Zero return | 0.087600 | 0.125821 | 0.098229 | 0.171495 |
| Matured expanding average | 0.088512 | 0.125954 | 0.099564 | 0.171740 |
| Eight-feature Ridge | 0.088776 | 0.124421 | 0.099297 | 0.168732 |

## Eligibility accounting

- `ELIGIBLE`: 12

## Leave-one-feature-out diagnostics

| Omitted feature | Ablated minus full MSE | HAC p-value | Holm-adjusted p-value |
|---|---:|---:|---:|
| `ABNB_MOM_12_2` | -0.00116731 | 0.345759 | 1.000000 |
| `ABNB_RET_21D` | 0.00006043 | 0.217643 | 1.000000 |
| `ABNB_RSI_14` | 0.00004981 | 0.144269 | 1.000000 |
| `ABNB_EMA_GAP_20` | -0.00089451 | 0.410501 | 1.000000 |
| `ABNB_MACD_HIST_NORM` | -0.00002107 | 0.139638 | 1.000000 |
| `SPY_RET_5D` | 0.00008265 | 0.317258 | 1.000000 |
| `PEER_RET_5D` | 0.00003428 | 0.588066 | 1.000000 |
| `SPY_RVOL_20D` | -0.00225385 | 0.141838 | 1.000000 |

Full block-length sensitivities and per-origin forecasts are in the JSON
and CSV artifacts.

## Interpretation boundary

Interpret the statistical result together with the 12-origin sample size,
overlapping three-month outcomes, and the unresolved source-provenance
limitations. No feature, model, threshold, or preprocessing redesign follows
from this final-test result.
