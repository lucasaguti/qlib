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
