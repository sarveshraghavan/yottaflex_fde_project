import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.network_expansion import FAULT_SCENARIOS, SCENARIOS, equipment, plan_exact_run_steps, topology_is_connected, write_network
from src.validate_sqlite import validate as validate_sqlite


class NetworkExpansionTests(unittest.TestCase):
    @staticmethod
    def read_csv(path):
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_shared_tanks_runs_sensor_fault_and_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = write_network(out, seed=123, facility_count=1, lines_per_facility=2, hours=1)
            lines, sensors, telemetry = (self.read_csv(out / name) for name in ("lines.csv", "sensors.csv", "telemetry.csv"))
            runs, truth, events = (self.read_csv(out / name) for name in ("simulation_runs.csv", "ground_truth.csv", "equipment_events.csv"))
            process_truth = self.read_csv(out / "process_truth.csv")
            alarms = self.read_csv(out / "alarms.csv")
            edge_cases = self.read_csv(out / "negative_fixtures.csv")
            boundaries = self.read_csv(out / "boundary_fixtures.csv")
            self.assertEqual(lines[0]["source_tank_id"], lines[1]["source_tank_id"])
            self.assertEqual(lines[0]["destination_tank_id"], lines[1]["destination_tank_id"])
            self.assertTrue(all(row["sim_run_id"] in {r["sim_run_id"] for r in runs} for row in telemetry))
            self.assertTrue(any(s["position"] == "inlet" and s["metric"] == "flow" for s in sensors))
            self.assertTrue(any(s["position"] == "outlet" and s["metric"] == "flow" for s in sensors))
            sensor_fault = next(row for row in truth if row["issue_type"] == "sensor_fault")
            self.assertEqual(sensor_fault["is_process_fault"], "false")
            self.assertIn("leak_coefficient_m3h_per_sqrt_m", json.loads(next(row for row in truth if row["issue_type"] == "leak")["fault_params_json"]))
            self.assertNotIn("scenario", json.loads(runs[0]["config_json"]))
            self.assertNotIn("issue_type", telemetry[0])
            self.assertNotIn("true_value", telemetry[0])
            self.assertNotIn("noise_sigma", telemetry[0])
            self.assertEqual(len(events), 12)  # Two diff-derived transitions for each of six fault runs.
            self.assertEqual(len(edge_cases), 5)
            self.assertTrue(all(r["validator_flagged"] == "true" for r in edge_cases))
            self.assertEqual(len(boundaries), 3)
            self.assertTrue(all(r["validator_passed"] == "true" for r in boundaries))
            self.assertEqual(summary["compound_fault_runs"], 1)
            self.assertEqual(summary["fault_free_run_count"], 5)
            self.assertEqual(summary["fault_run_count"], 6)
            self.assertEqual(summary["boundary_run_count"], 3)
            self.assertTrue(summary["all_boundary_tanks_within_capacity"])
            self.assertGreater(summary["pump_edge_mean_flow_fraction_of_available_runout"], 0.9)
            self.assertTrue(all(a["trigger_telemetry_id"] in {r["telemetry_id"] for r in telemetry} for a in alarms))
            self.assertEqual(len(process_truth), len(telemetry))
            self.assertTrue(summary["all_run_ids_on_telemetry"])
            self.assertTrue(summary["primary_keys_unique"])
            self.assertTrue(summary["foreign_keys_valid"])
            self.assertTrue(summary["pipe_node_references_valid"])
            self.assertTrue(summary["line_terminal_bridges_consistent"])
            self.assertTrue(summary["event_and_truth_run_ids_valid"])
            self.assertTrue(summary["all_negative_fixtures_flagged"])
            self.assertTrue(summary["all_boundary_fixtures_pass_range_checks"])
            self.assertTrue(summary["alarm_telemetry_references_valid"])
            self.assertEqual(summary["alarm_vs_detectable_on_labeled_windows"]["agreement_rate"], 1.0)
            self.assertLess(summary["max_true_network_residual_m3_h"], 1e-6)
            self.assertEqual(json.loads(runs[0]["config_json"])["noise_relative_sigma"]["flow"], 0.02)

    def test_target_topology_has_requested_scale_and_connected_facilities(self):
        facilities, tanks, pumps, valves, pipes, lines, sensors = equipment(3, 20, 30, 60)
        self.assertEqual([sum(1 for p in pumps if p["facility_id"] == f["facility_id"]) for f in facilities], [7, 7, 6])
        self.assertEqual([sum(1 for t in tanks if t["facility_id"] == f["facility_id"]) for f in facilities], [10, 10, 10])
        self.assertEqual(len(pumps), 20)
        self.assertEqual(len(valves), 60)
        self.assertEqual(len(lines), 20)
        self.assertEqual(len(sensors), 130)
        self.assertEqual(sensors[0]["sensor_id"], "SNS-001")
        self.assertTrue(all(len(s["sensor_id"]) == 7 and s["sensor_id"].startswith("SNS-") and s["sensor_id"][4:].isdigit() for s in sensors))
        for facility in facilities:
            local_valves = [v for v in valves if v["facility_id"] == facility["facility_id"]]
            self.assertEqual(len(local_valves), 20)
            self.assertTrue(topology_is_connected(facility["facility_id"], tanks, pumps, valves, pipes))

    def test_default_step_plan_hits_exact_rows_and_pairs_fault_windows(self):
        facilities, _, _, _, _, _, sensors = equipment(3, 20, 30, 60)
        plan = plan_exact_run_steps(100000, facilities, sensors)
        row_count = sum(sum(1 for s in sensors if s["facility_id"] == f["facility_id"]) * plan[(f["facility_id"], scenario)] for f in facilities for scenario in SCENARIOS)
        self.assertEqual(row_count, 100000)
        for facility in facilities:
            baseline_steps = plan[(facility["facility_id"], "baseline")]
            self.assertTrue(all(plan[(facility["facility_id"], scenario)] == baseline_steps for scenario in FAULT_SCENARIOS))
        self.assertLessEqual(max(plan.values()) - min(plan.values()), 2)

    def test_sql_seed_joins_and_feature_truth_exports_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_network(out, seed=20261022, telemetry_rows_target=10000)
            result = validate_sqlite(out)
            self.assertTrue(result["valid"])
            self.assertEqual(result["telemetry_rows"], 10000)
            self.assertEqual(result["invalid_polymorphic_pipe_nodes"], 0)
            self.assertEqual(result["invalid_sensor_id_formats"], 0)
            self.assertEqual(result["inconsistent_line_terminal_bridges"], 0)
            self.assertTrue(result["json_feature_export_has_no_truth_tables"])
            self.assertTrue(result["json_truth_export_is_separate"])

    def test_sensor_fault_changes_reading_without_changing_process_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_network(out, seed=7, facility_count=1, lines_per_facility=2, hours=1)
            telemetry = self.read_csv(out / "telemetry.csv")
            process_truth = self.read_csv(out / "process_truth.csv")
            base = {(r["sensor_id"], r["timestamp_utc"]): r for r in telemetry if r["sim_run_id"] == "SIM-2026-000001"}
            fault = {(r["sensor_id"], r["timestamp_utc"]): r for r in telemetry if r["sim_run_id"] == "SIM-2026-000010"}
            process_map = {r["telemetry_id"]: r for r in process_truth}
            faulty_sensor = next(row["entity_id"] for row in self.read_csv(out / "ground_truth.csv") if row["issue_type"] == "sensor_fault")
            sensor_rows = [r for r in fault.values() if r["sensor_id"] == faulty_sensor]
            self.assertTrue(all(r["quality_flag"] == "good" for r in sensor_rows))
            for key, row in fault.items():
                self.assertEqual(process_map[row["telemetry_id"]]["true_value"], process_map[base[key]["telemetry_id"]]["true_value"])
            self.assertEqual(len({r["value"] for r in sensor_rows}), 1)
            self.assertGreater(len({process_map[r["telemetry_id"]]["true_value"] for r in sensor_rows}), 1)

    def test_network_generation_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left, right = root / "left", root / "right"
            write_network(left, seed=99, facility_count=1, lines_per_facility=2, hours=1)
            write_network(right, seed=99, facility_count=1, lines_per_facility=2, hours=1)
            left_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in left.iterdir() if p.is_file()}
            right_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in right.iterdir() if p.is_file()}
            self.assertEqual(left_files, right_files)


if __name__ == "__main__":
    unittest.main()
