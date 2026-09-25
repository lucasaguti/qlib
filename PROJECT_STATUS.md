# ABNB Research Status

> **Dynamic document.** Update this file after every material implementation, validation, experiment, or change in blockers. Keep it factual and current; do not rewrite the charter in `PROJECT_INNATE.md`.

**Last updated:** 2026-09-25  
**Repository baseline:** Qlib checkout at `be725493`  
**Current phase:** source-data intake and validation
**Final test status:** not selected; no access has occurred

## Current state

- The upstream Qlib research infrastructure is present.
- The project charter and agent operating instructions are established at repository root.
- ABNB, BKNG, EXPE, and SPY current/archived CSVs, both source manifests, and the initial indicator PDF are registered under `research/abnb/data/raw/` and excluded from Git.
- Reproducible validation is implemented in `research/abnb/pipeline/validate_inputs.py`; results are in `research/abnb/validation/`.
- Byte, archive, schema, date, and value integrity passed. ABNB and EXPE are missing the XNYS session 2026-09-22.
- The supplied inputs are classified `DEVELOPMENT_ONLY`: point-in-time evidence is insufficient and usage rights are unknown.
- No processed dataset, frozen split, trained model, or model result exists.

## Immediate next actions

1. Investigate or replace the missing ABNB and EXPE observations for 2026-09-22 without filling them silently.
2. Obtain supporting point-in-time availability/corporate-action evidence and document data usage rights.
3. Decide whether to authorize a clearly labeled development-only feature pipeline while confirmatory use remains blocked.
4. After those decisions, build the canonical XNYS-indexed daily panel and feature-status layer.

## Blockers and open inputs

| Item | State | Needed resolution |
|---|---|---|
| XNYS 2026-09-22 observations | Missing | Investigate ABNB and EXPE source absence; preserve `MISSING_SOURCE` meanwhile |
| Point-in-time availability evidence | Blocked | Provide retained price-version and adjustment-state evidence or amend the intended claim |
| Data usage/retention/ML rights | Unknown | Record source terms or user-supplied authorization before confirmatory use |
| Final test period | Unset | Freeze before confirmatory evaluation |

## Latest verification

Initial validation completed with Python 3.12.10 and XNYS from `exchange-calendars==4.13.2`. All current/archived hashes match; structural and numeric checks passed. Full findings are in `research/abnb/validation/DATA_VALIDATION.md` and `data_validation.json`.
