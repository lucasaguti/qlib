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

No datasets registered.

| ID | Path | Role/instruments | Provider/version | Coverage | Adjustment and availability semantics | SHA-256 | Rights | State |
|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | awaiting user-supplied data |

## Calendars and corporate actions

No calendar or corporate-action sources registered.

| ID | Path | Identity/version | Coverage | Availability evidence | SHA-256 | State |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | pending |

## Indicator specifications and PDFs

No PDFs registered.

| ID | Path | Purpose | Version/date | SHA-256 | Reconciliation state |
|---|---|---|---|---|---|
| — | — | — | — | — | awaiting user-supplied outlines |

Any PDF interpretation that changes or clarifies a formula, seed, null behavior, timing rule, or parameter must be recorded in `PROJECT_DECISIONS.md`. A conflict with `PROJECT_INNATE.md` requires user resolution; a PDF does not silently override the charter.

## Derived datasets and experimental snapshots

No derived artifacts registered.

| ID | Path | Parents | Build config | Code revision | Coverage/split | SHA-256 | State |
|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | pending |

## Final-test access log

The final period is not yet selected. Once frozen, append every access, including failed or diagnostic access.

| Timestamp (UTC) | Actor | Purpose | Artifact/query | Authorization | Outcome |
|---|---|---|---|---|---|
| — | — | — | — | — | no access |
