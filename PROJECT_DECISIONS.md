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
