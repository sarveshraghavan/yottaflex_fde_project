# Development log

## 2026-11-02 — AI attribution and walkthrough answers

- Updated `AI_USAGE.md` to credit Claude for design reviews, validation suggestions, and checklists, and Codex for most code drafting, implementation, and local verification. Separated those contributions from my scope choices and review feedback.
- Added the current push/access and reviewer-readiness discussion to the prompt-history summary.
- Added walkthrough Q&A notes: the code uses bisection rather than `brentq`; the residual threshold derivation; why alarm agreement is not an independent benchmark; examples of corrected AI claims; and a proposed valve-opening what-if as the next operating-change feature.

## 2026-11-02 — AI-use clarity and negative tests

- Rewrote the AI-use account to identify which architecture choices Codex proposed, which scope and review decisions I made, and what remains unverified.
- Added failing-case tests for lifecycle reactivation, illegal operating-state transitions, broken event chains, missing restoration, and terminal-bridge mismatch; the suite now has 23 tests.
- Explicitly documented that ordinary demand/setpoint/mode changes are not simulated in this version.
- Ran the README workflow in a clean clone: sample validation and 23 tests passed with no `data/` directory; full generation, SQLite/JSON validation, two-generation hashes, and tests then passed.
- Tried pushing to the supplied GitHub URL. GitHub returned HTTP 403 for the authenticated account, so the commits remain local; no force push was attempted.

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
