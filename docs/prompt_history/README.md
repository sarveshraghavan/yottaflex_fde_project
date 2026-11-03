# Prompt history

This is a concise record of the main instructions and review questions that shaped the build. It summarizes the conversation rather than reproducing every exchange verbatim.

1. **Project brief:** supplied a business problem about pumps, tanks, valves, sensors and flow data, then asked what to build.
2. **Prototype first:** asked for a concrete project and agreed to validate one source-tank → pump → valve → pipe → destination-tank line before scaling up.
3. **Fault signatures:** requested baseline, leak, and blockage comparisons with flow, pressure, tank levels, and a mass-balance residual; emphasized that faults should arise from model parameters.
4. **Risk review:** raised caveats about mass balance being partly by construction, leak detection needing paired flows, sensor location affecting pressure signs, fault severity, and time-series behavior.
5. **Expand the prototype:** asked for sensitivity sweeps, degradation and valve cases, golden values, and model limits in the README.
6. **Noise and labels:** asked to account for paired-sensor noise, separate process truth from measured telemetry, keep fault schedules out of model inputs, and make detectability rules explicit.
7. **Submission completeness:** requested full scale, exact 100,000 telemetry rows, five negative edge cases, alarms, operating modes, dictionary/ERD, SQL and JSON exports, provenance, reproducibility, and path/leakage checks.
8. **Review refinements:** asked to scrutinize run duration, false alarms, tolerance derivation, reserve tanks, redundant Line/bridge references, polymorphic pipe endpoints, and sensor identifier width.
9. **Lifecycle validation:** asked to validate allowed equipment-event transitions, event chaining and restoration, and to add an invalid `retired → active` lifecycle fixture.
10. **Reviewer readiness:** requested visible design reasoning, a clean-clone test, clarity about the ignored full dataset, and supporting AI-use and prompt-history documentation.
11. **Push and final disclosure:** provided the intended GitHub URL and asked for a no-force push, then a clean-clone verification of the README workflow. Also requested accurate attribution of Claude's design reviews/checklists and Codex's implementation work, this conversation in the prompt history, and walkthrough preparation for the solver choice, residual threshold, alarm-check limitations, AI corrections, and a future operating-change what-if.

12. **Operating-change what-if:** accepted the reviewer-proposed single-line valve-opening command; requested paired `SimulationRun` configs, flow/pressure/tank deltas, determinism, input validation, and unchanged full-generator hashes. Follow-up review requested a volume-to-level reconciliation test and consistent updates to the design, data dictionary, AI-use note, dev log, walkthrough, and raw prompt archive.

See [AI usage](../AI_USAGE.md), [design rationale](../DESIGN.md), and the [project README](../../README.md) for the resulting decisions and checks.

The verbatim what-if review text is archived in [raw review prompts](raw/what-if-review.md). The chronological [Codex user-prompt archive](raw/codex-user-prompts.jsonl) contains the 30 user-message text payloads from this project thread. Local machine paths are redacted, attachments are not embedded, and assistant responses are not included. A full Claude source conversation was not available as an export.
