# Agent Guide: ABNB Forecasting Research

## Start here

This repository is an upstream Qlib checkout with a project-specific ABNB forecasting study layered onto it. Before acting, read in this order:

1. `PROJECT_INNATE.md` — authoritative, stable research contract.
2. `PROJECT_STATUS.md` — current phase, blockers, and next actions.
3. `PROJECT_DECISIONS.md` — durable decisions and their evidence.
4. `PROJECT_DATA.md` — input/output registry and final-test access log.
5. Relevant upstream Qlib code, tests, and documentation.

If documents conflict, follow the innate charter, then the most recent accepted decision, then current status. Ask the user to resolve any ambiguity that could change the target, information set, final-test isolation, or research claim.

## Document ownership

- Do not edit `PROJECT_INNATE.md` without explicit user instruction to change the research charter.
- Treat `PROJECT_STATUS.md`, `PROJECT_DECISIONS.md`, and `PROJECT_DATA.md` as persistent project memory, not generated summaries.
- After material work, update status, decisions, and data entries that the work actually changed. Preserve history in the decision and access logs.
- Use exact paths, config names, checksums, code revisions, and experiment/recorder IDs. Never report an artifact or test as present/passing without verifying it.
- Keep these root documents concise; detailed reports and machine-generated manifests should be linked rather than pasted into them.

## Research invariants

- Prevent look-ahead leakage at data, feature, label, preprocessing, tuning, and evaluation boundaries.
- Use the exact XNYS calendar and three-calendar-month maturity contract; never substitute calendar days or a fixed session count.
- At each origin, admit only point-in-time-available values and fully matured labels.
- Fit every learned transform within its training fold. Use chronological validation only.
- Maintain adjusted-price and corporate-action vintage evidence. Missing evidence remains an explicit limitation, not an assumed pass.
- Preserve missing/invalid/unavailable statuses. Do not fill price histories, relax windows, substitute peers, or silently coerce invalid observations.
- Keep the initial eight-feature set and three-model comparison fixed unless a separately labeled extension is authorized.
- Isolate the frozen final test and append every access to `PROJECT_DATA.md`.
- Treat overlapping targets and repeated searches as dependence and multiple-testing problems.
- Never connect research output to live trading or present it as investment advice.

## Working in this Qlib repository

- Prefer project-scoped code, configs, and tests over edits to reusable Qlib internals. Do not choose a permanent layout until implementation requirements and incoming data are known; record the choice in `PROJECT_DECISIONS.md`.
- Relevant framework surfaces include `qlib.data.dataset` for loaders/handlers/processors, `qlib.contrib.model.linear.LinearModel` for the Ridge baseline, `qlib.workflow` for experiment recording, and YAML workflows under `examples/benchmarks` as configuration examples.
- Qlib's generic portfolio backtest is not the primary evaluation. Implement forecast-level walk-forward metrics and dependence-aware inference explicitly.
- Keep raw, interim, processed, and snapshot layers separate. Raw inputs are immutable and should generally remain untracked; never add supplied data or licensed documents to Git without authorization.
- Configure paths and cutoffs rather than embedding machine-specific absolute paths or dates in research logic.
- Fix random seeds where applicable and persist environment, config, data checksum, calendar version, code revision, and outputs through Qlib recording or an equally auditable manifest.

## Implementation standards

- Write tests with each contract-bearing component. Include boundary cases for month-end/maturity selection, holidays, late/missing observations, corporate-action availability, recursive-indicator resets, matured-label admission, and fold-local preprocessing.
- Prefer small deterministic units for calendar, availability, feature, target, split, and metric logic.
- Use timezone-aware timestamps and name timestamp fields by meaning, such as `observed_at`, `available_at`, `issued_at`, and `matured_at`.
- Fail closed on provenance or eligibility uncertainty. Surface counts and reasons for excluded observations.
- Keep exploratory and confirmatory artifacts visibly distinct. Do not use final-test results to revise features, models, thresholds, or preprocessing.
- Preserve existing user changes. Inspect `git status` before edits and do not overwrite unrelated work.

## Verification

Run the narrowest relevant tests first, then broaden in proportion to impact. Typical commands are:

```powershell
python -m pytest <relevant-test-path> -q
python -m pytest . -m "not slow"
make black
```

On Windows, `make` targets may not be available; use their underlying commands from `Makefile` when needed. Do not claim the full suite passed if only focused tests ran. Documentation-only changes require link/content review and `git diff --check`, not the Python suite.

## Completion protocol

Before handing off a material change:

1. verify the implementation and inspect the final diff;
2. register new or changed data/artifacts and checksums;
3. append material decisions, including rationale and evidence;
4. update current status, blockers, next actions, and test results;
5. state exactly what was tested and what remains unverified.
