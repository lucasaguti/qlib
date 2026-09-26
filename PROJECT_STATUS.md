# ABNB Research Status

> **Dynamic document.** Update this file after every material implementation, validation, experiment, or change in blockers. Keep it factual and current; do not rewrite the charter in `PROJECT_INNATE.md`.

**Last updated:** 2026-09-25  
**Repository baseline:** Qlib checkout at `d19677c5`

**Current phase:** evaluation protocol frozen; development-only feature artifacts and temporal forecast contract complete; target values not constructed
**Final test status:** frozen as the 12 origins from 2025-06-30 through 2026-05-29; no post-freeze access has occurred

## Current state

- The upstream Qlib research infrastructure is present.
- The project charter and agent operating instructions are established at repository root.
- ABNB, BKNG, EXPE, and SPY current/archived CSVs, both source manifests, and the initial indicator PDF are registered under `research/abnb/data/raw/` and excluded from Git.
- Reproducible validation is implemented in `research/abnb/pipeline/validate_inputs.py`; results are in `research/abnb/validation/`.
- Byte, archive, schema, date, and value integrity passed. The 2026-09-22 gap was investigated: it was a regular XNYS session and later Yahoo views contain ABNB and EXPE observations, so the registered extraction omitted real source rows. Because the later view is not the registered point-in-time version, both statuses remain `MISSING_SOURCE`.
- The in-memory canonical daily panel is implemented in `research/abnb/pipeline/panel.py`. It verifies registered hashes, uses the full 1,452-session XNYS study calendar, retains source lineage metadata, masks unusable modeling prices, and preserves the two 2026-09-22 source gaps as `MISSING_SOURCE`.
- The eight locked daily feature functions are implemented in `research/abnb/pipeline/features.py`. Each returns a nullable value plus status, enforces its exact consecutive-session history, and resets/reseeds RSI, EMA, and MACD after unusable observations. SPY and peer functions can enforce an explicit anchor date for cross-security calls.
- Evaluation protocol `EVAL-PROTOCOL-001` version 1 is frozen in `research/abnb/EVALUATION_PROTOCOL.md` and `research/abnb/config/evaluation_protocol.json`. Development ends at the 2025-05 origin; the 12 origins from 2025-06 through 2026-05 are the isolated final test; origins from 2026-06 onward are quarantined. The protocol fixes complete-case feature eligibility, 24 eligible matured training observations, the Ridge alpha grid and fold-local scaling, dependence-aware uncertainty, eight leave-one-out ablations, and Holm familywise control. It was selected without constructing or reading targets or feature/target relationships.
- Daily feature orchestration is implemented in `research/abnb/pipeline/daily_features.py`. It evaluates all eight features at every canonical session and writes the untracked development artifact `research/abnb/data/interim/daily_features.parquet` with feature-level statuses and repeated calendar, source, parent-hash, build-time, and Git provenance.
- Monthly sampling is implemented in `research/abnb/pipeline/monthly_features.py` as strict row selection from the daily artifact. It selects the actual final XNYS session only for completed calendar months, copies all feature values and statuses without recalculation, and writes the untracked `research/abnb/data/interim/monthly_features.parquet` artifact. Each origin now carries its reference session, actual UTC close/information cutoff, issuance at the next XNYS session open, final-session maturity in the calendar month exactly three months later, and label-availability close.
- A current-provider corporate-action recheck matches every registered dividend and split row, but does not establish historical adjustment-state versions or availability. Per-observation point-in-time price and adjustment evidence remains blocked.
- Extraction rights are blocked absent express permission; retention, ML-processing, and backup rights remain unknown. The supplied inputs remain `DEVELOPMENT_ONLY`. The complete review and evidence requirements are in `research/abnb/validation/DATA_LIMITATIONS.md`.
- No persisted processed dataset, frozen split, trained model, or model result exists.

## Immediate next actions

1. Acquire a licensed replacement source that expressly permits extraction, retention, ML processing, and backup and supplies price/adjustment versions plus availability evidence.
2. Ingest any 2026-09-22 recovery as a new immutable source version, validate it, and rebuild/register downstream artifacts; retain `MISSING_SOURCE` until then.
3. Construct status-bearing three-calendar-month adjusted-return labels without admitting values before `label_available_at`.
4. Implement and test `EVAL-PROTOCOL-001`, including split isolation, common eligibility, fold-local scaling/tuning, dependence-aware metrics, and the predefined ablations, without accessing final-test outcomes.

## Blockers and open inputs

| Item | State | Needed resolution |
|---|---|---|
| XNYS 2026-09-22 observations | Investigated; retained missing | Later provider views contain both rows, but they are not the registered vintage; preserve `MISSING_SOURCE` until a licensed, versioned replacement is ingested |
| Point-in-time availability evidence | Blocked | Current action lists match, but historical price and adjustment versions plus both availability timestamps remain absent |
| Automated extraction right | Blocked | Obtain express provider permission or a licensed delivery mechanism |
| Retention, ML-processing, and backup rights | Unknown | Obtain and retain written grants and any deletion/archival conditions before confirmatory use |
| Final test execution | Frozen but not accessed | Implement and verify the protocol on development-only fixtures; resolve data blockers before the single authorized evaluation |

## Latest verification

Data-limitation review on 2026-09-25 America/New_York (online checks completed 2026-09-26 UTC): confirmed 2026-09-22 was an XNYS session; corroborated later ABNB and EXPE observations without modifying or supplementing the registered raw inputs; and matched the current provider's explicit corporate-action lists to all four registered CSVs. Rights review did not establish the required extraction, retention, ML-processing, or backup grants. See `research/abnb/validation/DATA_LIMITATIONS.md` and D010. `.venv\Scripts\python.exe -m pytest research/abnb/tests/test_panel.py -q` passed all 7 tests (4 dependency deprecation warnings); all four registered raw hashes and the two validation-document hashes matched `PROJECT_DATA.md`; `git diff --check` passed. At that verification stage, no final-test period existed and no final-test access had occurred.

Initial validation completed with Python 3.12.10 and XNYS from `exchange-calendars==4.13.2`. All current/archived hashes match; structural and numeric checks passed. Full findings are in `research/abnb/validation/DATA_VALIDATION.md` and `data_validation.json`.

Canonical-panel verification on 2026-09-25: `python -m pytest research/abnb/tests/test_panel.py -q` passed 7 tests. The default panel contains 5,808 rows (1,452 XNYS sessions x 4 securities): 5,806 `VALID`, 2 `MISSING_SOURCE`, and no invalid prices. A fresh input-validation run reconfirmed byte integrity; no derived panel snapshot was persisted.

Daily-feature verification on 2026-09-25 with Python 3.12.10: `python -m pytest research/abnb/tests/test_features.py -q` passed 50 tests, and `python -m pytest research/abnb/tests -q` passed all 57 ABNB tests. The feature suite covers every pre-boundary prefix, exact first-valid boundaries, hand-calculated formulas, XNYS position offsets, source-status failures, recursive reseeding, exact market/peer anchors, input immutability, and the development-data 2026-09-22 ABNB/EXPE gap. Black was not available in the project environment; `git diff --check` was used for whitespace validation. No feature dataset was persisted and no final-test access occurred.

Daily-feature artifact verification on 2026-09-25 with Python 3.12.10 and PyArrow 23.0.1: `python -m pytest research/abnb/tests -q` passed all 62 ABNB tests. The new tests cover complete feature/status schema, value/status null consistency, warm-up and real-gap propagation, lineage fields, rejected incomplete panels, and an actual Parquet round trip. `daily_features.parquet` contains 1,452 XNYS session rows and has SHA-256 `ba147b9470e5c267e2e0ff2fac8850f5e0554009adfc1715b5042fc105f449b6`. It is development-only and ignored by Git. Black remains unavailable in the project virtual environment; `git diff --check` passed. At that verification stage, no final-test period existed and no final-test access had occurred.

Monthly-sampling verification on 2026-09-25 with Python 3.12.10: `python -m pytest research/abnb/tests -q` passed all 67 ABNB tests. The monthly tests cover exact and holiday-shortened XNYS month-ends, exclusion of the incomplete September 2026 month, rejection of incomplete daily calendars, exact feature/status row equality, sentinel-based proof that recursive indicators and volatility are not recalculated, parent hashing, and a Parquet round trip. `monthly_features.parquet` contains 69 rows from 2020-12 through 2026-08 and has SHA-256 `31e959e3c1ee4ee861697d369019958169ffc834ce2069e86cac918ff655fee4`. It is development-only and ignored by Git. At that verification stage, no final-test period existed and no final-test access had occurred.

Temporal-contract verification on 2026-09-25 with Python 3.12.10: `.venv\Scripts\python.exe -m pytest research/abnb/tests -q` passed all 73 ABNB tests. The added tests cover weekend/holiday and year-boundary issuance, actual early closes, exact three-calendar-month final-session maturity, maturity months beyond current data coverage, explicit rejection of a 63-session approximation, and invariance of an origin's feature row to all later price mutations. The schema-v2 `monthly_features.parquet` retains 69 origins and has SHA-256 `7c774c32f4fd9a0582968bbef7a16cdacf796c583a301613df4e2b2aff4c7581`. Black is not installed in the project environment; `git diff --check` passed. At that verification stage, no final-test period existed and no final-test access had occurred.

Evaluation-protocol freeze on 2026-09-25: `EVAL-PROTOCOL-001` version 1 selects the 12 reference sessions from 2025-06-30 through 2026-05-29 using CAL-XNYS-001 and registered coverage constraints. PowerShell `ConvertFrom-Json` parsed the machine-readable config successfully. No target values were constructed or read and no feature/target relationships or exploratory results were examined. Documentation/config review and `git diff --check` are the applicable verification; model implementation remains pending.
