# AI use

I used Codex as a coding and documentation assistant while building this synthetic data generator. I supplied the project brief, selected the one-line prototype and the order of expansion, and reviewed the proposed model and dataset checks as the work progressed.

Codex helped implement and revise the Python generator, hydraulic tests, SQLite validation, exports, data dictionary, README, and this supporting documentation. I gave feedback on issues such as flow-balance interpretation, paired flow sensors, detectability under noise, alarm limitations, lifecycle coverage, bridge consistency, and reproducible output hashes. I then asked for those points to be checked against the generated artifacts.

The facilities, equipment, process values, scenarios, sensor readings, fault labels, and noise are generated synthetically by the repository code. No real plant data or third-party dataset was supplied to or used by the generator. AI assistance was not used to claim that the synthetic parameters are measured or calibrated. The validation and reproducibility results come from running the repository's code and tests.

The prompts that shaped the project are summarized in [prompt history](prompt_history/README.md). The design document records the engineering rationale and known limits.
