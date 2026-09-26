# ABNB Data and Artifact Registry

> **Dynamic document.** Register every supplied dataset, calendar, PDF specification, processed snapshot, and final result used by the study. Never edit source data in place. Add a new version and checksum when content changes.

## Intake rules

1. Preserve the exact supplied bytes in an immutable raw location.
2. Compute and record a SHA-256 checksum before inspection or transformation.
3. Record provenance, license/usage constraints, retrieval details, schema, timezone, and availability semantics; write `unknown` rather than infer missing facts.
4. Give derived artifacts their own versions, parent checksums, build configuration, code revision, and output checksum.
5. Keep restricted or large data out of Git. Commit metadata/manifests only when permitted.
6. Treat a file's modification time and observation date as insufficient evidence of historical availability.

## Source datasets

| ID | Path | Role/instruments | Provider/version | Coverage | Adjustment and availability semantics | SHA-256 | Rights | State |
|---|---|---|---|---|---|---|---|---|
| SRC-ABNB-001 | `research/abnb/data/raw/Dataset1/ABNB_daily.csv` | Forecast asset: ABNB | Yahoo Finance via yfinance; package version unknown | 2020-12-10 to 2026-09-23; 1,451 rows | `auto_adjust=false`; Close, Adj Close, dividends, and splits retained; PIT assertion unconfirmed | `76a120fb7de4489af1d81735ebe9797f3a335abfd6392a1aca9c24f1fbe3603f` | See rights matrix below | Development only; 2026-09-22 remains `MISSING_SOURCE`; later provider view documented in LIM-001 |
| SRC-BKNG-001 | `research/abnb/data/raw/Dataset2/BKNG_daily.csv` | Peer: BKNG | Yahoo Finance via yfinance; package version unknown | 2019-01-02 to 2026-09-23; 1,942 rows | Same; 11 dividends and one 25:1 split recorded | `b2ca085eb6104e2338cb99733eb5c8c19953f6259a336d7f21b6810ceac3cf7b` | See rights matrix below | Development only; structural validation passed |
| SRC-EXPE-001 | `research/abnb/data/raw/Dataset2/EXPE_daily.csv` | Peer: EXPE | Yahoo Finance via yfinance; package version unknown | 2019-01-02 to 2026-09-23; 1,941 rows | Same; 12 dividends and no splits recorded | `a74c26ee209d4aaad1708751942cb99ee83098a5a487a54a73ee76aed9402a68` | See rights matrix below | Development only; 2026-09-22 remains `MISSING_SOURCE`; later provider view documented in LIM-001 |
| SRC-SPY-001 | `research/abnb/data/raw/Dataset2/SPY_daily.csv` | Broad market: SPY | Yahoo Finance via yfinance; package version unknown | 2019-01-02 to 2026-09-23; 1,942 rows | Same; 31 dividends and no splits recorded | `9e37898aeea8730570cde4ca5403ddfd7384508c37bf63ff7ace2bb9e8d93069` | See rights matrix below | Development only; structural validation passed |

Each registered current CSV has a byte-identical immutable copy under its dataset's `versions/` directory.

### Usage-rights assessment

No project-specific provider contract, subscription entitlement, or express
permission was supplied. Public Yahoo/yfinance materials do not establish the
rights required by the research charter. The operative status is therefore:

| Right | Status | Confirmatory requirement |
|---|---|---|
| Automated extraction | `BLOCKED` | Express permission or licensed delivery covering the extraction method |
| Retention | `UNKNOWN` | Written permission for immutable source and derived-data retention |
| ML processing | `UNKNOWN` | Written permission for feature engineering, model fitting, evaluation, and derived artifacts |
| Backup | `UNKNOWN` | Written permission for archival/redundant copies and documented deletion duties |

See LIM-001 for the reviewed terms and evidence standard. Accessibility,
academic intent, and the `yfinance` software license are not treated as data
rights.

### Registered manifests

| Dataset | Path | Extracted at (UTC) | SHA-256 | Validation |
|---|---|---|---|---|
| Dataset1 | `research/abnb/data/raw/Dataset1/manifest.json` | 2026-09-24T20:08:30.811448+00:00 | `a302da5404d2187ea9563e9aaac33d54c97e73cb7979d3554df764bad4e5f3bc` | File hash, schema, row count, and coverage match |
| Dataset2 | `research/abnb/data/raw/Dataset2/manifest.json` | 2026-09-24T20:14:15.981190+00:00 | `b8461b9fbec7bec464d804cba803b4f7ca65eac4cf373341899085fe9d5e37e0` | All three file hashes, schemas, row counts, and coverage match |

## Calendars and corporate actions

| ID | Path | Identity/version | Coverage | Availability evidence | SHA-256 | State |
|---|---|---|---|---|---|---|
| CAL-XNYS-001 | Python environment dependency | XNYS via `exchange-calendars==4.13.2` | All registered source ranges | Library-generated schedule; source manifests do not identify their calendar | N/A | Validation calendar accepted; source-calendar provenance pending |

Corporate actions are embedded in the registered CSVs. Their effective dates
and values were structurally validated. A current-provider recheck on
2026-09-26 UTC matched all registered explicit action rows, as documented in
LIM-001, but historical versions and availability evidence remain unverified.

## Indicator specifications and PDFs

| ID | Path | Purpose | Version/date | SHA-256 | Reconciliation state |
|---|---|---|---|---|---|
| SPEC-IND-001 | `research/abnb/data/raw/specifications/ABNB_predictive_indicators1.pdf` | Initial eight feature definitions and data rules | Revision 2; 2026-09-24 | `c2f028079e15d4afa4b0ba35a2595b6229d1c35533b4c9a0b0fcdecaa0fef6dd` | Reviewed and reconciled in D006; implemented in `pipeline/features.py`; charter controls forecast origin, issuance, target, and unavailable-by-cutoff status |

Any PDF interpretation that changes or clarifies a formula, seed, null behavior, timing rule, or parameter must be recorded in `PROJECT_DECISIONS.md`. A conflict with `PROJECT_INNATE.md` requires user resolution; a PDF does not silently override the charter.

## Derived datasets and experimental snapshots

| ID | Path | Parents | Build config | Code revision | Coverage/split | SHA-256 | State |
|---|---|---|---|---|---|---|---|
| VAL-001 | `research/abnb/validation/data_validation.json` | SRC-ABNB-001, SRC-BKNG-001, SRC-EXPE-001, SRC-SPY-001 | `pipeline/validate_inputs.py`; `exchange-calendars==4.13.2` | Working tree at Qlib `be725493` | Full registered source coverage; no modeling split | `b1435e3c31161c7ee67a032956dfe757de6ed03285c06b01b13e416ac28168b8` | Completed; development-only readiness |
| VAL-002 | `research/abnb/validation/DATA_VALIDATION.md` | VAL-001; LIM-001 follow-up link | Human-readable validation summary | Working tree at Qlib `d19677c` | Full registered source coverage; no modeling split | `9ff7a0e5e6b25710aba87ca2937c2c62a3a498f3f52249f5a4781590147814af` | Completed |
| LIM-001 | `research/abnb/validation/DATA_LIMITATIONS.md` | SRC-ABNB-001, SRC-BKNG-001, SRC-EXPE-001, SRC-SPY-001; CAL-XNYS-001; current online corroboration | Manual source-gap, PIT/corporate-action, and rights review; no online response retained as research data | Git `d19677c59a8d229f53681af26654e28cde74fe64`; documentation working tree | Full registered source coverage; no modeling split or final-test access | `d7ba2ceb2ef8f94d68ac63bdd421bab82f78d02259be4fb4f4f47df96066f0e4` | Completed review; gaps and confirmatory blockers explicitly retained |
| FEAT-001 | `research/abnb/data/interim/daily_features.parquet` | SRC-ABNB-001, SRC-BKNG-001, SRC-EXPE-001, SRC-SPY-001; Dataset1/2 manifests; CAL-XNYS-001 | `pipeline/daily_features.py` schema v1; `exchange-calendars==4.13.2`; `pyarrow==23.0.1` | Git `0ffc0b841ef6f88ed4f9d779d36f8df56c857378`; dirty worktree recorded in artifact | 2020-12-10 through 2026-09-23; 1,452 daily sessions; no modeling split | `ba147b9470e5c267e2e0ff2fac8850f5e0554009adfc1715b5042fc105f449b6` | Completed; development-only; untracked |
| MONTH-001 | `research/abnb/data/interim/monthly_features.parquet` | FEAT-001 (`ba147b9470e5c267e2e0ff2fac8850f5e0554009adfc1715b5042fc105f449b6`); CAL-XNYS-001 | `pipeline/monthly_features.py` schema v2; final XNYS reference session for each completed calendar month; exact close/cutoff, next-session-open issuance, final-session maturity three calendar months later, and maturity-close label availability; `exchange-calendars==4.13.2`; `pyarrow==23.0.1` | Git `672f54198e1ff4d926dfe3b0ebdfbbe288d9e3ad`; dirty worktree recorded in artifact | 2020-12 through 2026-08; 69 monthly origins; partial 2026-09 excluded; scheduled maturities through 2026-11; no modeling split | `7c774c32f4fd9a0582968bbef7a16cdacf796c583a301613df4e2b2aff4c7581` | Completed; development-only; untracked |

## Frozen protocols

| ID | Path | Purpose/version | Frozen scope | SHA-256 | State |
|---|---|---|---|---|---|
| EVAL-PROTOCOL-001 | `research/abnb/config/evaluation_protocol.json` | Machine-readable evaluation protocol, version 1 | Development origins through 2025-05-30; 12 final-test origins from 2025-06-30 through 2026-05-29; post-test origins from 2026-06 quarantined | `dd74ed2a387cfa9caab496fcfe12cdcda58b8a1bcdf689b009e20da0ec2b154c` | Frozen 2026-09-25 before target construction or feature/target analysis; implementation pending |
| EVAL-PROTOCOL-001-NARRATIVE | `research/abnb/EVALUATION_PROTOCOL.md` | Human-readable evaluation protocol, version 1 | Eligibility, minimum history, Ridge tuning/scaling, dependence-aware inference, ablations, multiplicity, reporting, and isolation | `d39eaf767d96e7b24d921dd112d972d8f801279f2261e48ce73a73b0d6a5b4b2` | Frozen 2026-09-25; explanatory companion to the JSON contract |

## Final-test access log

The final period is frozen as the 12 origins from 2025-06-30 through
2026-05-29. Append every final-test row or outcome-derived access after the freeze,
including failed or diagnostic access. Selecting the period from calendar and
coverage constraints did not read targets and is not an access event.

| Timestamp (UTC) | Actor | Purpose | Artifact/query | Authorization | Outcome |
|---|---|---|---|---|---|
| — | — | — | — | — | no access |
