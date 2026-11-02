# YottaFlexx Synthetic Plant Network Generator

One deterministic, physics-based generator creates the plant assets, process truth, sensor readings, fault labels, alarms, and validation fixtures. All values are synthetic; no operating-plant data is used.

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

```powershell
python --version
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Generate the target dataset

```powershell
python src/network_expansion.py --out data --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 100000
```

The repository includes a 10,000-row starter dataset under `sample-data/`. Regenerate it with the same generator:

```powershell
python src/network_expansion.py --out sample-data --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 10000
```

The full `data/` output is ignored by Git because the SQL seed exceeds GitHub's 50 MB warning size. `sample-data/` is the reviewable starter set; the command above regenerates the full scale locally.

The default topology has 7/7/6 pumps, 10 tanks per facility, and 20 valves per facility. Valves are in series on each pump line; train sizes vary from two to four valves so the totals fit both the pump and facility counts. Every facility asset belongs to a connected graph. The generator allocates whole one-minute samples across runs to reach **exactly 100,000 telemetry rows**. Fault runs keep the same sample count as their baseline for paired comparisons; run lengths range from 69 to 71 samples at the default scale. Use `--time-steps` to give every run a fixed sample count instead, or adjust counts and `--telemetry-rows` to change scale.

Each facility gets 11 runs: two clean runs, three boundary runs (near-empty tank, near-full tank, pump curve edge), and six fault runs (leak, blockage, pump degradation, partial valve, sensor fault, and concurrent leak plus blockage). In total, 33 runs and 18 labeled fault runs are written. Ordinary operating changes (such as demand schedules, setpoint changes, and mode transitions) are not simulated yet; the runs use one nominal mode so this version can focus on fault signatures and exact scale.

Run windows are deliberately short (about 69–71 minutes) to preserve full sensor coverage while hitting the exact row target; they do not represent a diurnal cycle. Baseline source/destination levels shift by roughly half a metre over a run. Start times are not spread across morning and night demand conditions.

## Model and data limits

Each pump line uses the single-line steady-state solver at every one-minute step. Series valve assets and multiple pipe segments are represented in the topology, with resistance summed into the line solver. The pump-degradation case applies a 10% shutoff-head reduction as an immediate fault, not a slow per-day drift; it lowers mean discharge pressure by about 24.5 kPa over the short run, so it remains clearly measurable at this horizon. The short run is not intended to model gradual wear. Shared source and destination tanks change level over time; the additional buffer tanks are reserve tanks with configured levels and no flow in this simulation. It does not model transients, water hammer, pipe elasticity, or calibrated equipment curves.

The true flow residual is a reconciliation check: the same solved flows update tank storage, so closure is expected by construction and does not establish physical realism. The validator threshold is a two-sided 99% Gaussian envelope propagated from independent inlet/outlet flow sensor noise and summed across the facility. It is not a measured residual sigma or a 3σ rule. At the default settings the threshold is 25.06 m³/h; 6/1,049 fault-free steps (0.57%, including boundary runs) exceed it by chance under the noise model. Those residual exceedances are validation statistics, not `alarms.csv` records and not ground-truth process faults. The injected flow-conservation exception is 75.18 m³/h, exactly three times the threshold. The residual alone is a weak leak signal at this noise level; paired inlet/outlet flow sensors on each line provide the clearer leak evidence.

Sensor noise is independent Gaussian noise, configured as 2% flow, 1% pressure, and 0.5% level relative standard deviation. These are explicit assumptions, not measured plant noise. Window alarms and `detectable` use the same 3σ threshold and run-specific sample count. Alarms compare the measured window effect; for process faults, `detectable` compares the true process effect with that same threshold (sensor-fault detectability uses its measured effect). This prototype emits window alarms only for labeled fault windows; it does not scan clean runs with a general detector, so its alarm count should not be presented as independent precision/recall. `telemetry.csv` contains measured values only. `export.json` is the feature-oriented JSON export; `ground_truth.json` contains labels and process truth separately. The full SQL seed includes truth/evaluation tables for validation. Detector feature inputs must use telemetry and asset/run context only; they must never join to `ground_truth`, `process_truth`, alarm labels, or network-balance truth fields. Fault schedules and labels are not in `SimulationRun.config_json`.

Sensor locations are recorded by node or pipe and position. The included rules describe the model's expected signs: a blockage increases pressure loss across the restricted pipe and pump-discharge pressure, while a partial valve increases pressure loss across the valve. Distinguishing faults by pressure requires taps on both sides of the restriction. A stuck inlet-flow sensor may create an apparent paired-flow gap, while its process truth remains unchanged and its label is `is_process_fault=false`.

## Reproducibility and checks

```powershell
python src/network_expansion.py --out data --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 100000
python src/validate_sqlite.py --data data
python -c "import json; [json.load(open(p, encoding='utf-8')) for p in ('data/export.json', 'data/ground_truth.json')]; print('JSON valid')"
python src/repro_network.py --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 100000
python -m unittest discover -s tests -v
```

To validate the checked-in starter set, substitute `sample-data` for `data` and use `--telemetry-rows 10000` in the reproducibility command.

The SQLite validator loads `seed.sql` into an in-memory database, runs `PRAGMA foreign_key_check`, verifies joins and leakage boundaries, checks the exact telemetry count, and validates equipment-event transitions, per-asset chains within each run, and restorations at run end. It also checks Line-to-bridge redundancy in both directions. A six-row negative-fixture set includes an invalid lifecycle transition (`retired → active`) that must be rejected. The reproducibility script generates the outputs twice in temporary folders and compares row counts and SHA-256 hashes for CSV, SQL, JSON, and validation-summary outputs. `source_manifest.json` records relative filenames, hashes, CSV row counts, synthetic provenance, seed, and the relative generator command. `network_validation_summary.json` reports topology counts, telemetry volume, key and foreign-key checks, graph connectivity, edge-case fixtures, boundaries, residuals, and alarm references.

## Project layout

| Path | Purpose |
|---|---|
| `src/network_expansion.py` | Sole data generator and physics model. |
| `src/export_formats.py` | Writes portable JSON and SQLite seed SQL from the generated tables. |
| `src/validate_sqlite.py` | Loads the SQL seed and runs SQLite joins, FK, and leakage checks. |
| `src/repro_network.py` | Generates twice and compares all output hashes and CSV counts. |
| `src/line_physics.py` | Reusable one-line steady-state hydraulic solver. |
| `data/` | Full generated CSVs, `seed.sql`, feature `export.json`, `ground_truth.json`, summary, and manifest; Git-ignored. |
| `sample-data/` | Checked-in starter-scale version of the same outputs. |
| `docs/` | Design rationale, data dictionary, assumptions, AI use, prompt history, dev log, and walkthrough outline. |
| `tests/` | Physics, topology, and deterministic generation tests. |
| `requirements.txt`, `LICENSE`, `.gitignore` | Dependency declaration, reuse license, and generated/temp-file exclusions. |

See [the data dictionary](docs/data_dictionary.md) for exported columns and relationships, and [the assumptions](docs/assumptions.md) for model details and limits.

For why the model and data boundaries were chosen, see [the design rationale](docs/DESIGN.md). AI assistance is described in [AI usage](docs/AI_USAGE.md), and the project prompts and demo script are summarized in [prompt history](docs/prompt_history/README.md) and the [walkthrough outline](docs/WALKTHROUGH.md).
