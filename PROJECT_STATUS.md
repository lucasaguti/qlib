# ABNB Research Status

> **Dynamic document.** Update this file after every material implementation, validation, experiment, or change in blockers. Keep it factual and current; do not rewrite the charter in `PROJECT_INNATE.md`.

**Last updated:** 2026-09-25  
**Repository baseline:** Qlib checkout at `be725493`  
**Current phase:** documentation and research scaffolding  
**Final test status:** not selected; no access has occurred

## Current state

- The upstream Qlib research infrastructure is present.
- The project charter and agent operating instructions are established at repository root.
- No project dataset, indicator-outline PDF, project-specific implementation, frozen split, trained model, or result is currently registered.
- The user will manually add datasets and predictive-indicator PDF outlines.

## Workstream checklist

- [ ] Register incoming datasets and PDFs in `PROJECT_DATA.md` before using them.
- [ ] Verify source rights, schemas, checksums, timestamps, adjustment semantics, and XNYS calendar coverage.
- [ ] Define the project package/config/artifact layout without coupling research code to Qlib internals unnecessarily.
- [ ] Implement and test the point-in-time eligibility and three-calendar-month target contracts.
- [ ] Implement and test the eight locked features and per-value status fields.
- [ ] Freeze the development/final-test protocol and record the decision.
- [ ] Implement the zero and matured expanding-mean benchmarks.
- [ ] Implement fold-local Ridge preprocessing and chronological tuning.
- [ ] Run walk-forward evaluation and dependence-aware inference.
- [ ] Run predefined robustness analyses, then the authorized final evaluation.
- [ ] Publish a reproducible report, including negative or inconclusive findings.

## Immediate next actions

1. Wait for the manually supplied datasets and indicator PDFs.
2. Inventory them without mutating the originals; record hashes and provenance gaps.
3. Reconcile PDF definitions with the locked charter and log ambiguities before implementation.
4. Propose the development/final-test boundary from eligible sample coverage without inspecting final-test outcomes.

## Blockers and open inputs

| Item | State | Needed resolution |
|---|---|---|
| Historical datasets | Pending | User will add files manually |
| Indicator-outline PDFs | Pending | User will add files manually |
| Point-in-time availability evidence | Unknown | Assess once data arrives |
| Data usage/retention/ML rights | Unknown | Record source terms or user-supplied authorization |
| Final test period | Unset | Freeze before confirmatory evaluation |

## Latest verification

Documentation-only initialization; no code or data tests were required. Repository working state should be checked before each implementation session.
