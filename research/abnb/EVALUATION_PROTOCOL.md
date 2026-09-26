# Frozen Evaluation Protocol

**Protocol:** `EVAL-PROTOCOL-001` version 1  
**Frozen:** 2026-09-25, before constructing targets or examining any
feature/target relationship  
**Machine-readable source:** `config/evaluation_protocol.json`

This protocol implements the validation and inference contract in
`PROJECT_INNATE.md`. It may be corrected only for an implementation error or
an impossibility discovered without using final-test outcomes. Any correction
must create a new version, state the reason, and preserve this version. A
result-driven change is a separately labeled exploratory study and cannot
replace the confirmatory result.

## Frozen periods

- **Development origins:** 2020-12-31 through 2025-05-30, inclusive. Warm-up,
  feature status, target status, maturity, and minimum-history rules determine
  which of these origins are actually eligible.
- **Final-test origins:** the 12 monthly origins from 2025-06 through 2026-05,
  inclusive. Their exact reference sessions are frozen in the JSON config.
  This is the latest consecutive 12-origin block whose three-calendar-month
  maturities finish within the registered source coverage. The period was
  selected from calendar and coverage constraints, not outcomes.
- **Post-test quarantine:** origins from 2026-06 onward belong to neither
  development nor the frozen test. They cannot be used to enlarge or revise
  the confirmatory test.

The final-test feature values, targets, feature/target relationships, metrics,
predictions, and model choices must remain unread during development. Constructing the
already-existing status-bearing feature artifact before the split was chosen
does not constitute final-test access because no test was then defined and its
final-period values were not inspected. From this freeze forward, every read or
attempted read of final-test rows or outcome-derived artifacts must be appended
to the final-test access log in `PROJECT_DATA.md`.

## Eligibility and training history

An origin is eligible only when its target is valid and finite and all eight
locked features are finite with status `VALID`. There is no imputation,
missing-indicator model, shortened window, peer substitution, or complete-case
rule chosen per model. The zero-return benchmark, expanding historical mean,
full Ridge model, and ablations are scored on the same frozen common set of
eligible final-test origins.

At an issuance time, all admitted training labels must satisfy
`label_available_at <= issued_at_utc`. Ridge training rows must additionally
have all eight finite `VALID` features and requires at least 24 such monthly
observations. The expanding historical-average benchmark uses every valid,
finite, matured target available at issuance regardless of feature status; its
final-test scoring rows remain the common complete-case set. If Ridge's minimum
is not met, it emits no forecast; the origin is not moved and the threshold is
not relaxed. Training is expanding-window only.

## Ridge tuning and fold-local preprocessing

The alpha grid is
`[1e-4, 1e-3, 1e-2, 1e-1, 1, 10, 100, 1e3, 1e4]`. At every outer forecast
origin, select alpha using expanding, one-origin-ahead inner walk-forward mean
squared error. Every inner fit must itself have at least 24 eligible matured
observations, and alpha selection requires at least six inner validation
predictions. If two scores differ by no more than `1e-12`, choose the larger
alpha.

For every inner and outer fit, estimate each feature's mean and population
standard deviation (`ddof=0`) from that fit's training fold alone, then apply
that fitted transform to its validation or forecast row. A zero-variance
training feature uses scale 1. The intercept is fitted and unpenalized. No
scaler, imputer, feature selector, or other learned transform may be fitted on
development plus final-test data.

## Dependence-aware uncertainty

The primary 95% intervals use 10,000 circular moving-block bootstrap draws of
the paired monthly final-test rows, block length three months, and seed
`20260925`. Resample the complete paired row so forecasts, targets, hits, and
losses remain aligned. Recompute each reported statistic within each draw;
ratio statistics such as out-of-sample R-squared are not assembled from
separately bootstrapped components. Report percentile intervals. Block lengths
2, 4, and 6 are predefined dependence sensitivities and cannot replace the
three-month primary interval based on favorability.

Two-sided hypothesis-test p-values use an intercept-only Newey-West HAC test
of the paired monthly statistic with maximum lag 2, reflecting the mechanical
overlap of three-month targets. Report estimates and intervals even when a
p-value is not significant. With only 12 scheduled test origins, conclusions
must explicitly describe the low precision and may not treat nominal counts as
independent.

## Predictor ablations and multiplicity

There are no individual univariate feature/target significance tests in the
confirmatory protocol. The only predefined predictor-level analyses are eight
leave-one-feature-out Ridge ablations, one for each locked predictor. Each
ablation is retuned independently within every outer training fold using the
same alpha grid, history threshold, scaling, and inner-validation rules as the
full model.

For each ablation, calculate paired ablated-model squared error minus full-model
squared error on the common eligible final-test origins, so a positive estimate
favors retaining the feature. The eight two-sided HAC p-values form one family
and are adjusted with Holm's step-down
procedure at familywise alpha 0.05. Report all raw and adjusted p-values and
effect estimates. These ablations are secondary and exploratory: no ablation
can redefine the locked full model or rescue a negative primary comparison.
No additional feature subsets, signs, lags, windows, transformations, or
post-hoc subperiods are confirmatory.

## Reporting and isolation

The primary model comparison is the paired squared-error loss of full Ridge
against the expanding historical-average benchmark. Also report all chartered
metrics for Ridge and both benchmarks: MAE, RMSE, benchmark-relative
out-of-sample R-squared, directional accuracy with its class-frequency
baseline, temporal stability, and dependence-aware uncertainty. Ridge versus
zero return and the eight ablations are secondary. Metric disagreement must be
shown rather than resolved after seeing the test.

After development code, tests, and an auditable snapshot are complete, the
authorized final evaluation is a single pass. Its access, including failed
runs, must be logged. Final-test information cannot be used to alter features,
eligibility, alpha values, scaling, minimum history, uncertainty, multiplicity,
or any other protocol choice.
