import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.line_physics import TANK_AREA_M2
from src.what_if import run_what_if


class WhatIfTests(unittest.TestCase):
    def test_valve_change_writes_paired_runs_and_expected_deltas(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "what-if"
            summary = run_what_if(output, valve_opening=0.8, hours=24)

            with (output / "simulation_runs.csv").open(encoding="utf-8", newline="") as stream:
                runs = list(csv.DictReader(stream))
            with (output / "what_if_timeseries.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            persisted = json.loads((output / "summary.json").read_text(encoding="utf-8"))

            self.assertEqual(len(runs), 2)
            self.assertEqual(len(rows), 1440)
            self.assertEqual(summary, persisted)
            self.assertNotEqual(runs[0]["sim_run_id"], runs[1]["sim_run_id"])
            self.assertTrue(all(run["sim_run_id"].startswith("SIM-WIF-") for run in runs))
            self.assertTrue(all(json.loads(run["config_json"]) for run in runs))
            self.assertEqual(json.loads(runs[1]["config_json"])["line_parameters"]["valve_open"], 0.8)
            self.assertTrue(all(
                hashlib.sha256(run["config_json"].encode("utf-8")).hexdigest() == run["config_hash"]
                for run in runs
            ))
            self.assertLess(float(summary["mean_deltas"]["q_in_m3_h"]), 0.0)
            self.assertLess(float(summary["mean_deltas"]["q_out_m3_h"]), 0.0)
            self.assertAlmostEqual(float(rows[0]["delta_source_level_m"]), 0.0)
            self.assertAlmostEqual(float(rows[0]["delta_destination_level_m"]), 0.0)
            self.assertGreater(summary["end_level_deltas_m"]["source"], 0.0)
            self.assertLess(summary["end_level_deltas_m"]["destination"], 0.0)

    def test_end_level_delta_matches_integrated_volume_difference(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "what-if"
            summary = run_what_if(output, valve_opening=0.8, hours=24)
            with (output / "what_if_timeseries.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            for tank in ("source", "destination"):
                level_volume_m3 = summary["end_level_deltas_m"][tank] * TANK_AREA_M2
                self.assertAlmostEqual(level_volume_m3, summary["tank_volume_deltas_m3"][tank], places=8)
            last_step = rows[-1]
            step_hours = summary["step_seconds"] / 3600.0
            source_end_from_sample = float(last_step["delta_source_level_m"]) - (
                float(last_step["delta_q_in_m3_h"]) * step_hours / TANK_AREA_M2
            )
            destination_end_from_sample = float(last_step["delta_destination_level_m"]) + (
                float(last_step["delta_q_out_m3_h"]) * step_hours / TANK_AREA_M2
            )
            self.assertAlmostEqual(summary["end_level_deltas_m"]["source"], source_end_from_sample, places=8)
            self.assertAlmostEqual(summary["end_level_deltas_m"]["destination"], destination_end_from_sample, places=8)
            self.assertAlmostEqual(
                summary["mean_deltas"]["q_in_m3_h"] * summary["hours"],
                -summary["tank_volume_deltas_m3"]["source"],
                places=8,
            )

    def test_same_what_if_inputs_write_identical_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            left, right = root / "left", root / "right"
            run_what_if(left, valve_opening=0.8, hours=24)
            run_what_if(right, valve_opening=0.8, hours=24)
            for name in ("simulation_runs.csv", "what_if_timeseries.csv", "summary.json"):
                left_hash = hashlib.sha256((left / name).read_bytes()).hexdigest()
                right_hash = hashlib.sha256((right / name).read_bytes()).hexdigest()
                self.assertEqual(left_hash, right_hash)

    def test_rejects_out_of_range_valve_openings(self):
        with tempfile.TemporaryDirectory() as temp:
            for opening in (-0.1, 0.0, 1.01):
                with self.subTest(opening=opening), self.assertRaisesRegex(ValueError, "fully closed"):
                    run_what_if(Path(temp), valve_opening=opening, hours=1)


if __name__ == "__main__":
    unittest.main()
