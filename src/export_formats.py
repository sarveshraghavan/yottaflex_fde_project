"""Create portable JSON and SQLite seed exports from the generated CSV tables."""
import csv
import json
from pathlib import Path

TABLE_ORDER = [
    "facilities", "operating_modes", "tanks", "lines", "pumps", "valves", "pipes",
    "line_valves", "line_pipes", "sensors", "valve_mode_states", "simulation_runs",
    "telemetry", "process_truth", "ground_truth", "equipment_events", "alarms",
    "network_balance", "fault_location_rules", "negative_fixtures", "boundary_fixtures",
]
FEATURE_TABLES = {
    "facilities", "operating_modes", "tanks", "lines", "pumps", "valves", "pipes",
    "line_valves", "line_pipes", "sensors", "valve_mode_states", "simulation_runs", "telemetry",
}
TRUTH_TABLES = {
    "process_truth", "ground_truth", "equipment_events", "alarms", "network_balance",
    "fault_location_rules", "negative_fixtures", "boundary_fixtures",
}
PRIMARY_KEYS = {
    "facilities": ["facility_id"], "operating_modes": ["operating_mode_id"],
    "tanks": ["tank_id"], "lines": ["line_id"], "pumps": ["pump_id"],
    "valves": ["valve_id"], "pipes": ["pipe_id"],
    "line_valves": ["line_id", "valve_id"], "line_pipes": ["line_id", "pipe_id"],
    "sensors": ["sensor_id"], "valve_mode_states": ["valve_id", "operating_mode_id", "effective_from_utc"],
    "simulation_runs": ["sim_run_id"], "telemetry": ["telemetry_id"],
    "process_truth": ["telemetry_id"], "ground_truth": ["scenario_id"],
    "equipment_events": ["event_id"], "alarms": ["alarm_id"],
    "network_balance": ["timestamp_utc", "sim_run_id", "facility_id"],
    "negative_fixtures": ["case_id"], "boundary_fixtures": ["boundary_id"],
}
FOREIGN_KEYS = {
    "tanks": [("facility_id", "facilities", "facility_id")],
    "lines": [("facility_id", "facilities", "facility_id"), ("source_tank_id", "tanks", "tank_id"), ("destination_tank_id", "tanks", "tank_id"), ("pump_id", "pumps", "pump_id"), ("valve_id", "valves", "valve_id"), ("pipe_id", "pipes", "pipe_id")],
    "pumps": [("facility_id", "facilities", "facility_id"), ("line_id", "lines", "line_id")],
    "valves": [("facility_id", "facilities", "facility_id"), ("line_id", "lines", "line_id")],
    "pipes": [("facility_id", "facilities", "facility_id"), ("line_id", "lines", "line_id")],
    "line_valves": [("line_id", "lines", "line_id"), ("valve_id", "valves", "valve_id")],
    "line_pipes": [("line_id", "lines", "line_id"), ("pipe_id", "pipes", "pipe_id")],
    "sensors": [("facility_id", "facilities", "facility_id"), ("line_id", "lines", "line_id"), ("pipe_id", "pipes", "pipe_id")],
    "valve_mode_states": [("valve_id", "valves", "valve_id"), ("operating_mode_id", "operating_modes", "operating_mode_id")],
    "simulation_runs": [("facility_id", "facilities", "facility_id")],
    "telemetry": [("sim_run_id", "simulation_runs", "sim_run_id"), ("operating_mode_id", "operating_modes", "operating_mode_id"), ("facility_id", "facilities", "facility_id"), ("line_id", "lines", "line_id"), ("sensor_id", "sensors", "sensor_id")],
    "process_truth": [("telemetry_id", "telemetry", "telemetry_id"), ("sim_run_id", "simulation_runs", "sim_run_id"), ("sensor_id", "sensors", "sensor_id")],
    "ground_truth": [("sim_run_id", "simulation_runs", "sim_run_id"), ("evidence_sensor_id", "sensors", "sensor_id"), ("evidence_telemetry_id", "telemetry", "telemetry_id")],
    "equipment_events": [("sim_run_id", "simulation_runs", "sim_run_id"), ("cause_scenario_id", "ground_truth", "scenario_id")],
    "alarms": [("sim_run_id", "simulation_runs", "sim_run_id"), ("facility_id", "facilities", "facility_id"), ("line_id", "lines", "line_id"), ("trigger_telemetry_id", "telemetry", "telemetry_id")],
    "network_balance": [("sim_run_id", "simulation_runs", "sim_run_id"), ("facility_id", "facilities", "facility_id")],
}
INTEGER_COLUMNS = {"sequence_order", "seed", "sample_count", "detectability_sigma"}
REAL_COLUMNS = {"capacity_m3", "area_m2", "initial_volume_m3", "nominal_flow_m3_h", "shutoff_head_m", "pump_curve_a", "normal_opening_pct", "resistance_k", "value", "true_value", "noise_added", "noise_sigma", "effect_abs", "effect_relative", "true_effect_abs", "measured_effect_abs", "noise_sigma_single_sample", "noise_sigma_window", "window_effect_abs", "lower_limit", "upper_limit", "residual_m3_h", "tolerance_m3_h", "level_pct", "maximum_pct", "flow_fraction_of_runout", "q_in_true_m3_h", "q_out_true_m3_h", "q_leak_true_m3_h", "storage_rate_m3_h", "source_level_m", "destination_level_m", "true_supply_minus_leak_minus_storage_m3_h", "measured_supply_minus_leak_minus_storage_m3_h"}
REQUIRED_COLUMNS = {
    "facilities": {"facility_id", "name", "lifecycle_state"},
    "operating_modes": {"operating_mode_id", "name", "description", "effective_from_utc"},
    "tanks": {"tank_id", "facility_id", "tank_role", "capacity_m3", "area_m2", "initial_volume_m3", "lifecycle_state"},
    "lines": {"line_id", "facility_id", "source_tank_id", "destination_tank_id", "pump_id", "valve_id", "pipe_id"},
    "pumps": {"pump_id", "facility_id", "line_id", "nominal_flow_m3_h", "shutoff_head_m", "lifecycle_state"},
    "valves": {"valve_id", "facility_id", "line_id", "normal_opening_pct", "sequence_order", "resistance_k", "lifecycle_state"},
    "pipes": {"pipe_id", "facility_id", "from_node_id", "to_node_id", "resistance_k", "edge_role", "lifecycle_state"},
    "line_valves": {"line_id", "valve_id", "sequence_order"}, "line_pipes": {"line_id", "pipe_id", "sequence_order"},
    "sensors": {"sensor_id", "facility_id", "entity_type", "position", "metric", "unit"},
    "valve_mode_states": {"valve_id", "operating_mode_id", "state", "effective_from_utc"},
    "simulation_runs": {"sim_run_id", "facility_id", "seed", "config_hash", "config_json", "started_at_utc", "status"},
    "telemetry": {"telemetry_id", "timestamp_utc", "sim_run_id", "operating_mode_id", "facility_id", "sensor_id", "position", "metric", "value", "unit", "quality_flag"},
    "process_truth": {"telemetry_id", "timestamp_utc", "sim_run_id", "sensor_id", "true_value", "noise_added", "noise_sigma"},
    "ground_truth": {"scenario_id", "sim_run_id", "issue_type", "entity_id", "start_ts", "end_ts", "is_process_fault", "fault_params_json", "primary_signal", "evidence_sensor_id", "evidence_telemetry_id", "effect_abs", "effect_relative", "true_effect_abs", "measured_effect_abs", "noise_sigma_single_sample", "noise_sigma_window", "sample_count", "detectability_sigma", "detectability_rule", "detectable", "alarm_detected", "expected_sign_by_location_json"},
    "equipment_events": {"event_id", "event_ts", "entity_type", "entity_id", "event_type", "from_state", "to_state", "sim_run_id", "cause_scenario_id"},
    "alarms": {"alarm_id", "timestamp_utc", "sim_run_id", "facility_id", "alarm_type", "primary_signal", "trigger_telemetry_id", "window_effect_abs", "noise_sigma_window", "detector_rule", "status"},
    "network_balance": {"timestamp_utc", "sim_run_id", "facility_id", "true_supply_minus_leak_minus_storage_m3_h", "measured_supply_minus_leak_minus_storage_m3_h", "q_in_true_m3_h", "q_out_true_m3_h", "q_leak_true_m3_h", "storage_rate_m3_h", "source_level_m", "destination_level_m"},
    "fault_location_rules": {"issue_type", "location", "signal", "expected_sign", "meaning"},
    "negative_fixtures": {"case_id", "case", "entity", "observed", "ground_truth_issue", "is_process_fault", "validator_rule", "validator_flagged"},
    "boundary_fixtures": {"boundary_id", "case", "metric", "value", "unit", "lower_limit", "upper_limit", "expected_validator_result", "scenario_coverage", "validator_passed"},
}
UNIQUE_COLUMNS = {
    "valves": [("line_id", "sequence_order")],
    "pipes": [("line_id", "sequence_order")],
    "line_valves": [("line_id", "sequence_order")],
    "line_pipes": [("line_id", "sequence_order")],
}
ENUM_CHECKS = {
    "lifecycle_state": ("planned", "active", "maintenance", "out_of_service", "retired"),
}
COLUMN_CHECKS = {
    ("sensors", "sensor_id"): "substr(\"sensor_id\",1,4)='SNS-' AND length(\"sensor_id\")>=7 AND substr(\"sensor_id\",5) NOT GLOB '*[^0-9]*'",
}


def quote(value):
    if value is None or value == "":
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def sql_type(column):
    if column in INTEGER_COLUMNS:
        return "INTEGER"
    if column in REAL_COLUMNS:
        return "REAL"
    return "TEXT"


def read_tables(out):
    tables = {}
    for name in TABLE_ORDER:
        path = out / f"{name}.csv"
        if path.exists():
            with path.open(encoding="utf-8", newline="") as handle:
                tables[name] = list(csv.DictReader(handle))
    return tables


def typed_value(column, value):
    if value == "":
        return None
    if column.endswith("_json") or column == "config_json":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if column in INTEGER_COLUMNS:
        try:
            return int(value)
        except ValueError:
            return value
    if column in REAL_COLUMNS:
        try:
            return float(value)
        except ValueError:
            return value
    return value


def build_exports(out: Path, seed: int, command: str, summary: dict):
    tables = read_tables(out)
    ddl = ["PRAGMA foreign_keys = ON;", "PRAGMA defer_foreign_keys = ON;", "BEGIN TRANSACTION;"]
    inserts = []
    for name, rows in tables.items():
        columns = list(rows[0]) if rows else []
        if not columns:
            continue
        definitions = [f'"{column}" {sql_type(column)}' + (" NOT NULL" if column in REQUIRED_COLUMNS.get(name, set()) else "") for column in columns]
        for column in columns:
            if column in ENUM_CHECKS:
                allowed = ", ".join(quote(value) for value in ENUM_CHECKS[column])
                definitions.append(f'CHECK ("{column}" IN ({allowed}))')
            if (name, column) in COLUMN_CHECKS:
                definitions.append(f'CHECK ({COLUMN_CHECKS[(name, column)]})')
        keys = PRIMARY_KEYS.get(name, [])
        if keys:
            definitions.append("PRIMARY KEY (" + ", ".join(f'"{key}"' for key in keys) + ")")
        for column, parent, parent_key in FOREIGN_KEYS.get(name, []):
            if column in columns:
                definitions.append(f'FOREIGN KEY ("{column}") REFERENCES "{parent}" ("{parent_key}")')
        for unique_columns in UNIQUE_COLUMNS.get(name, []):
            definitions.append("UNIQUE (" + ", ".join(f'"{column}"' for column in unique_columns) + ")")
        ddl.append(f'CREATE TABLE "{name}" (\n  ' + ",\n  ".join(definitions) + "\n);")
        col_sql = ", ".join(f'"{column}"' for column in columns)
        for row in rows:
            values = ", ".join(quote(row.get(column)) for column in columns)
            inserts.append(f'INSERT INTO "{name}" ({col_sql}) VALUES ({values});')
    seed_sql = "\n".join(ddl + inserts + ["COMMIT;", ""])
    (out / "seed.sql").write_text(seed_sql, encoding="utf-8", newline="\n")
    def compact_tables(names):
        result = {}
        for name in TABLE_ORDER:
            if name not in names or name not in tables:
                continue
            rows = tables[name]
            columns = list(rows[0]) if rows else []
            result[name] = {
                "columns": columns,
                "rows": [[typed_value(column, row[column]) for column in columns] for row in rows],
            }
        return result

    metadata = {"provenance": "All values are synthetic; no external operational data was used.", "seed": seed, "generator_command": command}
    feature_payload = {"metadata": metadata, "tables": compact_tables(FEATURE_TABLES)}
    truth_payload = {"metadata": metadata, "tables": compact_tables(TRUTH_TABLES), "network_validation_summary": summary}
    (out / "export.json").write_text(json.dumps(feature_payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (out / "ground_truth.json").write_text(json.dumps(truth_payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
