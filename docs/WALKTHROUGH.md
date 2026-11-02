# Project walkthrough (about 3 minutes)

1. **State the goal:** “This project generates a reproducible synthetic fluid-network dataset for testing fault analytics. It is not a calibrated digital twin.”
2. **Show the model:** open `src/line_physics.py` and `src/network_expansion.py`. Point out that faults change resistance, valve opening, or pump head before the solver calculates flow and pressure.
3. **Show the data boundary:** inspect `sample-data/telemetry.csv`, `sample-data/process_truth.csv`, and `sample-data/ground_truth.csv`. Explain that measured readings, solved process truth, and scenario labels are separate; the model feature export excludes truth tables.
4. **Show observability:** open `sample-data/sensors.csv` and `docs/data_dictionary.md`. Point to the inlet/outlet flow pair and pressure sensor positions around process restrictions.
5. **Show validation:** run `python src/validate_sqlite.py --data sample-data`, then `python -m unittest discover -s tests -v`. Point out the invalid `retired → active` fixture and event restoration checks.
6. **Show reproducibility and scale:** run `python src/repro_network.py --seed 20261022 --facilities 3 --pumps 20 --tanks 30 --valves 60 --telemetry-rows 100000`. State that `source_manifest.json` records hashes and that the same generator writes the full set to ignored `data/`.
7. **Close with limits:** mention the one-minute steady-state model, short run windows, assumed noise, reserve tanks, provisional thresholds, and the absence of an independent alarm benchmark.

Before recording or presenting, run the commands on the machine used for the demo and confirm the current summary values. This file is a rehearsal outline, not a recording of a completed presentation.
