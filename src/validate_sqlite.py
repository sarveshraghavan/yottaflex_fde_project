"""Load the portable seed SQL into SQLite and run relational/leakage checks."""
import argparse
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

try:
    from src.network_expansion import equipment_event_checks, lifecycle_transition_allowed
except ModuleNotFoundError:
    from network_expansion import equipment_event_checks, lifecycle_transition_allowed


def validate(data_dir: Path):
    seed_path = data_dir / "seed.sql"
    if not seed_path.exists():
        raise FileNotFoundError(f"Missing {seed_path}; generate the dataset first")
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
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
    checks["invalid_sensor_id_formats"] = db.execute("""
        SELECT COUNT(*) FROM sensors
        WHERE substr(sensor_id, 1, 4) != 'SNS-' OR length(sensor_id) < 7 OR substr(sensor_id, 5) GLOB '*[^0-9]*'
    """).fetchone()[0]
    checks["inconsistent_line_terminal_bridges"] = db.execute("""
        SELECT COUNT(*) FROM lines l
        WHERE l.valve_id != (SELECT v.valve_id FROM line_valves v WHERE v.line_id=l.line_id ORDER BY v.sequence_order DESC LIMIT 1)
           OR l.pipe_id != (SELECT p.pipe_id FROM line_pipes p WHERE p.line_id=l.line_id ORDER BY p.sequence_order DESC LIMIT 1)
    """).fetchone()[0]
    checks["orphan_line_valve_bridges"] = db.execute("SELECT COUNT(*) FROM line_valves b LEFT JOIN lines l ON l.line_id=b.line_id WHERE l.line_id IS NULL").fetchone()[0]
    checks["orphan_line_pipe_bridges"] = db.execute("SELECT COUNT(*) FROM line_pipes b LEFT JOIN lines l ON l.line_id=b.line_id WHERE l.line_id IS NULL").fetchone()[0]
    checks["unbridged_line_valves"] = db.execute("SELECT COUNT(*) FROM line_valves b LEFT JOIN valves v ON v.valve_id=b.valve_id WHERE v.valve_id IS NULL").fetchone()[0]
    checks["unbridged_line_pipes"] = db.execute("SELECT COUNT(*) FROM line_pipes b LEFT JOIN pipes p ON p.pipe_id=b.pipe_id WHERE p.pipe_id IS NULL").fetchone()[0]
    checks["invalid_polymorphic_pipe_nodes"] = db.execute("""
        WITH equipment_nodes(node_id, facility_id) AS (
            SELECT tank_id, facility_id FROM tanks
            UNION ALL SELECT pump_id, facility_id FROM pumps
            UNION ALL SELECT valve_id, facility_id FROM valves
        )
        SELECT COUNT(*) FROM pipes p
        LEFT JOIN equipment_nodes src ON src.node_id=p.from_node_id AND src.facility_id=p.facility_id
        LEFT JOIN equipment_nodes dst ON dst.node_id=p.to_node_id AND dst.facility_id=p.facility_id
        WHERE src.node_id IS NULL OR dst.node_id IS NULL OR p.from_node_id=p.to_node_id
    """).fetchone()[0]
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
    events = [{key: row[key] for key in ("event_id", "event_ts", "entity_type", "entity_id", "event_type", "from_state", "to_state", "sim_run_id", "cause_scenario_id")} for row in db.execute("SELECT event_id,event_ts,entity_type,entity_id,event_type,from_state,to_state,sim_run_id,cause_scenario_id FROM equipment_events")]
    run_end_by_id = {}
    for sim_run_id, started_at, config_json in db.execute("SELECT sim_run_id,started_at_utc,config_json FROM simulation_runs"):
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        run_end_by_id[sim_run_id] = (started + timedelta(hours=json.loads(config_json)["hours"])).isoformat().replace("+00:00", "Z")
    event_checks = equipment_event_checks(events, run_end_by_id)
    checks["equipment_event_transitions_valid"] = event_checks["transitions_valid"]
    checks["equipment_event_chains_valid"] = event_checks["chains_valid"]
    checks["equipment_fault_events_restored"] = event_checks["fault_events_restored"]
    lifecycle_fixture = db.execute("SELECT observed,validator_flagged FROM negative_fixtures WHERE case_id='EDGE-006' AND validator_rule='allowed_lifecycle_transition'").fetchone()
    checks["invalid_lifecycle_transition_fixture_flagged"] = bool(lifecycle_fixture and lifecycle_fixture["validator_flagged"] == "true" and not lifecycle_transition_allowed(*[part.split("=", 1)[1] for part in lifecycle_fixture["observed"].split("; ")]))
    checks["all_expected_joins_complete"] = all(
        checks[key] == checks["telemetry_rows"] for key in (
            "telemetry_sensor_run_mode_join_rows", "telemetry_truth_join_rows"
        )
    ) and checks["ground_truth_run_evidence_join_rows"] == db.execute("SELECT COUNT(*) FROM ground_truth").fetchone()[0] and checks["alarm_trigger_join_rows"] == db.execute("SELECT COUNT(*) FROM alarms").fetchone()[0]
    checks["valid"] = not checks["foreign_key_violations"] and checks["invalid_polymorphic_pipe_nodes"] == 0 and checks["invalid_sensor_id_formats"] == 0 and checks["inconsistent_line_terminal_bridges"] == 0 and checks["orphan_line_valve_bridges"] == 0 and checks["orphan_line_pipe_bridges"] == 0 and checks["unbridged_line_valves"] == 0 and checks["unbridged_line_pipes"] == 0 and checks["equipment_event_transitions_valid"] and checks["equipment_event_chains_valid"] and checks["equipment_fault_events_restored"] and checks["invalid_lifecycle_transition_fixture_flagged"] and checks["exact_telemetry_target"] and checks["telemetry_has_no_truth_or_fault_columns"] and checks["config_has_no_fault_schedule"] and checks["json_feature_export_has_no_truth_tables"] and checks["json_truth_export_is_separate"] and checks["all_expected_joins_complete"]
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
