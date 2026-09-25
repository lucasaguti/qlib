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
| SRC-ABNB-001 | `research/abnb/data/raw/Dataset1/ABNB_daily.csv` | Forecast asset: ABNB | Yahoo Finance via yfinance; package version unknown | 2020-12-10 to 2026-09-23; 1,451 rows | `auto_adjust=false`; Close, Adj Close, dividends, and splits retained; PIT assertion unconfirmed | `76a120fb7de4489af1d81735ebe9797f3a335abfd6392a1aca9c24f1fbe3603f` | Unknown | Development only; missing XNYS 2026-09-22 |
| SRC-BKNG-001 | `research/abnb/data/raw/Dataset2/BKNG_daily.csv` | Peer: BKNG | Yahoo Finance via yfinance; package version unknown | 2019-01-02 to 2026-09-23; 1,942 rows | Same; 11 dividends and one 25:1 split recorded | `b2ca085eb6104e2338cb99733eb5c8c19953f6259a336d7f21b6810ceac3cf7b` | Unknown | Development only; structural validation passed |
| SRC-EXPE-001 | `research/abnb/data/raw/Dataset2/EXPE_daily.csv` | Peer: EXPE | Yahoo Finance via yfinance; package version unknown | 2019-01-02 to 2026-09-23; 1,941 rows | Same; 12 dividends and no splits recorded | `a74c26ee209d4aaad1708751942cb99ee83098a5a487a54a73ee76aed9402a68` | Unknown | Development only; missing XNYS 2026-09-22 |
| SRC-SPY-001 | `research/abnb/data/raw/Dataset2/SPY_daily.csv` | Broad market: SPY | Yahoo Finance via yfinance; package version unknown | 2019-01-02 to 2026-09-23; 1,942 rows | Same; 31 dividends and no splits recorded | `9e37898aeea8730570cde4ca5403ddfd7384508c37bf63ff7ace2bb9e8d93069` | Unknown | Development only; structural validation passed |

Each registered current CSV has a byte-identical immutable copy under its dataset's `versions/` directory.

### Registered manifests

| Dataset | Path | Extracted at (UTC) | SHA-256 | Validation |
|---|---|---|---|---|
| Dataset1 | `research/abnb/data/raw/Dataset1/manifest.json` | 2026-09-24T20:08:30.811448+00:00 | `a302da5404d2187ea9563e9aaac33d54c97e73cb7979d3554df764bad4e5f3bc` | File hash, schema, row count, and coverage match |
| Dataset2 | `research/abnb/data/raw/Dataset2/manifest.json` | 2026-09-24T20:14:15.981190+00:00 | `b8461b9fbec7bec464d804cba803b4f7ca65eac4cf373341899085fe9d5e37e0` | All three file hashes, schemas, row counts, and coverage match |

## Calendars and corporate actions

| ID | Path | Identity/version | Coverage | Availability evidence | SHA-256 | State |
|---|---|---|---|---|---|---|
| CAL-XNYS-001 | Python environment dependency | XNYS via `exchange-calendars==4.13.2` | All registered source ranges | Library-generated schedule; source manifests do not identify their calendar | N/A | Validation calendar accepted; source-calendar provenance pending |

Corporate actions are embedded in the registered CSVs. Their effective dates and values were structurally validated, but historical versions and availability evidence remain unverified.

## Indicator specifications and PDFs

| ID | Path | Purpose | Version/date | SHA-256 | Reconciliation state |
|---|---|---|---|---|---|
| SPEC-IND-001 | `research/abnb/data/raw/specifications/ABNB_predictive_indicators1.pdf` | Initial eight feature definitions and data rules | Revision 2; 2026-09-24 | `c2f028079e15d4afa4b0ba35a2595b6229d1c35533b4c9a0b0fcdecaa0fef6dd` | Reviewed and reconciled in D006; implemented in `pipeline/features.py`; charter controls forecast origin, issuance, target, and unavailable-by-cutoff status |

Any PDF interpretation that changes or clarifies a formula, seed, null behavior, timing rule, or parameter must be recorded in `PROJECT_DECISIONS.md`. A conflict with `PROJECT_INNATE.md` requires user resolution; a PDF does not silently override the charter.

## Derived datasets and experimental snapshots

| ID | Path | Parents | Build config | Code revision | Coverage/split | SHA-256 | State |
|---|---|---|---|---|---|---|---|
| VAL-001 | `research/abnb/validation/data_validation.json` | SRC-ABNB-001, SRC-BKNG-001, SRC-EXPE-001, SRC-SPY-001 | `pipeline/validate_inputs.py`; `exchange-calendars==4.13.2` | Working tree at Qlib `be725493` | Full registered source coverage; no modeling split | `b1435e3c31161c7ee67a032956dfe757de6ed03285c06b01b13e416ac28168b8` | Completed; development-only readiness |
| VAL-002 | `research/abnb/validation/DATA_VALIDATION.md` | VAL-001 | Human-readable validation summary | Working tree at Qlib `be725493` | Full registered source coverage; no modeling split | `9dd3bd1d2317491d06078f9d36bb5548b74e0b49b2115dce7ba02420eed5f896` | Completed |
| FEAT-001 | `research/abnb/data/interim/daily_features.parquet` | SRC-ABNB-001, SRC-BKNG-001, SRC-EXPE-001, SRC-SPY-001; Dataset1/2 manifests; CAL-XNYS-001 | `pipeline/daily_features.py` schema v1; `exchange-calendars==4.13.2`; `pyarrow==23.0.1` | Git `0ffc0b841ef6f88ed4f9d779d36f8df56c857378`; dirty worktree recorded in artifact | 2020-12-10 through 2026-09-23; 1,452 daily sessions; no modeling split | `ba147b9470e5c267e2e0ff2fac8850f5e0554009adfc1715b5042fc105f449b6` | Completed; development-only; untracked |
| MONTH-001 | `research/abnb/data/interim/monthly_features.parquet` | FEAT-001 (`ba147b9470e5c267e2e0ff2fac8850f5e0554009adfc1715b5042fc105f449b6`); CAL-XNYS-001 | `pipeline/monthly_features.py` schema v1; final XNYS session of each completed calendar month; `exchange-calendars==4.13.2`; `pyarrow==23.0.1` | Git `672f54198e1ff4d926dfe3b0ebdfbbe288d9e3ad`; dirty worktree recorded in artifact | 2020-12 through 2026-08; 69 monthly rows; partial 2026-09 excluded; no modeling split | `31e959e3c1ee4ee861697d369019958169ffc834ce2069e86cac918ff655fee4` | Completed; development-only; untracked |

## Final-test access log

The final period is not yet selected. Once frozen, append every access, including failed or diagnostic access.

| Timestamp (UTC) | Actor | Purpose | Artifact/query | Authorization | Outcome |
|---|---|---|---|---|---|
| — | — | — | — | — | no access |
