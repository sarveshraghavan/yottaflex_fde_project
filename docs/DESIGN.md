# Design rationale

## Problem and scope

The project brief asks for a reproducible synthetic dataset for an industrial fluid network: facilities and connected pumps, tanks, valves and pipes; operating modes; sensor telemetry; process faults and sensor faults; alarms; ground truth; validation and documentation. The target configuration is three facilities, 20 pumps, 30 tanks, 60 valves and exactly 100,000 telemetry rows.

This repository implements one deterministic generator at both starter and target scale. The checked-in `sample-data/` has 10,000 telemetry rows so reviewers can inspect a manageable dataset. Full outputs are generated into the ignored `data/` directory using the command in the README. The model is a prototype for dataset generation and fault-signature experiments, not a digital twin or an operational alarm product.

Deliberately out of scope are real facility data, transient hydraulics and water hammer, calibrated pump/valve curves, diurnal demand, a general-purpose online alarm detector, measured sensor-noise distributions, facility-wide demand schedules, mode transitions, and multi-parameter operating changes. In addition to the dataset generator, `src/what_if.py` provides a standalone single-line valve-opening comparison. It reuses the validated solver while keeping exploratory outputs separate from the generator and its reproducibility hashes.

## Key decisions

- **Faults change the process model.** A leak adds an orifice-like outlet, blockage raises pipe resistance, pump degradation lowers shutoff head, and a partial valve changes its opening/resistance. The hydraulic solver produces the resulting flows and pressures; the generator does not create faults by multiplying telemetry signals. This keeps process truth and tank storage effects connected to the simulated fault.
- **Process truth and measurements are separate.** `process_truth` stores the solved value and injected noise for evaluation; `telemetry` contains the measured value and quality flag. Sensor faults change readings while leaving process truth unchanged.
- **Ground truth has its own export.** `ground_truth.json` contains scenario labels and process/evaluation tables. `export.json` is the feature-oriented export and excludes labels and truth tables. The complete SQL seed intentionally contains both for validation, so a model input pipeline must select feature tables only.
- **One generator serves all scales.** `src/network_expansion.py` builds both the starter sample and full dataset, avoiding drift between a preview script and the submission generator. A reusable single-line solver is composed across facility networks.
- **Operating what-if stays separate.** `src/what_if.py` compares one valve opening with the baseline using the same solver and initial tank levels. It writes paired run records and deltas to a separate output folder. This narrow wrapper demonstrates an operating change without altering the canonical full-dataset generator or its output hashes; it is not facility-wide scheduling.
- **Sensor locations are explicit.** Sensors record the asset/node or pipe and position. Each line has paired inlet and outlet flow sensors; their difference is the primary leak signal. Pressure taps at both sides of a restriction help separate blockage from a partial valve.
- **Determinism is part of the output contract.** Seeded assumptions, fixed decimal formatting, sorted exports and SHA-256 manifests make generated files comparable across repeat runs.

## Trade-offs

- **Steady state each minute versus transients:** the solver finds an operating point per step, which is fast and stable for large synthetic exports. It does not represent water hammer, pressure waves, or other fast dynamics.
- **Short runs versus diurnal coverage:** the exact 100,000-row target is reached by allocating 69–71 one-minute samples per run while preserving paired baseline/fault windows and all sensors. These roughly one-hour windows do not cover a full day or morning/night patterns.
- **Reserve tanks versus active exchange:** shared source and destination tanks evolve with flow. Additional tanks are reserve tanks with configured initial levels and no flow in this simulation; their telemetry is flat by design.
- **Synthetic noise versus measured noise:** independent Gaussian noise is assumed at 2% relative standard deviation for flow, 1% for pressure, and 0.5% for level. These values are illustrative configuration choices, not estimates from plant data.
- **Simple thresholds versus a detector study:** alarm and `detectable` labels use a run-window 3σ comparison based on the configured noise. Alarms are emitted only for labeled fault windows. Their agreement with labels is a consistency check, not an independent alarm-performance benchmark.

## Testing and validation approach

The test suite covers the one-line physics signatures, tank bounds and determinism, golden operating-point values, topology allocation/connectivity, exact row planning, sensor-fault separation, and deterministic file output. What-if tests check the paired SimulationRun configs and hashes, repeat-run identity, input validation, expected flow/level directions, and the balance between integrated flow-volume differences and tank-level changes. Failure-path tests reject a retired-to-active lifecycle transition, an illegal equipment state change, a broken event chain, a missing restoration, and a terminal valve/bridge mismatch. The generator also writes isolated invalid and boundary fixtures. The SQLite validator loads the generated SQL seed and checks foreign keys, joins, leakage boundaries, polymorphic pipe endpoints, sensor IDs, bridge redundancy in both directions, and equipment-event transitions/chains/restorations. `src/repro_network.py` generates twice and compares row counts and SHA-256 hashes for every output, including SQL, both JSON exports, and the validation summary.

Reproduce the checks with the commands in the README. On the default configuration, the test suite contains 27 tests.

## Limitations

- All assets, telemetry, scenarios, and noise are synthetic; no real operational records were used.
- Noise levels and the propagated two-sided 99% flow-balance envelope are explicit assumptions. The tolerance is provisional and should be recalibrated against measured residuals before use beyond this prototype.
- The clean-run measured residual exceeds the envelope on 6 of 1,049 samples (0.57%) under the configured seed/noise. Such exceedances are expected statistical outcomes, not injected faults or alarm records.
- The true network residual is near zero because the same solved flows update tank storage. It checks bookkeeping and conservation implementation, not physical realism.
- The one-minute steady-state model omits transients, water hammer, pipe elasticity and calibrated equipment curves.
- Runs last about an hour, so there is no diurnal cycle. The pump degradation is an immediate 10% head reduction, not slow wear.
- Reserve tanks remain at configured levels. Partial valve and blockage signatures depend on having pressure observations at the relevant sides of the restriction.
- The labeled-window alarm check reuses the same effect/noise window logic as `detectable`; it is not an independent detector and should not be reported as unbiased precision/recall.
- Facility-wide demand schedules, mode transitions and multi-parameter operating changes are not simulated. The standalone what-if covers one valve opening on one line only.
- A full clean-run detector, field-calibrated thresholds, and a benchmark against measured fault data have not been built.

## Evidence that the implementation works

For seed `20261022` at the target scale, the generated summary reports:

- exactly **100,000 telemetry rows** across 33 runs;
- a maximum absolute true network residual of about **1.75 × 10⁻⁹ m³/h** (expected near zero by construction);
- **6/1,049 = 0.57%** fault-free residual samples beyond the configured two-sided 99% envelope;
- all six invalid fixtures flagged, including the invalid lifecycle transition, and all three boundary fixtures in range;
- valid equipment-event transitions and per-run chains, with every fault transition restored at run end;
- zero foreign-key violations and zero mismatches/orphans in the line/valve/pipe bridge checks;
- **27 passing tests**, including explicit lifecycle/event failure cases and a check that the 24-hour what-if volume difference agrees with tank level change times the configured 2,000 m² tank area; and
- matching row counts and hashes across all **25 generated output files** in the reproducibility check.

These results establish repeatability and internal checks for this model. They do not establish that its hydraulic assumptions match a real installation.
