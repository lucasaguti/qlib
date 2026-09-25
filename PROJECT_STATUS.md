# ABNB Research Status

> **Dynamic document.** Update this file after every material implementation, validation, experiment, or change in blockers. Keep it factual and current; do not rewrite the charter in `PROJECT_INNATE.md`.

**Last updated:** 2026-09-25  
**Repository baseline:** Qlib checkout at `be725493`  
**Current phase:** development-only canonical panel and daily feature pipeline
**Final test status:** not selected; no access has occurred

## Current state

- The upstream Qlib research infrastructure is present.
- The project charter and agent operating instructions are established at repository root.
- ABNB, BKNG, EXPE, and SPY current/archived CSVs, both source manifests, and the initial indicator PDF are registered under `research/abnb/data/raw/` and excluded from Git.
- Reproducible validation is implemented in `research/abnb/pipeline/validate_inputs.py`; results are in `research/abnb/validation/`.
- Byte, archive, schema, date, and value integrity passed. ABNB and EXPE are missing the XNYS session 2026-09-22.
- The in-memory canonical daily panel is implemented in `research/abnb/pipeline/panel.py`. It verifies registered hashes, uses the full 1,452-session XNYS study calendar, retains source lineage metadata, masks unusable modeling prices, and preserves the two 2026-09-22 source gaps as `MISSING_SOURCE`.
- The eight locked daily feature functions are implemented in `research/abnb/pipeline/features.py`. Each returns a nullable value plus status, enforces its exact consecutive-session history, and resets/reseeds RSI, EMA, and MACD after unusable observations.
- The supplied inputs are classified `DEVELOPMENT_ONLY`: point-in-time evidence is insufficient and usage rights are unknown.
- No persisted processed dataset, frozen split, trained model, or model result exists.

## Immediate next actions

1. Add daily-panel orchestration that evaluates the eight tested feature functions for each session and preserves their indicator-specific statuses.
2. Investigate or replace the missing ABNB and EXPE observations for 2026-09-22 without filling them silently.
3. Obtain supporting point-in-time availability/corporate-action evidence and document data usage rights.
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

Daily-feature verification on 2026-09-25 with Python 3.12.10: `python -m pytest research/abnb/tests/test_features.py -q` passed 24 tests, and `python -m pytest research/abnb/tests -q` passed all 31 ABNB tests. Black was not available in the project environment; `git diff --check` was used for whitespace validation. No feature dataset was persisted and no final-test access occurred.
