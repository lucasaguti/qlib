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
