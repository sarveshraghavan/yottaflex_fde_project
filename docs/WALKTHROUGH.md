# Project walkthrough (about 3 minutes)

1. **State the goal:** “This project generates a reproducible synthetic fluid-network dataset for testing fault analytics. It is not a calibrated digital twin.”
2. **Show the model:** open `src/line_physics.py` and `src/network_expansion.py`. Point out that faults change resistance, valve opening, or pump head before the solver calculates flow and pressure.
3. **Show the data boundary:** inspect `sample-data/telemetry.csv`, `sample-data/process_truth.csv`, and `sample-data/ground_truth.csv`. Explain that measured readings, solved process truth, and scenario labels are separate; the model feature export excludes truth tables.
4. **Show observability:** open `sample-data/sensors.csv` and `docs/data_dictionary.md`. Point to the inlet/outlet flow pair and pressure sensor positions around process restrictions.
5. **Show validation:** run `python src/validate_sqlite.py --data sample-data`, then `python -m unittest discover -s tests -v`. Point out the invalid `retired → active` fixture and event restoration checks.
6. **Show reproducibility and scale:** run `python src/repro_network.py --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 100000`. State that `source_manifest.json` records hashes and that the same generator writes the full set to ignored `data/`.
7. **Show an operating change:** run `python src/what_if.py --out what-if-output --valve-opening 0.8 --hours 24`. Explain that it compares identical initial conditions, writes paired `SimulationRun` configs outside the main dataset, and reports flow/pressure and tank deltas. At 80% opening, mean flow falls by about 5.60 m³/h, discharge pressure rises by about 20.90 kPa, and the 24-hour source/destination levels differ from baseline by about +0.0672/-0.0672 m. The integrated volume difference is about 134.34 m³, matching the level change times the 2,000 m² area.
8. **Close with limits:** mention the one-minute steady-state model, short generator run windows, assumed noise, reserve tanks, provisional thresholds, and the absence of an independent alarm benchmark. The what-if only changes one valve on one line; the next extensions could add pump speed, demand changes, and facility-wide schedules.

Before recording or presenting, run the commands on the machine used for the demo and confirm the current summary values. This file is a rehearsal outline, not a recording of a completed presentation.

## Likely reviewer questions

### Why `brentq`?

The current code does **not** use `brentq`; it uses bracketed bisection in `src/line_physics.py`. The solver has a scalar flow variable and a bracketed head-balance residual, and bisection gives predictable convergence without adding SciPy to a standard-library-only project. Brent's method could reduce function evaluations while retaining a bracket, but would add a dependency or require implementing more solver code. At this network size, the simpler method is adequate. Do not tell reviewers the code uses `brentq`.

### Where does the 25.06 m³/h threshold come from?

It is a provisional, two-sided 99% Gaussian envelope for the sum of the seven line-level inlet-minus-outlet residuals at one facility. With 2% relative flow noise and a nominal 130 m³/h per sensor, one sensor's assumed sigma is `0.02 × 130 = 2.6 m³/h`. For independent inlet and outlet sensors over seven pumps, propagated sigma is `sqrt(2 × 7) × 2.6`. Multiplying by the 99% two-sided normal quantile, 2.576, gives about `25.06 m³/h`. It is a configured-noise assumption, not calibrated against real residual data.

### Why isn't the alarm agreement an independent benchmark?

The alarm rows are created only for labeled fault windows and use the same window effect, noise assumption, and threshold family as `detectable`. Agreement checks that two pieces of generator logic remain consistent. It does not measure how an independently designed detector performs on unseen or fault-free data.

### What AI output did I correct or qualify?

I challenged the implication that near-zero mass balance proves realism; tank storage is updated from the same solved flows, so the check is partly by construction. I also pointed out that an early leak threshold of 1.0 sat at the bottom of the then-current sweep. The sweep was extended down to 0.05; the later result brackets the paired-flow crossing between 1.25 and 1.5 under assumed noise, not measured plant noise.

For the what-if, I suggested comparing the 24-hour flow-volume difference with tank-level displacement. Codex ran the check and found its summary used the last sampled level at 23:59 although the flow means covered the final minute as well. I asked Codex to correct the time boundary and test `Δlevel × tank area ≈ Δvolume`; the summary now integrates all 1,440 steps and the test checks it against the 2,000 m² tank area. These review details are documented in `docs/DESIGN.md` and `docs/AI_USAGE.md`.

### Why is the what-if limited to one parameter on one line?

The small wrapper reuses the validated one-line solver, isolates the effect of one valve change from the nominal case, and writes outside the main generator so its hashes do not change. At 80% opening in this model, mean flow falls about 5.60 m³/h, discharge pressure rises about 20.90 kPa, and the source/destination levels differ by about +0.0672/-0.0672 m after 24 hours. The summary reconciles the integrated 134.34 m³ volume difference with those levels using the 2,000 m² tank area. I would extend it next with pump speed, demand changes, and then facility-wide scenarios with shared tanks and schedules.
