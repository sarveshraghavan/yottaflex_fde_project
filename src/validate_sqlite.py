"""Load the portable seed SQL into SQLite and run relational/leakage checks."""
import argparse
import json
import sqlite3
from pathlib import Path


def validate(data_dir: Path):
    seed_path = data_dir / "seed.sql"
    if not seed_path.exists():
        raise FileNotFoundError(f"Missing {seed_path}; generate the dataset first")
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(seed_path.read_text(encoding="utf-8"))
    checks = {}
    network_summary = json.loads((data_dir / "network_validation_summary.json").read_text(encoding="utf-8"))
    checks["foreign_key_violations"] = [list(row) for row in db.execute("PRAGMA foreign_key_check")]
    checks["telemetry_rows"] = db.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]
    checks["telemetry_sensor_run_mode_join_rows"] = db.execute("""
        SELECT COUNT(*) FROM telemetry t
        JOIN sensors s ON s.sensor_id=t.sensor_id
        JOIN simulation_runs r ON r.sim_run_id=t.sim_run_id
        JOIN facilities f ON f.facility_id=t.facility_id
        JOIN operating_modes m ON m.operating_mode_id=t.operating_mode_id
    """).fetchone()[0]
    checks["telemetry_truth_join_rows"] = db.execute("""
        SELECT COUNT(*) FROM telemetry t JOIN process_truth p ON p.telemetry_id=t.telemetry_id
    """).fetchone()[0]
    checks["ground_truth_run_evidence_join_rows"] = db.execute("""
        SELECT COUNT(*) FROM ground_truth g
        JOIN simulation_runs r ON r.sim_run_id=g.sim_run_id
        JOIN telemetry t ON t.telemetry_id=g.evidence_telemetry_id
        JOIN sensors s ON s.sensor_id=g.evidence_sensor_id
    """).fetchone()[0]
    checks["alarm_trigger_join_rows"] = db.execute("""
        SELECT COUNT(*) FROM alarms a JOIN telemetry t ON t.telemetry_id=a.trigger_telemetry_id
    """).fetchone()[0]
    checks["valve_mode_bridge_join_rows"] = db.execute("""
        SELECT COUNT(*) FROM valve_mode_states v JOIN valves x ON x.valve_id=v.valve_id
        JOIN operating_modes m ON m.operating_mode_id=v.operating_mode_id
    """).fetchone()[0]
    checks["line_valve_bridge_rows"] = db.execute("SELECT COUNT(*) FROM line_valves").fetchone()[0]
    checks["expected_telemetry_rows"] = network_summary["telemetry_rows_target"]
    checks["exact_telemetry_target"] = checks["telemetry_rows"] == checks["expected_telemetry_rows"] and network_summary["telemetry_rows_exact"]
    telemetry_columns = {row[1] for row in db.execute("PRAGMA table_info(telemetry)")}
    forbidden_telemetry = {"true_value", "noise_added", "noise_sigma", "issue_type", "fault_params_json", "is_process_fault"}
    checks["telemetry_has_no_truth_or_fault_columns"] = not bool(telemetry_columns & forbidden_telemetry)
    config_rows = db.execute("SELECT config_json FROM simulation_runs").fetchall()
    forbidden_config = {"scenario", "fault_schedule", "fault_type", "issue_type", "fault_params", "fault_params_json"}
    checks["config_has_no_fault_schedule"] = all(not (forbidden_config & set(json.loads(row[0]).keys())) for row in config_rows)
    feature_export = json.loads((data_dir / "export.json").read_text(encoding="utf-8"))
    truth_export = json.loads((data_dir / "ground_truth.json").read_text(encoding="utf-8"))
    feature_tables = set(feature_export["tables"])
    truth_tables = set(truth_export["tables"])
    checks["json_feature_export_has_no_truth_tables"] = not bool(feature_tables & {"ground_truth", "process_truth", "network_balance", "alarms", "equipment_events"})
    checks["json_truth_export_is_separate"] = {"ground_truth", "process_truth"}.issubset(truth_tables)
    checks["all_expected_joins_complete"] = all(
        checks[key] == checks["telemetry_rows"] for key in (
            "telemetry_sensor_run_mode_join_rows", "telemetry_truth_join_rows"
        )
    ) and checks["ground_truth_run_evidence_join_rows"] == db.execute("SELECT COUNT(*) FROM ground_truth").fetchone()[0] and checks["alarm_trigger_join_rows"] == db.execute("SELECT COUNT(*) FROM alarms").fetchone()[0]
    checks["valid"] = not checks["foreign_key_violations"] and checks["exact_telemetry_target"] and checks["telemetry_has_no_truth_or_fault_columns"] and checks["config_has_no_fault_schedule"] and checks["json_feature_export_has_no_truth_tables"] and checks["json_truth_export_is_separate"] and checks["all_expected_joins_complete"]
    db.close()
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    args = parser.parse_args()
    result = validate(args.data)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
