# ABNB Research Decision Log

> **Dynamic document.** Append durable methodological and implementation decisions. Do not erase superseded entries; add a new entry that links to and supersedes the old one. Planned work and transient notes belong in `PROJECT_STATUS.md`.

## Decision format

```text
### DNNN — Short title

- Date: YYYY-MM-DD
- Status: proposed | accepted | superseded
- Scope: data | target | feature | validation | model | evaluation | infrastructure
- Decision: What was chosen.
- Rationale: Why it was chosen without relying on final-test outcomes.
- Consequences: Constraints, migrations, or follow-up work.
- Evidence: Code/config/artifact paths, source documents, and experiment IDs.
- Supersedes: DNNN or none.
```

## Accepted decisions

### D001 — Separate immutable charter from living project state

- Date: 2026-09-25
- Status: accepted
- Scope: infrastructure
- Decision: Treat `PROJECT_INNATE.md` as user-controlled research intent; maintain progress, provenance, and implementation choices in dynamic root documents.
- Rationale: Prevent routine agent edits from silently drifting the confirmatory research question.
- Consequences: Charter changes require explicit user direction. Agents update relevant dynamic documents with material work.
- Evidence: `PROJECT_INNATE.md`, `PROJECT_STATUS.md`, `PROJECT_DATA.md`, `AGENTS.md`.
- Supersedes: none.

### D002 — Extend Qlib through project-scoped components first

- Date: 2026-09-25
- Status: accepted
- Scope: infrastructure
- Decision: Prefer project-specific handlers, processors, models, configs, and tests outside Qlib core; modify core only when a demonstrated framework defect or reusable integration requires it.
- Rationale: Preserve upstream behavior and keep the study auditable as a discrete research layer.
- Consequences: The concrete project directory layout must be chosen when implementation begins and then recorded here.
- Evidence: Existing `qlib.data.dataset`, `qlib.contrib.model.linear.LinearModel`, and `qlib.workflow` extension points.
- Supersedes: none.

### D003 — Keep supplied inputs in an untracked project raw-data layer

- Date: 2026-09-25
- Status: accepted
- Scope: data
- Decision: Preserve supplied current files, archived versions, manifests, and specifications byte-for-byte under `research/abnb/data/raw/`; exclude that directory from Git.
- Rationale: Keep the study self-contained while protecting immutable source material and avoiding accidental publication of potentially restricted data.
- Consequences: Transformations must write to separate interim/processed layers. Source changes require a new version and registry entry.
- Evidence: `.gitignore`, `PROJECT_DATA.md`, and the registered raw paths.
- Supersedes: none.

### D004 — Restrict initial Yahoo/yfinance inputs to development use

- Date: 2026-09-25
- Status: accepted
- Scope: data
- Decision: Classify the registered inputs as `DEVELOPMENT_ONLY` until point-in-time price/adjustment availability evidence and usage rights are documented.
- Rationale: Mechanical validation passed, but the manifests' point-in-time assertions lack retained supporting evidence and do not state usage rights.
- Consequences: Pipeline and contract tests may use the files if clearly labeled development work; confirmatory evaluation and claims remain blocked.
- Evidence: `research/abnb/validation/DATA_VALIDATION.md` and `data_validation.json`.
- Supersedes: none.

### D005 — Represent the canonical daily panel as a complete XNYS product

- Date: 2026-09-25
- Status: accepted
- Scope: data
- Decision: Build an in-memory long-form panel indexed by `(session_date, security)` over every XNYS session from the latest registered first observation through the latest registered last observation. Keep the parsed source adjusted close separately, expose a modeling adjusted close only for `VALID` rows, and classify rows as `VALID`, `MISSING_SOURCE`, `INVALID_PRICE`, or `UNAVAILABLE_BY_CUTOFF`. Missing and invalid source states take precedence over cutoff masking.
- Rationale: A complete calendar product makes source gaps explicit and prevents an intersection, fill, or invalid value from silently changing indicator windows. Separating source and modeling values preserves audit evidence while failing closed downstream.
- Consequences: The default development panel covers 2020-12-10 through 2026-09-23 and retains ABNB and EXPE on 2026-09-22 as missing. Cutoff classification uses XNYS regular-session close only as a development proxy; it does not resolve missing point-in-time adjustment-state evidence. Persisted snapshots require separate registry entries.
- Evidence: `research/abnb/pipeline/panel.py`; `research/abnb/tests/test_panel.py` (7 tests passed on 2026-09-25).
- Supersedes: none.

### D006 — Expose status-bearing daily feature primitives

- Date: 2026-09-25
- Status: accepted
- Scope: feature
- Decision: Implement each locked feature as an independent function over oldest-to-newest daily adjusted closes, returning `FeatureResult(value, status)` for the final supplied session. Use the PDF's simple-average seeds and recursive updates for RSI, EMA, and MACD; reset recursive state after any non-`VALID` observation. Fixed-window functions inspect exactly their trailing required sessions. Exact-index equality is enforced for pandas EXPE/BKNG inputs, and non-pandas peer sequences are required to be pre-aligned. SPY and peer functions accept an optional `anchor_date` and fail closed unless dated inputs end on that exact session. If multiple source failures occur in one required window, apply the canonical source-state precedence `MISSING_SOURCE`, then `INVALID_PRICE`, then `UNAVAILABLE_BY_CUTOFF`.
- Rationale: A small scalar result contract makes every formula and boundary independently testable while preserving the source status needed to distinguish absence, invalidity, cutoff masking, and warm-up. It also keeps daily indicator logic separate from later monthly sampling and model fitting.
- Consequences: Callers must provide complete common-calendar daily rows, preferably with canonical panel statuses. Daily panel orchestration and monthly sampling remain separate follow-up components. Passing only price sequences cannot reconstruct an unavailable-by-cutoff state, so explicit statuses are required to retain it.
- Evidence: `research/abnb/pipeline/features.py`; `research/abnb/tests/test_features.py` (50 focused tests and 57 total ABNB tests passed on 2026-09-25); `research/abnb/data/raw/specifications/ABNB_predictive_indicators1.pdf` revision 2.
- Supersedes: none.

### D007 — Persist a self-describing development daily feature table

- Date: 2026-09-25
- Status: accepted
- Scope: feature
- Decision: Materialize one row per canonical XNYS session with the eight locked nullable feature values and one categorical status per feature. Repeat calendar identity, source versions, parent source and manifest hashes, UTC build time, Git revision, dirty-worktree state, and `DEVELOPMENT_ONLY` readiness as ordinary columns, and also retain the table contract in Parquet metadata. Write atomically to the ignored interim-data layer.
- Rationale: Explicit row-level provenance remains available to readers that do not preserve pandas metadata, while embedded metadata makes the artifact self-describing for pandas-aware consumers. Reusing the canonical panel and tested feature primitives avoids a second implementation of calendar alignment, status precedence, or indicator formulas.
- Consequences: `research/abnb/data/interim/daily_features.parquet` is reproducible but must not be treated as confirmatory-ready while source evidence and rights remain unresolved. Rebuilds create a new timestamp and artifact checksum and must update the data registry when retained or used. Monthly forecast-origin sampling remains a separate downstream step.
- Evidence: `research/abnb/pipeline/daily_features.py`; `research/abnb/tests/test_daily_features.py`; FEAT-001 in `PROJECT_DATA.md` (62 total ABNB tests passed on 2026-09-25).
- Supersedes: none.

### D008 — Sample monthly features only from completed daily month-ends

- Date: 2026-09-25
- Status: accepted
- Scope: feature
- Decision: Create the monthly feature table by selecting the existing daily-feature row on the final XNYS session of each completed calendar month. Exclude a partial terminal month whose actual XNYS month-end is absent. Copy all eight feature values and their statuses unchanged; do not invoke or reproduce any feature calculation during sampling.
- Rationale: The locked indicators are daily-history calculations. Recomputing them on monthly observations would change their definitions, while accepting a partial month would create a forecast origin that violates the month-end contract.
- Consequences: The current development artifact contains 69 origins from December 2020 through August 2026 and excludes partial September 2026. Monthly rebuilds depend on and record the exact daily artifact hash. Target maturity, issuance timing, and eligibility are separate downstream contracts.
- Evidence: `research/abnb/pipeline/monthly_features.py`; `research/abnb/tests/test_monthly_features.py`; MONTH-001 in `PROJECT_DATA.md` (67 total ABNB tests passed on 2026-09-25).
- Supersedes: none.

### D009 — Derive forecast timing from exact XNYS sessions

- Date: 2026-09-25
- Status: accepted
- Scope: target
- Decision: For every completed monthly origin, set `reference_session` to the final XNYS session of the reference month, `reference_close_utc` and `information_cutoff_utc` to that session's official close, and `issued_at_utc` to the following XNYS session's official open. Set `maturity_session` to the final XNYS session in the calendar month exactly three months after the reference month and `label_available_at` to its official close. Derive future maturity timing from the pinned calendar even when source-price coverage has not completed the maturity month; this schedules availability but does not assert that a label value exists.
- Rationale: Direct calendar lookup preserves weekends, holidays, daylight-saving changes, early closes, and year boundaries while enforcing the charter's calendar-month horizon. It prevents a fixed 63-session offset from changing the target date.
- Consequences: Labels may only be admitted at or after `label_available_at`; unavailable or incomplete maturity prices must remain explicitly unavailable. The monthly artifact schema advances to version 2. The duplicated source `session_date` remains for daily-row lineage while `reference_session` gives it its forecast-contract meaning.
- Evidence: `research/abnb/pipeline/monthly_features.py`; `research/abnb/tests/test_monthly_features.py`; `research/abnb/tests/test_daily_features.py`; MONTH-001 in `PROJECT_DATA.md` (73 total ABNB tests passed on 2026-09-25).
- Supersedes: none.

### D010 — Retain the source gaps and confirmatory data blockers

- Date: 2026-09-25
- Status: accepted
- Scope: data
- Decision: Keep ABNB and EXPE on 2026-09-22 as `MISSING_SOURCE` in the registered source versions. Treat later Yahoo observations as diagnostic corroboration only, not as replacements. Continue to classify all four Yahoo/yfinance inputs as `DEVELOPMENT_ONLY` because point-in-time price/adjustment evidence and the required extraction, retention, ML-processing, and backup rights are not established.
- Rationale: The date was an XNYS session and later provider views contain both observations, showing an omission in the registered extraction. Those later views cannot reconstruct the source state at the 2026-09-24 extraction or at historical forecast cutoffs. Current corporate-action agreement does not provide historical version evidence, and public terms do not grant all rights required by the charter.
- Consequences: Do not patch `SRC-ABNB-001` or `SRC-EXPE-001`, fill the session, or promote downstream artifacts to confirmatory use. A licensed replacement must be ingested as a new immutable version with availability, adjustment-state, rights, retrieval, and checksum evidence, followed by complete rebuild and registration.
- Evidence: `research/abnb/validation/DATA_LIMITATIONS.md` (LIM-001); `PROJECT_DATA.md`; XNYS via `exchange-calendars==4.13.2`; diagnostic checks completed 2026-09-26 UTC.
- Supersedes: none.

### D011 — Freeze the development and final-test evaluation protocol

- Date: 2026-09-25
- Status: accepted
- Scope: validation | model | evaluation
- Decision: Freeze `EVAL-PROTOCOL-001` version 1 before target construction or feature/target analysis. Development origins end on 2025-05-30. The final test is the 12 consecutive monthly origins from 2025-06-30 through 2026-05-29; origins from 2026-06 onward are quarantined. Require complete, finite, `VALID` values for all eight features and a valid finite target, with no imputation and a common evaluation set for all models. Ridge uses at least 24 eligible matured observations, expanding one-origin-ahead inner validation, fold-local population-standard-deviation scaling, and the fixed alpha grid `1e-4` through `1e4` in powers of ten. Primary uncertainty is a 10,000-draw circular moving-block bootstrap with a three-month block and seed `20260925`; paired hypothesis tests use Newey-West HAC lag 2. The only predictor-level tests are eight leave-one-feature-out Ridge ablations, treated as one Holm-controlled family at familywise alpha 0.05; no univariate feature/target significance tests are authorized.
- Rationale: The final-test block is the latest consecutive 12-origin block whose three-calendar-month maturities finish within registered coverage. Twelve observations preserve a full annual cycle, while the earlier data remain available for expanding training. The minimum history gives three observations per locked predictor before an intercept, and the broad logarithmic grid is scale-independent after fold-local standardization. Complete-case eligibility fails closed on unavailable information. Three-month blocks and HAC lag 2 address the mechanical overlap of three-month monthly targets. Holm controls familywise error across the eight predefined predictor ablations without assuming independence. All choices were made from the charter, calendar, coverage, and model dimensionality, without reading target values or feature/target relationships.
- Consequences: Final-test outcomes cannot influence features, preprocessing, tuning, eligibility, uncertainty, or multiplicity. Every attempted or successful access to a final-test row or outcome-derived artifact after the freeze must be logged in `PROJECT_DATA.md`. Protocol corrections require a new preserved version and cannot be motivated by final-test results. Confirmatory evaluation remains blocked by source rights and point-in-time evidence and cannot run until target construction and implementation verification are complete.
- Evidence: `research/abnb/EVALUATION_PROTOCOL.md`; `research/abnb/config/evaluation_protocol.json` (`dd74ed2a387cfa9caab496fcfe12cdcda58b8a1bcdf689b009e20da0ec2b154c`); CAL-XNYS-001.
- Supersedes: none.

### D012 — Materialize targets without opening the frozen final test

- Date: 2026-09-25
- Status: accepted
- Scope: target | evaluation
- Decision: Construct `ABNB_RETURN_3M` as `maturity_adjusted_close / reference_adjusted_close - 1` from the exact ABNB adjusted closes on the calendar-derived reference and maturity sessions. Retain one target row per scheduled origin with explicit source, `IMMATURE`, and `WITHHELD_BY_PROTOCOL` states. For the development artifact, read prices only through 2025-08-29, the last development-label maturity; leave all 12 frozen final-test prices and returns null, and retain the three post-test origins as `IMMATURE`. Admit a training label only when it is finite, `VALID`, and `label_available_at <=` the current origin's `issued_at_utc`; do not perform preprocessing in target construction or selection.
- Rationale: Exact adjusted prices implement the split- and cash-dividend-adjusted total-return contract. A target-only artifact can complete and test the development pipeline without reading outcomes that the frozen protocol reserves for the single authorized final evaluation. Explicit statuses prevent missing, invalid, immature, or protocol-withheld values from being silently coerced.
- Consequences: `TARGET-001` is development-only and cannot support confirmatory claims while source rights and point-in-time adjustment evidence remain blocked. The future evaluation runner must unlock final-test prices only in its logged, single authorized pass and must fit every learned transform inside each training fold.
- Evidence: `research/abnb/pipeline/targets.py`; `research/abnb/tests/test_targets.py`; TARGET-001 in `PROJECT_DATA.md` (84 total ABNB tests passed on 2026-09-25).
- Supersedes: none.
