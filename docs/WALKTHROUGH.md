# Project walkthrough (about 3 minutes)

1. **State the goal:** “This project generates a reproducible synthetic fluid-network dataset for testing fault analytics. It is not a calibrated digital twin.”
2. **Show the model:** open `src/line_physics.py` and `src/network_expansion.py`. Point out that faults change resistance, valve opening, or pump head before the solver calculates flow and pressure.
3. **Show the data boundary:** inspect `sample-data/telemetry.csv`, `sample-data/process_truth.csv`, and `sample-data/ground_truth.csv`. Explain that measured readings, solved process truth, and scenario labels are separate; the model feature export excludes truth tables.
4. **Show observability:** open `sample-data/sensors.csv` and `docs/data_dictionary.md`. Point to the inlet/outlet flow pair and pressure sensor positions around process restrictions.
5. **Show validation:** run `python src/validate_sqlite.py --data sample-data`, then `python -m unittest discover -s tests -v`. Point out the invalid `retired → active` fixture and event restoration checks.
6. **Show reproducibility and scale:** run `python src/repro_network.py --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 100000`. State that `source_manifest.json` records hashes and that the same generator writes the full set to ignored `data/`.
7. **Close with limits:** mention the one-minute steady-state model, short run windows, assumed noise, reserve tanks, provisional thresholds, and the absence of an independent alarm benchmark.

Before recording or presenting, run the commands on the machine used for the demo and confirm the current summary values. This file is a rehearsal outline, not a recording of a completed presentation.

## Likely reviewer questions

### Why `brentq`?

The current code does **not** use `brentq`; it uses bracketed bisection in `src/line_physics.py`. The solver has a scalar flow variable and a bracketed head-balance residual, and bisection gives predictable convergence without adding SciPy to a standard-library-only project. Brent's method could reduce function evaluations while retaining a bracket, but would add a dependency or require implementing more solver code. At this network size, the simpler method is adequate. Do not tell reviewers the code uses `brentq`.

### Where does the 25.06 m³/h threshold come from?

It is a provisional, two-sided 99% Gaussian envelope for the sum of the seven line-level inlet-minus-outlet residuals at one facility. With 2% relative flow noise and a nominal 130 m³/h per sensor, one sensor's assumed sigma is `0.02 × 130 = 2.6 m³/h`. For independent inlet and outlet sensors over seven pumps, propagated sigma is `sqrt(2 × 7) × 2.6`. Multiplying by the 99% two-sided normal quantile, 2.576, gives about `25.06 m³/h`. It is a configured-noise assumption, not calibrated against real residual data.

### Why isn't the alarm agreement an independent benchmark?

The alarm rows are created only for labeled fault windows and use the same window effect, noise assumption, and threshold family as `detectable`. Agreement checks that two pieces of generator logic remain consistent. It does not measure how an independently designed detector performs on unseen or fault-free data.

### What AI output did I correct or qualify?

I challenged the implication that near-zero mass balance proves realism; tank storage is updated from the same solved flows, so the check is partly by construction. I also pointed out that an early leak threshold of 1.0 sat at the bottom of the then-current sweep. The sweep was extended down to 0.05; the later result brackets the paired-flow crossing between 1.25 and 1.5 under assumed noise, not measured plant noise. Those caveats are documented in `docs/DESIGN.md` and `docs/AI_USAGE.md`.

### Why is operating-change simulation out of scope, and what would come next?

This version first establishes repeatable fault signatures and reaches the exact dataset scale. Ordinary changes such as a demand schedule or valve setpoint are not represented; all runs use the nominal mode except for boundary and fault scenarios. The first extension would be a `what-if` command that reruns the solver from identical initial conditions with a changed valve opening (for example, 100% versus 80%) and reports the flow, pressure, and tank-level differences over the same time grid.
