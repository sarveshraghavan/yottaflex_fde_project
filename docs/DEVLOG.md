# Development log

## 2026-11-03 — Single-line operating what-if

- Took the optional single-line valve-opening what-if from project review feedback and kept it separate from the canonical network generator so the 25 generated output hashes remain unchanged.
- Added paired `SimulationRun`-shape records with config hashes, a per-step flow/pressure/level comparison, a summary, deterministic IDs, and opening-range validation. The standalone files live in `what-if-output/`, which is git-ignored; they are not merged into the main relational export.
- Follow-up review noticed that the old “end” level was the last sample at 23:59 while flow deltas covered the full day. Updated the summary to integrate all 1,440 steps and added a test reconciling `Δlevel × 2,000 m²` to the integrated volume difference.
- Added raw copies of the two what-if review prompts under `docs/prompt_history/raw/`, updated the AI-use, design, dictionary, README and walkthrough docs, and grew the suite to 27 tests.
- Verified that a 24-hour run with an 80% valve opening lowers mean flow by about 5.60 m³/h and raises discharge pressure by about 20.90 kPa. The source and destination end-level deltas are about +0.0672 m and -0.0672 m, matching the approximately 134.34 m³ transferred-volume difference at the configured 2,000 m² area.
- After pushing `5e9e746`, cloned the public GitHub branch from scratch and ran the README flow: sample validation, JSON check, all 27 tests, the what-if command, full 100,000-row generation, full SQLite/JSON validation, and the 25-output reproducibility check all passed.

## 2026-11-02 — Public GitHub push

- After the GitHub credentials were corrected, pushed `3d6979f` to `sarveshraghavan/yottaflex_fde_project` on `main`.
- GitHub reports the repository visibility as public and the default branch as `main`; remote `main` matched the local commit at push time.
- Cloned published `main` at `98b63a2`. The README setup, sample validation, and all 23 tests passed before `data/` existed; full generation, SQLite/JSON validation, two-generation hash comparison, and all 23 tests then passed from that clone.

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
