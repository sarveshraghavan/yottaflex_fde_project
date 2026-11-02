# Development log

## 2026-11-02 — Reviewer-readiness documentation

- Added a design rationale with scope, choices, trade-offs, test approach, limitations, and measured validation evidence.
- Added an AI-use statement, a summarized prompt history, and a short walkthrough guide.
- Clarified that the full-scale output is generated on demand because its SQL seed is too large for a normal GitHub file; the committed sample remains available for inspection.

## 2026-11-02 — Lifecycle and event validation

- Added lifecycle transition validation through a rejected `retired → active` negative fixture.
- Checked event transition pairs, per-asset chains within a simulation run, and matching restoration at run end.
- Extended bridge checks to catch orphaned or mismatched parent/equipment references.
- Regenerated the sample and full outputs; reran SQLite validation, 18 tests, and full-output reproducibility.

## Earlier milestones

- **`f4d2bea` — Add reproducible synthetic plant dataset sample:** introduced the starter dataset and core generator artifacts.
- **`6ab052a` — Align entity dictionary and equipment identifiers:** aligned schema documentation and sensor identifiers with the specification.
- **`22a65e2` — Validate lifecycle and equipment event transitions:** added lifecycle/event validation and refreshed committed sample artifacts.

See `git log --oneline` for the repository history. The generated target-scale dataset is local and ignored; regenerate it with the README command and seed.
