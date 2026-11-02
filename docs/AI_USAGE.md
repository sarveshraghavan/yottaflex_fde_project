# How I used AI on this project

I used Codex as my main coding assistant. It drafted most of the generator, solver integration, export and validation code, tests, and project documentation. That is substantial use, and I do not present the implementation as code I wrote unaided.

## Where AI helped

Codex accelerated the first implementation and the repeated edit-and-check cycle: it drafted the Python components, tests, SQLite/JSON export logic, and documentation, then ran the generator, tests, SQLite checks, and reproducibility script in the project workspace. It also helped turn review comments into specific validator changes and regression checks.

## Who proposed what

Codex proposed starting with a one-line hydraulic solver and making process faults change solver parameters. It also proposed paired inlet/outlet flow sensors for leak detection, a separate process-truth layer, a windowed noise-based `detectable` rule, a single generator for preview and full scale, and the initial expansion order. I chose to proceed with that approach and repeatedly steered the scope toward the brief's row counts, required entities, edge cases, documentation, and reviewability.

The 3σ window threshold and the specific synthetic noise percentages are modeling choices developed with AI assistance. They are not supplied by the brief or supported by plant measurements. The code records them as assumptions; they should not be represented as operationally validated settings.

## What I reviewed and changed

I reviewed the proposed design and generated summaries, then pushed back on several claims or gaps:

- I pointed out that near-zero mass-balance residual is partly guaranteed by using the solved flows to update tank storage. It is a bookkeeping check, not evidence that the physics is realistic; the design and README now say that.
- I questioned a reported leak threshold of 1.0 because it was at the edge of the sweep. That result should be treated as censored unless the sweep continues below it.
- I asked that paired-flow detectability include the combined noise of both sensors, and raised the need to account for sensor placement, short run windows, reserve tanks, alarm false exceedances, lifecycle state changes, and bridge consistency.
- I directed the lifecycle review that led to the invalid `retired → active` fixture and requested event-chain, restoration, and bridge-mismatch failure tests.

Codex executed the latest 23-test suite, sample and full SQLite validation, and the full reproducibility run. I reviewed the resulting logs and summaries in this session. The target-scale run reported exactly 100,000 telemetry rows, a maximum true residual of about 1.75 × 10⁻⁹ m³/h, and 6/1,049 (0.57%) fault-free samples beyond the modeled 99% residual envelope. The reproducibility script matched hashes and row counts across 25 outputs.

## What I have not verified

I have not compared the synthetic model or its noise assumptions with real plant measurements, nor verified that these thresholds generalize to a real facility. I have not completed a clean-clone run of the README commands or independently rehearsed/presented the walkthrough. The full output was generated locally, but no GitHub push has succeeded yet because GitHub returned HTTP 403 for the configured repository URL.

All generated process values, readings, events, alarms, and labels are synthetic. No real plant records or third-party operational dataset were used.
