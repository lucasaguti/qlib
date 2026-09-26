# Development-Only Expanding-Window Forecast Evaluation

> This is a development-period pseudo-out-of-sample diagnostic, not the frozen
> confirmatory final-test result. Source rights and point-in-time adjustment
> evidence remain unresolved, and no final-test row was read.

Scored origins: **8** (2024-10-31 through 2025-05-30).

## Primary metrics

| Model | MAE [95% CI] | RMSE [95% CI] | R^2 vs zero [95% CI] | R^2 vs expanding mean [95% CI] | Directional accuracy [95% CI] | Class-frequency baseline |
|---|---:|---:|---:|---:|---:|---:|
| Zero return | 0.060673 [0.034931, 0.084544] | 0.069458 [0.044425, 0.087608] | 0.000000 [0.000000, 0.000000] | 0.020855 [-0.036898, 0.068300] | 0.000000 [0.000000, 0.000000] | 0.500 |
| Matured expanding average | 0.061358 [0.035090, 0.086284] | 0.070193 [0.043817, 0.089074] | -0.021299 [-0.073307, 0.035585] | 0.000000 [0.000000, 0.000000] | 0.500000 [0.125000, 0.875000] | 0.500 |
| Eight-feature Ridge | 0.061615 [0.035169, 0.086416] | 0.070715 [0.045645, 0.088341] | -0.036542 [-0.084035, 0.009475] | -0.014926 [-0.117686, 0.075417] | 0.375000 [0.125000, 0.625000] | 0.500 |

## Dependence-aware primary comparison

The paired mean squared-error difference is Ridge minus the matured
expanding-average benchmark, so negative values favor Ridge.

- Estimate: 0.00007354
- Circular three-month block-bootstrap 95% interval: [-0.00039409, 0.00054154]
- Newey-West HAC(2) two-sided p-value: 0.783437

## Temporal stability

Temporal stability uses two fixed chronological halves:

| Model | First-half MAE | Second-half MAE | First-half RMSE | Second-half RMSE |
|---|---:|---:|---:|---:|
| Zero return | 0.052148 | 0.069198 | 0.059948 | 0.077814 |
| Matured expanding average | 0.050622 | 0.072095 | 0.058759 | 0.080010 |
| Eight-feature Ridge | 0.052622 | 0.070609 | 0.061930 | 0.078523 |

## Eligibility accounting

- `INSUFFICIENT_RIDGE_HISTORY`: 26
- `INCOMPLETE_FEATURES`: 12
- `INSUFFICIENT_INNER_VALIDATION`: 8
- `ELIGIBLE`: 8

## Leave-one-feature-out diagnostics

| Omitted feature | Ablated minus full MSE | HAC p-value | Holm-adjusted p-value |
|---|---:|---:|---:|
| `ABNB_MOM_12_2` | 0.00000134 | 0.452014 | 1.000000 |
| `ABNB_RET_21D` | 0.00000427 | 0.387939 | 1.000000 |
| `ABNB_RSI_14` | 0.00000240 | 0.702096 | 1.000000 |
| `ABNB_EMA_GAP_20` | 0.00000112 | 0.724197 | 1.000000 |
| `ABNB_MACD_HIST_NORM` | 0.00000156 | 0.176593 | 1.000000 |
| `SPY_RET_5D` | 0.00000777 | 0.200067 | 1.000000 |
| `PEER_RET_5D` | 0.00000072 | 0.821736 | 1.000000 |
| `SPY_RVOL_20D` | -0.00103555 | 0.055546 | 0.444364 |

Full block-length sensitivities and per-origin forecasts are in the JSON
and CSV artifacts.

## Interpretation boundary

These results can validate the implementation and show development-period
behavior. They cannot support the confirmatory research claim. The isolated
12-origin final test remains unopened until the data blockers are resolved.
