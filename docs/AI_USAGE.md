# How I used AI on this project

I used both Claude and Codex. I relied heavily on AI for the implementation: Codex drafted most of the generator, solver integration, exports, validators, tests, and documentation. I did not write that code unaided.

## What each tool contributed

- **Claude:** design review, validation suggestions, and reviewer checklists. Its feedback focused on risks such as mass balance being near zero by construction, paired-flow noise, sensor placement, overly easy fault magnitudes, sweep thresholds, lifecycle/event coverage, redundant bridges, and submission completeness.
- **Codex:** primary code drafting and local implementation. It translated the chosen design into Python, generated SQL/JSON/CSV outputs, added validators and tests, and ran the build, test, SQLite, and reproducibility commands in this workspace.

Claude and Codex both contributed suggestions; I chose which suggestions to adopt and directed the project scope and build sequence. The one-line solver approach, parameter-based process faults, paired inlet/outlet flow sensors, separate process-truth data, and the windowed detectability rule were design suggestions developed with AI assistance that I chose to use. The 3σ rule and noise percentages are modeling assumptions, not values from the brief or plant measurements.

## What I reviewed, changed, and checked

I steered the work toward the brief's required scale, entities, edge cases, exports, and reviewer documentation. During review, I raised several points that changed the claims or checks:

- I pushed back on treating the near-zero mass-balance residual as proof of realistic physics. The same solved flows update tank storage, so closure mainly checks bookkeeping; the design and README now say this.
- I questioned an early report that treated a leak threshold of 1.0 as a minimum when it was the bottom of that sweep. The sweep was later extended down to 0.05. In the updated summary, the paired-flow crossing is bracketed between leak coefficients 1.25 and 1.5 under the assumed 2% sensor-noise floor; it remains a model result, not a measured detection limit.
- I asked that paired-flow detectability account for noise from both sensors and that sensor locations, short run windows, reserve tanks, expected clean residual exceedances, lifecycle transitions, and bridge consistency be made explicit.
- I directed the lifecycle review that added the rejected `retired → active` fixture and requested failure tests for invalid event transitions, broken chains, missing restoration, and a terminal bridge mismatch.

Codex executed the checks in this workspace; I reviewed their results. The latest clean-clone run completed the README setup and verification commands. Before generating `data/`, sample SQLite validation and all 23 tests passed; then full generation, SQLite/JSON validation, the two-generation hash check, and all 23 tests passed. The target run produced exactly 100,000 telemetry rows, a maximum true residual of about 1.75 × 10⁻⁹ m³/h, and 6/1,049 (0.57%) fault-free residual samples outside the assumed 99% envelope. Reproducibility matched hashes and row counts across 25 outputs.

## What I have not verified

I have not compared the synthetic model, noise assumptions, or thresholds with real plant measurements, and I do not know whether these settings generalize to a real facility. I have not independently rehearsed or presented the walkthrough. The first push attempt failed with HTTP 403 under the wrong GitHub credentials; after authentication was corrected, commit `3d6979f` was pushed to the public repository `sarveshraghavan/yottaflex_fde_project`. A clean-clone check against the GitHub copy is being completed separately. No generated value is real plant data; all assets, scenarios, readings, events, alarms, and labels are synthetic.
