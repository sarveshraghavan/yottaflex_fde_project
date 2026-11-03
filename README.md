# YottaFlexx Synthetic Plant Network Generator

**Repository:** [sarveshraghavan/yottaflex_fde_project](https://github.com/sarveshraghavan/yottaflex_fde_project)  
One deterministic, physics-based generator creates a synthetic plant network and its process truth, sensor readings, fault labels, alarms, and validation fixtures. No operating-plant data is used.


## Expected results

| Command | Expected result |
|---|---|
| `python src/validate_sqlite.py --data sample-data` | Valid report; zero foreign-key violations; exactly 10,000 telemetry rows; all required negative fixtures flagged |
| `python -m unittest discover -s tests -v` | 27 tests pass |
| Full generation command below | Exactly 100,000 telemetry rows across 33 runs; typically about 15 seconds and about 123 MB in `data/` |
| `python src/repro_network.py ...` | `reproducible: true`; matching row counts and SHA-256 hashes across 25 output files |
| `python src/what_if.py --out what-if-output --valve-opening 0.8 --hours 24` | Writes paired `SimulationRun` records, a 1,440-step comparison, and a JSON summary with flow, pressure, tank-volume and level deltas |

The full-generation time and disk use are typical for the project environment and can vary by machine.

> **Reviewer note:** the full 100,000-row dataset is intentionally generated on demand and is not committed because its SQL export exceeds GitHub's normal file-size warning limit. The committed 10,000-row `sample-data/` can be validated immediately; the exact command to regenerate the full dataset is below.

## Quick review from a clean clone

After the [setup](#setup), run these checks without generating the full `data/` directory:

```powershell
python src/validate_sqlite.py --data sample-data
python -m unittest discover -s tests -v
```

To create the full target-scale files, run the command in [Generate the target dataset](#generate-the-target-dataset). To verify two independent full generations, run the command in [Reproducibility and checks](#reproducibility-and-checks).

## Setup

Requires Python 3.10 or later. The generator, JSON/SQL exports, SQLite validation, and tests use only the Python standard library. `requirements.txt` records that there are no third-party packages to pin.

```shell
python --version
python -m venv .venv
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# macOS / Linux:        source .venv/bin/activate
python -m pip install -r requirements.txt
```

Use `python3` instead of `python` if `python` is not found. On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1` before installing dependencies.

## Generate the target dataset

```powershell
python src/network_expansion.py --out data --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 100000
```

The repository includes a 10,000-row starter dataset under `sample-data/`. Regenerate it with the same generator:

```powershell
python src/network_expansion.py --out sample-data --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 10000
```

The full `data/` output is ignored by Git because the SQL seed exceeds GitHub's 50 MB warning size. `sample-data/` is the reviewable starter set; the command above regenerates the full scale locally.

## Simulate an operating change

The standalone what-if command compares a baseline line with the same line at a changed valve opening, starting from identical tank levels and using the same time grid. For example:

```shell
python src/what_if.py --out what-if-output --valve-opening 0.8 --hours 24 --step-seconds 60
```

It writes two rows in `simulation_runs.csv`, each with a `config_json` and hash, paired per-step values and deltas in `what_if_timeseries.csv`, and mean flow/pressure changes plus end-of-window tank-volume and level differences in `summary.json`. The level deltas are calculated from the integrated flow differences and the 2,000 m² tank area, so they represent the end of the full interval (including the last time step). The records use a `SIM-WIF-` ID prefix and a separate output folder; they do not enter the main dataset's `simulation_runs.csv`. The default `what-if-output/` folder is git-ignored. Thus the command leaves the canonical generator's files and hashes unchanged. It models one valve opening on one line only; facility-wide demand schedules, mode transitions and multi-parameter changes remain out of scope.

For the example above, mean flow decreases by about 5.60 m³/h and discharge pressure rises by about 20.90 kPa. The integrated 24-hour volume difference is about 134.34 m³, corresponding to source and destination level differences of about +0.06717 m and −0.06717 m.

The default topology has 7/7/6 pumps, 10 tanks per facility, and 20 valves per facility. Valves are in series on each pump line; train sizes vary from two to four valves so the totals fit both the pump and facility counts. Every facility asset belongs to a connected graph. The generator allocates whole one-minute samples across runs to reach **exactly 100,000 telemetry rows**. Fault runs keep the same sample count as their baseline for paired comparisons; run lengths range from 69 to 71 samples at the default scale. Use `--time-steps` to give every run a fixed sample count instead, or adjust counts and `--telemetry-rows` to change scale.

Each facility gets 11 runs: two clean runs, three boundary runs (near-empty tank, near-full tank, pump curve edge), and six fault runs (leak, blockage, pump degradation, partial valve, sensor fault, and concurrent leak plus blockage). In total, 33 runs and 18 labeled fault runs are written. Runs use one nominal mode so this version can focus on fault signatures and exact scale.

Run windows are deliberately short (about 69–71 minutes) to preserve full sensor coverage while hitting the exact row target; they do not represent a diurnal cycle. Baseline source/destination levels shift by roughly half a metre over a run. Start times are not spread across morning and night demand conditions.

## Model and data limits

| Area | Assumption or limitation |
|---|---|
| Solver | Steady-state line hydraulics are solved at each one-minute step. Series valve assets and multiple pipe segments are represented, with resistance summed into the line solver. Transients, water hammer, pipe elasticity, and calibrated equipment curves are out of scope. |
| Pump degradation | A fault applies an immediate 10% shutoff-head reduction, not slow per-day wear. It lowers mean discharge pressure by about 24.5 kPa over these short runs. |
| Tanks | Shared source and destination tanks change level. Buffer tanks are reserve tanks with configured levels and no flow in this simulation. |
| Noise | Independent Gaussian assumptions: 2% flow, 1% pressure, and 0.5% level relative standard deviation. These are not measured plant noise. |
| Flow-balance tolerance | Two-sided 99% Gaussian envelope propagated from independent inlet/outlet flow sensor noise and summed across the facility: **25.06 m³/h** at default settings. This is not a measured residual sigma or a 3σ rule. Six of 1,049 fault-free steps (0.57%, including boundary runs) exceed it by chance. The injected conservation exception is 75.18 m³/h, three times the threshold. |
| Alarms and detectability | Window alarms and `detectable` use a **3σ threshold over each run window**, with the run-specific sample count. Alarms compare measured window effect; process-fault detectability compares true process effect (sensor-fault detectability uses its measured effect). The prototype only emits window alarms for labeled fault windows; it does not scan clean runs with a general detector, so alarm precision/recall is not an independent benchmark. |
| Sensors and residual | Paired inlet/outlet flow sensors provide clearer leak evidence than the network residual alone, which is weak at this noise level. Sensor locations are recorded by node or pipe and position. Distinguishing blockage from a partial valve by pressure requires taps on both sides of the restriction. A stuck inlet-flow sensor can create an apparent flow gap without a process fault. |
| Truth boundary | `telemetry.csv` contains measured values only. `export.json` is feature-oriented; `ground_truth.json` holds labels and process truth separately. SQL includes truth/evaluation tables for validation. Detector inputs must not join ground truth, process truth, alarm labels, or network-balance truth fields. Fault schedules are not stored in `SimulationRun.config_json`. |

## Reproducibility and checks

```shell
python src/network_expansion.py --out data --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 100000
python src/validate_sqlite.py --data data
python src/check_json.py --data data
python src/repro_network.py --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 100000
python -m unittest discover -s tests -v
```

For the checked-in starter set, use these exact commands:

```shell
python src/validate_sqlite.py --data sample-data
python src/check_json.py --data sample-data
python src/repro_network.py --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 10000
```

The SQLite validator loads `seed.sql` into an in-memory database, runs `PRAGMA foreign_key_check`, verifies joins and leakage boundaries, checks the exact telemetry count, and validates equipment-event transitions, per-asset chains within each run, and restorations at run end. It also checks Line-to-bridge redundancy in both directions. A six-row negative-fixture set includes an invalid lifecycle transition (`retired → active`) that must be rejected. The reproducibility script generates the outputs twice in temporary folders and compares row counts and SHA-256 hashes for CSV, SQL, JSON, and validation-summary outputs. `source_manifest.json` records relative filenames, hashes, CSV row counts, synthetic provenance, seed, and the relative generator command. `network_validation_summary.json` reports topology counts, telemetry volume, key and foreign-key checks, graph connectivity, edge-case fixtures, boundaries, residuals, and alarm references.

## Project layout

| Path | Purpose |
|---|---|
| `src/network_expansion.py` | Sole data generator and physics model. |
| `src/export_formats.py` | Writes portable JSON and SQLite seed SQL from the generated tables. |
| `src/validate_sqlite.py` | Loads the SQL seed and runs SQLite joins, FK, and leakage checks. |
| `src/check_json.py` | Parses and verifies the feature and truth JSON exports. |
| `src/repro_network.py` | Generates twice and compares all output hashes and CSV counts. |
| `src/line_physics.py` | Reusable one-line steady-state hydraulic solver. |
| `src/what_if.py` | Paired baseline and changed-valve operating-change simulation. |
| `data/` | Full generated CSVs, `seed.sql`, feature `export.json`, `ground_truth.json`, summary, and manifest; Git-ignored. |
| `sample-data/` | Checked-in starter-scale version of the same outputs. |
| `docs/` | Design rationale, data dictionary, assumptions, AI use, prompt history, dev log, and walkthrough outline. |
| `tests/` | Physics, topology, deterministic generation, and what-if tests. |
| `requirements.txt`, `LICENSE`, `.gitignore` | Dependency declaration, reuse license, and generated/temp-file exclusions. |

## Where to look

- Labels: `ground_truth.json`
- Per-step process values: `process_truth.csv`
- Triggered window alarms: `alarms.csv`
- Entity definitions and validation rules: [data dictionary](docs/data_dictionary.md)
- Model decisions: [design rationale](docs/DESIGN.md)
- Additional model details: [assumptions](docs/assumptions.md)

AI assistance was used for design review and heavily for code, tests, and documentation drafting; the contributor's role and review limits are described in [AI usage](docs/AI_USAGE.md). Project prompts are summarized in [prompt history](docs/prompt_history/README.md), and the demo plan is in the [walkthrough outline](docs/WALKTHROUGH.md).
