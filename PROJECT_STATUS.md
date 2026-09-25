# ABNB Research Status

> **Dynamic document.** Update this file after every material implementation, validation, experiment, or change in blockers. Keep it factual and current; do not rewrite the charter in `PROJECT_INNATE.md`.

**Last updated:** 2026-09-25  
**Repository baseline:** Qlib checkout at `672f5419`

**Current phase:** development-only daily and monthly feature artifacts complete; target construction not started
**Final test status:** not selected; no access has occurred

## Current state

- The upstream Qlib research infrastructure is present.
- The project charter and agent operating instructions are established at repository root.
- ABNB, BKNG, EXPE, and SPY current/archived CSVs, both source manifests, and the initial indicator PDF are registered under `research/abnb/data/raw/` and excluded from Git.
- Reproducible validation is implemented in `research/abnb/pipeline/validate_inputs.py`; results are in `research/abnb/validation/`.
- Byte, archive, schema, date, and value integrity passed. ABNB and EXPE are missing the XNYS session 2026-09-22.
- The in-memory canonical daily panel is implemented in `research/abnb/pipeline/panel.py`. It verifies registered hashes, uses the full 1,452-session XNYS study calendar, retains source lineage metadata, masks unusable modeling prices, and preserves the two 2026-09-22 source gaps as `MISSING_SOURCE`.
- The eight locked daily feature functions are implemented in `research/abnb/pipeline/features.py`. Each returns a nullable value plus status, enforces its exact consecutive-session history, and resets/reseeds RSI, EMA, and MACD after unusable observations. SPY and peer functions can enforce an explicit anchor date for cross-security calls.
- Daily feature orchestration is implemented in `research/abnb/pipeline/daily_features.py`. It evaluates all eight features at every canonical session and writes the untracked development artifact `research/abnb/data/interim/daily_features.parquet` with feature-level statuses and repeated calendar, source, parent-hash, build-time, and Git provenance.
- Monthly sampling is implemented in `research/abnb/pipeline/monthly_features.py` as strict row selection from the daily artifact. It selects the actual final XNYS session only for completed calendar months, copies all feature values and statuses without recalculation, and writes the untracked `research/abnb/data/interim/monthly_features.parquet` artifact.
- The supplied inputs are classified `DEVELOPMENT_ONLY`: point-in-time evidence is insufficient and usage rights are unknown.
- No persisted processed dataset, frozen split, trained model, or model result exists.

## Immediate next actions

1. Investigate or replace the missing ABNB and EXPE observations for 2026-09-22 without filling them silently.
2. Obtain supporting point-in-time availability/corporate-action evidence and document data usage rights.
3. Define and test forecast issuance and three-calendar-month target maturity orchestration.
4. Freeze the final-test period before any confirmatory evaluation.

## Blockers and open inputs

| Item | State | Needed resolution |
|---|---|---|
| XNYS 2026-09-22 observations | Missing | Investigate ABNB and EXPE source absence; preserve `MISSING_SOURCE` meanwhile |
| Point-in-time availability evidence | Blocked | Provide retained price-version and adjustment-state evidence or amend the intended claim |
| Data usage/retention/ML rights | Unknown | Record source terms or user-supplied authorization before confirmatory use |
| Final test period | Unset | Freeze before confirmatory evaluation |

## Latest verification

Initial validation completed with Python 3.12.10 and XNYS from `exchange-calendars==4.13.2`. All current/archived hashes match; structural and numeric checks passed. Full findings are in `research/abnb/validation/DATA_VALIDATION.md` and `data_validation.json`.

Canonical-panel verification on 2026-09-25: `python -m pytest research/abnb/tests/test_panel.py -q` passed 7 tests. The default panel contains 5,808 rows (1,452 XNYS sessions x 4 securities): 5,806 `VALID`, 2 `MISSING_SOURCE`, and no invalid prices. A fresh input-validation run reconfirmed byte integrity; no derived panel snapshot was persisted.

Daily-feature verification on 2026-09-25 with Python 3.12.10: `python -m pytest research/abnb/tests/test_features.py -q` passed 50 tests, and `python -m pytest research/abnb/tests -q` passed all 57 ABNB tests. The feature suite covers every pre-boundary prefix, exact first-valid boundaries, hand-calculated formulas, XNYS position offsets, source-status failures, recursive reseeding, exact market/peer anchors, input immutability, and the development-data 2026-09-22 ABNB/EXPE gap. Black was not available in the project environment; `git diff --check` was used for whitespace validation. No feature dataset was persisted and no final-test access occurred.

Daily-feature artifact verification on 2026-09-25 with Python 3.12.10 and PyArrow 23.0.1: `python -m pytest research/abnb/tests -q` passed all 62 ABNB tests. The new tests cover complete feature/status schema, value/status null consistency, warm-up and real-gap propagation, lineage fields, rejected incomplete panels, and an actual Parquet round trip. `daily_features.parquet` contains 1,452 XNYS session rows and has SHA-256 `ba147b9470e5c267e2e0ff2fac8850f5e0554009adfc1715b5042fc105f449b6`. It is development-only and ignored by Git. Black remains unavailable in the project virtual environment; `git diff --check` passed. No final-test period exists and no final-test access occurred.

Monthly-sampling verification on 2026-09-25 with Python 3.12.10: `python -m pytest research/abnb/tests -q` passed all 67 ABNB tests. The monthly tests cover exact and holiday-shortened XNYS month-ends, exclusion of the incomplete September 2026 month, rejection of incomplete daily calendars, exact feature/status row equality, sentinel-based proof that recursive indicators and volatility are not recalculated, parent hashing, and a Parquet round trip. `monthly_features.parquet` contains 69 rows from 2020-12 through 2026-08 and has SHA-256 `31e959e3c1ee4ee861697d369019958169ffc834ce2069e86cac918ff655fee4`. It is development-only and ignored by Git. No final-test period exists and no final-test access occurred.
