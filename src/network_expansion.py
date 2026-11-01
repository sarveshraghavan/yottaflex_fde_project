"""Small multi-line network generator built on the one-line solver."""
import argparse
import csv
import json
import math
import random
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # Support both `python src/network_expansion.py` and package imports.
    from src.line_physics import Line, Tank, solve_line
    from src.export_formats import build_exports
except ModuleNotFoundError:
    from line_physics import Line, Tank, solve_line
    from export_formats import build_exports

SCENARIOS = ("baseline", "baseline_repeat", "boundary_tank_low", "boundary_tank_high", "boundary_pump_edge", "leak", "blockage", "pump_degradation", "valve_partial", "sensor_fault", "compound_fault")
FAULT_SCENARIOS = ("leak", "blockage", "pump_degradation", "valve_partial", "sensor_fault", "compound_fault")
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOISE_RELATIVE_SIGMA = {"flow": 0.02, "pressure": 0.01, "level": 0.005}
DETECTABILITY_SIGMA = 3.0


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: (f"{value:.8f}" if isinstance(value, float) else value) for key, value in row.items()} for row in rows)


def stable_values(value, places=8):
    if isinstance(value, float):
        return round(value, places)
    if isinstance(value, dict):
        return {k: stable_values(v, places) for k, v in value.items()}
    if isinstance(value, list):
        return [stable_values(v, places) for v in value]
    return value


def window_detection_threshold(noise_sigma_single_sample, sample_count):
    """Shared 3-sigma threshold for a mean signal over a labeled run window."""
    return DETECTABILITY_SIGMA * noise_sigma_single_sample / math.sqrt(max(1, sample_count))


def fid(i): return f"FAC-{i:03d}"
def tid(i): return f"TANK-{i:03d}"
def pid(i): return f"PUMP-{i:03d}"
def vid(i): return f"VALVE-{i:03d}"
def pipeid(i): return f"PIPE-{i:03d}"
def lineid(i): return f"LINE-{i:03d}"


def distribute(total, groups):
    return [total // groups + (1 if i < total % groups else 0) for i in range(groups)]


def plan_exact_run_steps(target_rows, facilities, sensors):
    """Allocate whole samples to runs for an exact row target, preserving paired fault windows."""
    weights = {f["facility_id"]: sum(1 for s in sensors if s["facility_id"] == f["facility_id"]) for f in facilities}
    total_per_step = len(SCENARIOS) * sum(weights.values())
    base_steps = target_rows // total_per_step
    if base_steps < 1:
        raise ValueError(f"telemetry target must be at least {total_per_step} rows")
    remainder = target_rows - base_steps * total_per_step
    # Each baseline/fault set moves together; repeat and boundary runs are independently adjustable.
    variables = []
    for facility in facilities:
        weight = weights[facility["facility_id"]]
        for scenario in ("baseline_repeat", "boundary_tank_low", "boundary_tank_high", "boundary_pump_edge"):
            variables.append((weight, facility["facility_id"], scenario))
        variables.append((weight * (1 + len(FAULT_SCENARIOS)), facility["facility_id"], "_paired_group"))
    allocation = None
    max_possible = remainder // min(v[0] for v in variables)
    # Minimize the largest run-length adjustment; this keeps the default horizons within a few minutes.
    for max_extra in range(max_possible + 1):
        ways = {0: []}
        for row_weight, facility_id, scenario in variables:
            updated = {}
            for prior, counts in ways.items():
                for count in range(min(max_extra, (remainder - prior) // row_weight) + 1):
                    total = prior + count * row_weight
                    if total not in updated:
                        updated[total] = counts + [count]
            ways = updated
        if remainder in ways:
            allocation = ways[remainder]
            break
    if allocation is None:
        raise ValueError(f"cannot reach exactly {target_rows} rows with whole samples and paired fault windows; choose another target or --time-steps")
    steps = {(f["facility_id"], scenario): base_steps for f in facilities for scenario in SCENARIOS}
    for (_, facility_id, scenario), count in zip(variables, allocation):
        if scenario == "_paired_group":
            for paired_scenario in ("baseline",) + FAULT_SCENARIOS:
                steps[(facility_id, paired_scenario)] += count
        else:
            steps[(facility_id, scenario)] += count
    return steps


def topology_is_connected(facility_id, tanks, pumps, valves, pipes):
    nodes = {r["tank_id"] for r in tanks if r["facility_id"] == facility_id}
    nodes |= {r["pump_id"] for r in pumps if r["facility_id"] == facility_id}
    nodes |= {r["valve_id"] for r in valves if r["facility_id"] == facility_id}
    adjacency = {node: set() for node in nodes}
    for edge in pipes:
        if edge["facility_id"] == facility_id:
            adjacency[edge["from_node_id"]].add(edge["to_node_id"])
            adjacency[edge["to_node_id"]].add(edge["from_node_id"])
    if not nodes or not pipe_node_references_valid(tanks, pumps, valves, pipes):
        return False
    reached, todo = set(), [next(iter(nodes))]
    while todo:
        node = todo.pop()
        if node in reached:
            continue
        reached.add(node)
        todo.extend(adjacency[node] - reached)
    return reached == nodes


def pipe_node_references_valid(tanks, pumps, valves, pipes):
    """Validate polymorphic pipe endpoints against this facility's tank/pump/valve IDs."""
    node_facility = {}
    for rows, id_column in ((tanks, "tank_id"), (pumps, "pump_id"), (valves, "valve_id")):
        node_facility.update({row[id_column]: row["facility_id"] for row in rows})
    return all(
        edge["from_node_id"] in node_facility
        and edge["to_node_id"] in node_facility
        and node_facility[edge["from_node_id"]] == edge["facility_id"]
        and node_facility[edge["to_node_id"]] == edge["facility_id"]
        for edge in pipes
    )


def equipment(facility_count, pump_count, tank_count, valve_count):
    """Build a connected manifold topology with one pump and series valve train per line."""
    if pump_count < facility_count or tank_count < 2 * facility_count:
        raise ValueError("Need at least one pump and two tanks per facility")
    if valve_count < pump_count:
        raise ValueError("Need at least one valve per pump line")
    facilities, tanks, pumps, valves, pipes, lines, sensors = [], [], [], [], [], [], []
    line_valves, line_pipes = [], []
    sensor_n = line_n = pump_n = valve_n = pipe_n = tank_n = 0
    pump_counts = distribute(pump_count, facility_count)
    tank_counts = distribute(tank_count, facility_count)
    valve_counts = distribute(valve_count, facility_count)
    for fidx, fno in enumerate(range(1, facility_count + 1)):
        facility_id = fid(fno)
        facilities.append({"facility_id": facility_id, "name": f"Facility {fno}", "lifecycle_state": "active"})
        local_tanks = []
        for local in range(tank_counts[fidx]):
            tank_n += 1
            tank_id = tid(tank_n)
            role = "shared_source" if local == 0 else ("shared_destination" if local == 1 else "buffer")
            volume = 60000 if local == 0 else (56000 if local == 1 else 50000)
            tanks.append({"tank_id": tank_id, "facility_id": facility_id, "tank_role": role, "capacity_m3": 100000, "area_m2": 2000, "initial_volume_m3": volume, "lifecycle_state": "active"})
            local_tanks.append(tank_id)
        source_id, destination_id = local_tanks[:2]
        # Buffer tanks attach to the destination manifold, keeping the facility graph connected.
        for before, after in zip(local_tanks[1:], local_tanks[2:]):
            pipe_n += 1
            pipes.append({"pipe_id": pipeid(pipe_n), "facility_id": facility_id, "line_id": "", "from_node_id": before, "to_node_id": after, "resistance_k": 0.01, "edge_role": "buffer_manifold", "lifecycle_state": "active"})
        local_valves_per_line = distribute(valve_counts[fidx], pump_counts[fidx])
        for local_pump_index in range(pump_counts[fidx]):
            valves_per_line = local_valves_per_line[local_pump_index]
            line_n += 1; pump_n += 1
            this_line, pump_id = lineid(line_n), pid(pump_n)
            pumps.append({"pump_id": pump_id, "facility_id": facility_id, "line_id": this_line, "nominal_flow_m3_h": 130, "shutoff_head_m": 50, "pump_curve_a": 0.0015, "lifecycle_state": "active"})
            node_path = [source_id, pump_id]
            train = []
            for sequence in range(1, valves_per_line + 1):
                valve_n += 1
                valve_id = vid(valve_n)
                train.append(valve_id); node_path.append(valve_id)
                valves.append({"valve_id": valve_id, "facility_id": facility_id, "line_id": this_line, "normal_opening_pct": 100, "sequence_order": sequence, "resistance_k": 0.0005 / valves_per_line, "lifecycle_state": "active"})
                line_valves.append({"line_id": this_line, "valve_id": valve_id, "sequence_order": sequence})
            node_path.append(destination_id)
            line_pipe_ids = []
            pipe_resistance = 0.001 / (len(node_path) - 1)
            for sequence, (from_node, to_node) in enumerate(zip(node_path, node_path[1:]), 1):
                pipe_n += 1; pipe_id = pipeid(pipe_n); line_pipe_ids.append(pipe_id)
                pipes.append({"pipe_id": pipe_id, "facility_id": facility_id, "line_id": this_line, "from_node_id": from_node, "to_node_id": to_node, "resistance_k": pipe_resistance, "edge_role": "line_segment", "sequence_order": sequence, "lifecycle_state": "active"})
                line_pipes.append({"line_id": this_line, "pipe_id": pipe_id, "sequence_order": sequence})
            lines.append({"line_id": this_line, "facility_id": facility_id, "source_tank_id": source_id, "destination_tank_id": destination_id, "pump_id": pump_id, "first_valve_id": train[0], "last_valve_id": train[-1], "outlet_pipe_id": line_pipe_ids[-1], "valve_id": train[-1], "pipe_id": line_pipe_ids[-1], "valves_per_line": valves_per_line})
            locations = [
                ("flow", "pump", "inlet", pump_id, ""), ("flow", "pipe", "outlet", "", line_pipe_ids[-1]),
                ("pressure", "pump", "discharge", pump_id, ""), ("pressure", "valve_train", "valve_train_outlet", train[-1], ""),
                ("pressure", "pipe", "pipe_outlet", "", line_pipe_ids[-1]),
            ]
            for metric, entity_type, position, entity_id, pipe_id in locations:
                sensor_n += 1
                sensors.append({"sensor_id": f"SNS-{sensor_n:03d}", "facility_id": facility_id, "line_id": this_line, "entity_type": entity_type, "entity_id": entity_id, "node_id": entity_id if entity_id else "", "pipe_id": pipe_id, "position": position, "metric": metric, "unit": "m3/h" if metric == "flow" else "kPa"})
        for tank_id in local_tanks:
            sensor_n += 1
            tank = next(t for t in tanks if t["tank_id"] == tank_id)
            sensors.append({"sensor_id": f"SNS-{sensor_n:03d}", "facility_id": facility_id, "line_id": "", "entity_type": "tank", "entity_id": tank_id, "node_id": tank_id, "pipe_id": "", "position": "level", "metric": "level", "unit": "m", "initial_level_m": 50.0 * tank["initial_volume_m3"] / tank["capacity_m3"]})
    return facilities, tanks, pumps, valves, pipes, lines, sensors


def configured_line(scenario, valves_per_line=1):
    line = Line()
    if scenario == "boundary_pump_edge":
        return replace(line, pipe_k_m_per_m3h2=0.00001, valve_k_m_per_m3h2=0.00001)
    if scenario == "leak":
        return replace(line, leak_cl_m3h_per_sqrt_m=5.0, leak_pos=0.5)
    if scenario == "blockage":
        return replace(line, pipe_k_m_per_m3h2=line.pipe_k_m_per_m3h2 * 3.0)
    if scenario == "pump_degradation":
        return replace(line, h0_m=line.h0_m * 0.90)
    if scenario == "valve_partial":
        # One valve in a series train is throttled; preserve the summed resistance.
        total_resistance_factor = (valves_per_line - 1 + 1 / (0.65 ** 2)) / valves_per_line
        return replace(line, valve_open=1 / math.sqrt(total_resistance_factor))
    if scenario == "compound_fault":
        return replace(line, leak_cl_m3h_per_sqrt_m=5.0, leak_pos=0.5, pipe_k_m_per_m3h2=line.pipe_k_m_per_m3h2 * 3.0)
    return line


def simulate_run(facility, facility_lines, sensors, run_id, scenario, seed, time_steps, step_seconds):
    """Advance parallel lines that share source/destination tank storage."""
    source_volume = 5000 if scenario == "boundary_tank_low" else 60000
    destination_volume = 95000 if scenario == "boundary_tank_high" else (64000 if scenario == "boundary_pump_edge" else 56000)
    source = Tank(100000, 2000, 0, source_volume)
    destination = Tank(100000, 2000, 0, destination_volume)
    by_line = {ln["line_id"]: [s for s in sensors if s["line_id"] == ln["line_id"]] for ln in facility_lines}
    rng = random.Random(seed)  # reset for paired runs: same sensor/time gets common noise
    telemetry, process_truth, balances, states = [], [], [], []
    point_no = 0
    dt_h = step_seconds / 3600
    for step in range(int(time_steps)):
        step_rows = []
        timestamp = (START + timedelta(seconds=step * step_seconds)).isoformat().replace("+00:00", "Z")
        source_head, destination_head = source.head_m, destination.head_m
        line_results, state_now = {}, {}
        for idx, ln in enumerate(facility_lines):
            active = scenario in FAULT_SCENARIOS and idx == 0
            physics = configured_line(scenario if active or scenario == "boundary_pump_edge" else "baseline", ln["valves_per_line"])
            result = solve_line(physics, source_head, destination_head)
            line_results[ln["line_id"]] = result
            state_now[ln["pump_id"]] = "degraded" if active and scenario == "pump_degradation" else "running"
            state_now[ln["valve_id"]] = "partial" if active and scenario == "valve_partial" else "open"
            state_now[ln["pipe_id"]] = "leaking" if active and scenario == "leak" else ("blocked" if active and scenario == "blockage" else ("leaking_blocked" if active and scenario == "compound_fault" else "normal"))
            for sensor in by_line[ln["line_id"]]:
                pos, metric, sid = sensor["position"], sensor["metric"], sensor["sensor_id"]
                if metric == "flow":
                    true_value = result["q_in"] if pos == "inlet" else result["q_out"]
                elif metric == "pressure" and pos == "discharge":
                    true_value = (result["h_discharge"] - source_head) * 9.81
                elif metric == "pressure" and sensor["entity_type"] in {"valve", "valve_train"}:
                    true_value = (result["h_discharge"] - source_head - result["valve_drop_m"]) * 9.81
                elif metric == "pressure" and sensor["entity_type"] == "pipe":
                    true_value = (result["h_discharge"] - source_head - result["valve_drop_m"] - result["pipe_drop_m"]) * 9.81
                else:
                    true_value = 0.0
                sigma = abs(true_value) * NOISE_RELATIVE_SIGMA[metric]
                measured = true_value + rng.gauss(0, sigma)
                quality = "good"
                if scenario == "sensor_fault" and idx == 0 and pos == "inlet":
                    # Stuck-at reading: process truth remains normal; only the sensor output is altered.
                    if step == 0:
                        stuck_value = measured
                    measured = stuck_value
                point_no += 1
                telemetry_id = f"TLM-{run_id[-6:]}-{point_no:07d}"
                point = {"telemetry_id": telemetry_id, "timestamp_utc": timestamp, "sim_run_id": run_id, "operating_mode_id": "MODE-001", "facility_id": facility, "line_id": ln["line_id"], "sensor_id": sid, "entity_id": sensor["entity_id"], "node_id": sensor["node_id"], "pipe_id": sensor["pipe_id"], "position": pos, "metric": metric, "value": round(measured, 8), "unit": sensor["unit"], "quality_flag": quality}
                telemetry.append(point); step_rows.append(point)
                process_truth.append({"telemetry_id": telemetry_id, "timestamp_utc": timestamp, "sim_run_id": run_id, "sensor_id": sid, "true_value": round(true_value, 8), "noise_added": round(measured - true_value, 8), "noise_sigma": round(sigma, 8)})
                state_now[sid] = "stuck_at" if scenario == "sensor_fault" and idx == 0 and pos == "inlet" else "good"
        q_in = sum(v["q_in"] for v in line_results.values())
        q_out = sum(v["q_out"] for v in line_results.values())
        q_leak = sum(v["q_leak"] for v in line_results.values())
        src_next = source.volume_m3 - q_in * dt_h
        dst_next = destination.volume_m3 + q_out * dt_h
        if src_next < 0 or dst_next > destination.capacity_m3:
            raise ValueError("Tank boundary reached; reduce horizon or change initial tank configuration")
        source2, destination2 = replace(source, volume_m3=src_next), replace(destination, volume_m3=dst_next)
        storage_rate = ((source2.volume_m3 + destination2.volume_m3) - (source.volume_m3 + destination.volume_m3)) / dt_h
        true_residual = -q_leak - storage_rate
        # Metered external flow is reconstructed from generated sensor readings.
        source_id, destination_id = facility_lines[0]["source_tank_id"], facility_lines[0]["destination_tank_id"]
        for sensor in sensors:
            if sensor["facility_id"] != facility or sensor["metric"] != "level":
                continue
            if sensor["entity_id"] == source_id:
                true_value = source.level_m
            elif sensor["entity_id"] == destination_id:
                true_value = destination.level_m
            else:
                # Buffer assets are connected storage nodes; this prototype holds them at their initial level.
                true_value = sensor["initial_level_m"]
            sigma = abs(true_value) * NOISE_RELATIVE_SIGMA["level"]
            measured = true_value + rng.gauss(0, sigma)
            point_no += 1
            telemetry_id = f"TLM-{run_id[-6:]}-{point_no:07d}"
            point = {"telemetry_id": telemetry_id, "timestamp_utc": timestamp, "sim_run_id": run_id, "operating_mode_id": "MODE-001", "facility_id": facility, "line_id": "", "sensor_id": sensor["sensor_id"], "entity_id": sensor["entity_id"], "node_id": sensor["node_id"], "pipe_id": "", "position": "level", "metric": "level", "value": round(measured, 8), "unit": sensor["unit"], "quality_flag": "good"}
            telemetry.append(point); step_rows.append(point)
            process_truth.append({"telemetry_id": telemetry_id, "timestamp_utc": timestamp, "sim_run_id": run_id, "sensor_id": sensor["sensor_id"], "true_value": round(true_value, 8), "noise_added": round(measured - true_value, 8), "noise_sigma": round(sigma, 8)})
            state_now[sensor["sensor_id"]] = "good"
        inlet_measured = sum(r["value"] for r in step_rows if r["metric"] == "flow" and r["position"] == "inlet")
        outlet_measured = sum(r["value"] for r in step_rows if r["metric"] == "flow" and r["position"] == "outlet")
        measured_residual = -(inlet_measured - outlet_measured) - storage_rate
        balances.append({"timestamp_utc": timestamp, "sim_run_id": run_id, "facility_id": facility, "true_supply_minus_leak_minus_storage_m3_h": true_residual, "measured_supply_minus_leak_minus_storage_m3_h": measured_residual, "q_in_true_m3_h": q_in, "q_out_true_m3_h": q_out, "q_leak_true_m3_h": q_leak, "storage_rate_m3_h": storage_rate, "source_level_m": source.level_m, "destination_level_m": destination.level_m})
        source, destination = source2, destination2
    return telemetry, process_truth, balances, state_now


def value_map(rows):
    return {(r["sensor_id"], r["timestamp_utc"]): r for r in rows}


def write_network(out: Path, seed=20261022, facility_count=3, lines_per_facility=None, hours=1, step_seconds=60, noise_pct=None, *, pump_count=20, tank_count=30, valve_count=60, telemetry_rows_target=100000, time_steps=None):
    global NOISE_RELATIVE_SIGMA
    explicit_time_steps = time_steps is not None
    if noise_pct is None:
        noise_pct = {"flow": 2.0, "pressure": 1.0, "level": 0.5}
    if set(noise_pct) != {"flow", "pressure", "level"} or any(value < 0 for value in noise_pct.values()):
        raise ValueError("noise_pct must specify nonnegative flow, pressure, and level percentages")
    NOISE_RELATIVE_SIGMA = {k: v / 100.0 for k, v in noise_pct.items()}
    out.mkdir(parents=True, exist_ok=True)
    legacy_line_count = lines_per_facility is not None
    if lines_per_facility is not None:
        pump_count = facility_count * lines_per_facility
        tank_count = facility_count * 2
        valve_count = pump_count
    facilities, tanks, pumps, valves, pipes, lines, sensors = equipment(facility_count, pump_count, tank_count, valve_count)
    lines_per_facility = max(len([ln for ln in lines if ln["facility_id"] == f["facility_id"]]) for f in facilities)
    if time_steps is None and legacy_line_count:
        time_steps = max(1, int(hours * 3600 // step_seconds))
        step_plan = {(f["facility_id"], scenario): time_steps for f in facilities for scenario in SCENARIOS}
    elif time_steps is None:
        step_plan = plan_exact_run_steps(telemetry_rows_target, facilities, sensors)
        time_steps = max(step_plan.values())
    else:
        step_plan = {(f["facility_id"], scenario): time_steps for f in facilities for scenario in SCENARIOS}
    all_telemetry, all_process_truth, all_balances, runs, events, truth, alarms = [], [], [], [], [], [], []
    run_no = 0
    for f_index, facility in enumerate(facilities, 1):
        flines = [l for l in lines if l["facility_id"] == facility["facility_id"]]
        fsensors = [s for s in sensors if s["facility_id"] == facility["facility_id"] and s["metric"] != "level"]
        run_data = {}
        for scenario in SCENARIOS:
            run_step_count = step_plan[(facility["facility_id"], scenario)]
            run_hours = run_step_count * step_seconds / 3600
            run_no += 1
            run_id = f"SIM-2026-{run_no:06d}"
            run_seed = seed + f_index + (1000 if scenario == "baseline_repeat" else 0)
            telemetry, process_truth, balances, end_states = simulate_run(facility["facility_id"], flines, sensors, run_id, scenario, run_seed, run_step_count, step_seconds)
            run_data[scenario] = (run_id, telemetry, balances, end_states, process_truth)
            config = {"seed": run_seed, "noise_relative_sigma": NOISE_RELATIVE_SIGMA, "detectability_sigma": DETECTABILITY_SIGMA, "hours": run_hours, "time_steps": run_step_count, "step_seconds": step_seconds, "pump_count": pump_count, "tank_count": tank_count, "valve_count": valve_count, "lines_per_facility_max": lines_per_facility, "initial_source_fill_fraction": 0.05 if scenario == "boundary_tank_low" else 0.60, "initial_destination_fill_fraction": 0.95 if scenario == "boundary_tank_high" else 0.56, "boundary_case": scenario if scenario.startswith("boundary_") else "none", "base_model_parameters": {"pump_h0_m": 50.0, "pump_a": 0.0015, "pipe_k": 0.00001 if scenario == "boundary_pump_edge" else 0.001, "valve_k": 0.00001 if scenario == "boundary_pump_edge" else 0.0005}}
            runs.append({"sim_run_id": run_id, "facility_id": facility["facility_id"], "seed": run_seed, "config_hash": __import__("hashlib").sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(), "config_json": json.dumps(config, sort_keys=True), "started_at_utc": START.isoformat().replace("+00:00", "Z"), "status": "complete"})
            all_telemetry.extend(telemetry); all_process_truth.extend(process_truth); all_balances.extend(balances)
            if scenario in FAULT_SCENARIOS:
                target = flines[0]
                inlet_sensor_id = next(s["sensor_id"] for s in fsensors if s["line_id"] == target["line_id"] and s["metric"] == "flow" and s["position"] == "inlet")
                entity_id = {"leak": target["pipe_id"], "blockage": target["pipe_id"], "pump_degradation": target["pump_id"], "valve_partial": target["valve_id"], "sensor_fault": inlet_sensor_id, "compound_fault": target["pipe_id"]}[scenario]
                base_run = run_data["baseline"]
                baseline_rows, baseline_truth = base_run[1], base_run[4]
                base_map, fault_map = value_map(baseline_rows), value_map(telemetry)
                base_true, fault_true = value_map(baseline_truth), value_map(process_truth)
                line_sensors = [s for s in fsensors if s["line_id"] == target["line_id"]]
                signal = {"leak": "paired_flow_difference", "blockage": "pipe_pressure_drop", "pump_degradation": "pump_discharge_pressure", "valve_partial": "valve_pressure_drop", "sensor_fault": "paired_flow_difference", "compound_fault": "paired_flow_difference"}[scenario]
                if scenario in {"leak", "sensor_fault", "compound_fault"}:
                    inlet = next(s for s in line_sensors if s["metric"] == "flow" and s["position"] == "inlet")
                    outlet = next(s for s in line_sensors if s["metric"] == "flow" and s["position"] == "outlet")
                    keys = [(inlet["sensor_id"], r["timestamp_utc"]) for r in baseline_rows if r["sensor_id"] == inlet["sensor_id"]]
                    measured_effect_abs = sum((fault_map[k]["value"] - fault_map[(outlet["sensor_id"], k[1])]["value"]) - (base_map[k]["value"] - base_map[(outlet["sensor_id"], k[1])]["value"]) for k in keys) / len(keys)
                    true_effect_abs = 0.0 if scenario == "sensor_fault" else sum(fault_true[k]["true_value"] - fault_true[(outlet["sensor_id"], k[1])]["true_value"] for k in keys) / len(keys)
                    noise_sigma = math.sqrt((NOISE_RELATIVE_SIGMA["flow"] * 130) ** 2 * 2)
                    evidence_sensor = inlet if scenario == "sensor_fault" else outlet
                elif scenario == "blockage":
                    vin = next(s for s in line_sensors if s["metric"] == "pressure" and s["position"] == "valve_train_outlet")
                    pout = next(s for s in line_sensors if s["metric"] == "pressure" and s["position"] == "pipe_outlet")
                    keys = [(vin["sensor_id"], r["timestamp_utc"]) for r in baseline_rows if r["sensor_id"] == vin["sensor_id"]]
                    true_effect_abs = sum((fault_true[k]["true_value"] - fault_true[(pout["sensor_id"], k[1])]["true_value"]) - (base_true[k]["true_value"] - base_true[(pout["sensor_id"], k[1])]["true_value"]) for k in keys) / len(keys)
                    measured_effect_abs = sum((fault_map[k]["value"] - fault_map[(pout["sensor_id"], k[1])]["value"]) - (base_map[k]["value"] - base_map[(pout["sensor_id"], k[1])]["value"]) for k in keys) / len(keys)
                    noise_sigma = math.sqrt((NOISE_RELATIVE_SIGMA["pressure"] * 200) ** 2 * 2)
                    evidence_sensor = pout
                elif scenario == "valve_partial":
                    up = next(s for s in line_sensors if s["metric"] == "pressure" and s["position"] == "discharge")
                    down = next(s for s in line_sensors if s["metric"] == "pressure" and s["position"] == "valve_train_outlet")
                    keys = [(up["sensor_id"], r["timestamp_utc"]) for r in baseline_rows if r["sensor_id"] == up["sensor_id"]]
                    true_effect_abs = sum((fault_true[k]["true_value"]-fault_true[(down["sensor_id"], k[1])]["true_value"]) - (base_true[k]["true_value"]-base_true[(down["sensor_id"], k[1])]["true_value"]) for k in keys)/len(keys)
                    measured_effect_abs = sum((fault_map[k]["value"]-fault_map[(down["sensor_id"], k[1])]["value"]) - (base_map[k]["value"]-base_map[(down["sensor_id"], k[1])]["value"]) for k in keys)/len(keys)
                    noise_sigma = math.sqrt((NOISE_RELATIVE_SIGMA["pressure"] * 200) ** 2 * 2)
                    evidence_sensor = down
                else:
                    sensor = next(s for s in line_sensors if s["metric"] == "pressure" and s["position"] == "discharge")
                    keys = [(sensor["sensor_id"], r["timestamp_utc"]) for r in baseline_rows if r["sensor_id"] == sensor["sensor_id"]]
                    true_effect_abs = sum(fault_true[k]["true_value"] - base_true[k]["true_value"] for k in keys) / len(keys)
                    measured_effect_abs = sum(fault_map[k]["value"] - base_map[k]["value"] for k in keys) / len(keys)
                    noise_sigma = NOISE_RELATIVE_SIGMA["pressure"] * 200
                    evidence_sensor = sensor
                sample_count = max(1, run_step_count)
                window_sigma = noise_sigma / math.sqrt(sample_count)
                effect_abs = measured_effect_abs if scenario == "sensor_fault" else true_effect_abs
                effect_for_detectability = measured_effect_abs if scenario == "sensor_fault" else true_effect_abs
                detectable = abs(effect_for_detectability) >= window_detection_threshold(noise_sigma, sample_count)
                nominal = 130 if "flow" in signal else 200
                fault_params = {"leak": {"leak_coefficient_m3h_per_sqrt_m": 5.0, "leak_position_fraction": 0.5}, "blockage": {"pipe_resistance_multiplier": 3.0}, "pump_degradation": {"shutoff_head_factor": 0.9}, "valve_partial": {"opening_fraction": 0.65}, "sensor_fault": {"fault_mode": "stuck_at", "position": "line_inlet_flow"}, "compound_fault": {"leak_coefficient_m3h_per_sqrt_m": 5.0, "pipe_resistance_multiplier": 3.0}}[scenario]
                evidence_key = next(k for k in reversed(list(fault_map)) if k[0] == evidence_sensor["sensor_id"])
                evidence_id = fault_map[evidence_key]["telemetry_id"]
                truth_row = {"scenario_id": f"SCN-{run_no:06d}", "sim_run_id": run_id, "issue_type": scenario, "entity_id": entity_id, "start_ts": START.isoformat().replace("+00:00", "Z"), "end_ts": (START+timedelta(hours=run_hours)).isoformat().replace("+00:00", "Z"), "is_process_fault": "false" if scenario == "sensor_fault" else "true", "fault_params_json": json.dumps(fault_params, sort_keys=True), "primary_signal": signal, "evidence_sensor_id": evidence_sensor["sensor_id"], "evidence_telemetry_id": evidence_id, "effect_abs": round(effect_abs, 8), "effect_relative": round(effect_abs / nominal, 8), "true_effect_abs": round(true_effect_abs, 8), "measured_effect_abs": round(measured_effect_abs, 8), "noise_sigma_single_sample": round(noise_sigma, 8), "noise_sigma_window": round(window_sigma, 8), "sample_count": sample_count, "detectability_sigma": DETECTABILITY_SIGMA, "detectability_rule": "abs(window_mean_effect) >= detectability_sigma * noise_sigma_single_sample / sqrt(sample_count)", "detectable": str(detectable).lower(), "expected_sign_by_location_json": json.dumps(expected_signs(scenario), sort_keys=True)}
                alarm_triggered = abs(measured_effect_abs) >= window_detection_threshold(noise_sigma, sample_count)
                truth_row["alarm_detected"] = str(alarm_triggered).lower()
                truth.append(truth_row)
                if alarm_triggered:
                    alarms.append({"alarm_id": f"ALM-{len(alarms)+1:07d}", "timestamp_utc": truth_row["end_ts"], "sim_run_id": run_id, "facility_id": facility["facility_id"], "line_id": target["line_id"], "alarm_type": "abnormal_window_signal", "primary_signal": signal, "trigger_telemetry_id": evidence_id, "window_effect_abs": round(measured_effect_abs, 8), "noise_sigma_window": round(window_sigma, 8), "detector_rule": f"abs(window_mean_effect) >= {DETECTABILITY_SIGMA:g} * noise_sigma_window", "status": "open"})
                # State events come from the difference between baseline and faulted snapshots.
                baseline_states, fault_states = base_run[3], run_data[scenario][3]
                for asset, fault_state in fault_states.items():
                    normal_state = baseline_states.get(asset, fault_state)
                    if normal_state == fault_state:
                        continue
                    entity_type = "sensor" if asset.startswith("SNS-") else ("pump" if asset.startswith("PUMP-") else ("valve" if asset.startswith("VALVE-") else "pipe"))
                    events.append({"event_id": f"EVT-{len(events)+1:07d}", "event_ts": START.isoformat().replace("+00:00", "Z"), "entity_type": entity_type, "entity_id": asset, "event_type": "state_change", "from_state": normal_state, "to_state": fault_state, "sim_run_id": run_id, "cause_scenario_id": f"SCN-{run_no:06d}"})
                    events.append({"event_id": f"EVT-{len(events)+1:07d}", "event_ts": (START+timedelta(hours=run_hours)).isoformat().replace("+00:00", "Z"), "entity_type": entity_type, "entity_id": asset, "event_type": "state_change", "from_state": fault_state, "to_state": normal_state, "sim_run_id": run_id, "cause_scenario_id": f"SCN-{run_no:06d}"})

    write_csv(out / "facilities.csv", facilities, ["facility_id", "name", "lifecycle_state"])
    write_csv(out / "tanks.csv", tanks, ["tank_id", "facility_id", "tank_role", "capacity_m3", "area_m2", "initial_volume_m3", "lifecycle_state"])
    write_csv(out / "pumps.csv", pumps, ["pump_id", "facility_id", "line_id", "nominal_flow_m3_h", "shutoff_head_m", "lifecycle_state"])
    write_csv(out / "valves.csv", valves, ["valve_id", "facility_id", "line_id", "normal_opening_pct", "sequence_order", "resistance_k", "lifecycle_state"])
    write_csv(out / "pipes.csv", pipes, ["pipe_id", "facility_id", "line_id", "from_node_id", "to_node_id", "resistance_k", "edge_role", "sequence_order", "lifecycle_state"])
    write_csv(out / "lines.csv", lines, ["line_id", "facility_id", "source_tank_id", "destination_tank_id", "pump_id", "valve_id", "pipe_id"])
    write_csv(out / "line_valves.csv", [{"line_id": l["line_id"], "valve_id": v["valve_id"], "sequence_order": v["sequence_order"]} for l in lines for v in valves if v["line_id"] == l["line_id"]], ["line_id", "valve_id", "sequence_order"])
    write_csv(out / "line_pipes.csv", [{"line_id": l["line_id"], "pipe_id": q["pipe_id"], "sequence_order": q.get("sequence_order", 1)} for l in lines for q in pipes if q["line_id"] == l["line_id"]], ["line_id", "pipe_id", "sequence_order"])
    write_csv(out / "sensors.csv", sensors, ["sensor_id", "facility_id", "line_id", "entity_type", "entity_id", "node_id", "pipe_id", "position", "metric", "unit", "initial_level_m"])
    write_csv(out / "telemetry.csv", all_telemetry, ["telemetry_id", "timestamp_utc", "sim_run_id", "operating_mode_id", "facility_id", "line_id", "sensor_id", "entity_id", "node_id", "pipe_id", "position", "metric", "value", "unit", "quality_flag"])
    write_csv(out / "process_truth.csv", all_process_truth, ["telemetry_id", "timestamp_utc", "sim_run_id", "sensor_id", "true_value", "noise_added", "noise_sigma"])
    write_csv(out / "simulation_runs.csv", runs, ["sim_run_id", "facility_id", "seed", "config_hash", "config_json", "started_at_utc", "status"])
    write_csv(out / "equipment_events.csv", events, ["event_id", "event_ts", "entity_type", "entity_id", "event_type", "from_state", "to_state", "sim_run_id", "cause_scenario_id"])
    write_csv(out / "ground_truth.csv", truth, ["scenario_id", "sim_run_id", "issue_type", "entity_id", "start_ts", "end_ts", "is_process_fault", "fault_params_json", "primary_signal", "evidence_sensor_id", "evidence_telemetry_id", "effect_abs", "effect_relative", "true_effect_abs", "measured_effect_abs", "noise_sigma_single_sample", "noise_sigma_window", "sample_count", "detectability_sigma", "detectability_rule", "detectable", "alarm_detected", "expected_sign_by_location_json"])
    write_csv(out / "alarms.csv", alarms, ["alarm_id", "timestamp_utc", "sim_run_id", "facility_id", "line_id", "alarm_type", "primary_signal", "trigger_telemetry_id", "window_effect_abs", "noise_sigma_window", "detector_rule", "status"])
    write_csv(out / "network_balance.csv", all_balances, ["timestamp_utc", "sim_run_id", "facility_id", "true_supply_minus_leak_minus_storage_m3_h", "measured_supply_minus_leak_minus_storage_m3_h", "q_in_true_m3_h", "q_out_true_m3_h", "q_leak_true_m3_h", "storage_rate_m3_h", "source_level_m", "destination_level_m"])
    write_csv(out / "fault_location_rules.csv", expected_signs("all").values(), ["issue_type", "location", "signal", "expected_sign", "meaning"])
    operating_modes = [{"operating_mode_id":"MODE-001", "name":"nominal", "description":"Normal synthetic line operation", "effective_from_utc":START.isoformat().replace("+00:00","Z"), "effective_to_utc":""}]
    valve_mode_states = [{"valve_id":v["valve_id"], "operating_mode_id":"MODE-001", "state":"open", "effective_from_utc":START.isoformat().replace("+00:00","Z"), "effective_to_utc":""} for v in valves]
    write_csv(out / "operating_modes.csv", operating_modes, ["operating_mode_id", "name", "description", "effective_from_utc", "effective_to_utc"])
    write_csv(out / "valve_mode_states.csv", valve_mode_states, ["valve_id", "operating_mode_id", "state", "effective_from_utc", "effective_to_utc"])
    max_pumps_per_facility = max(len([l for l in lines if l["facility_id"] == f["facility_id"]]) for f in facilities)
    edge_cases = edge_case_fixtures(NOISE_RELATIVE_SIGMA["flow"], max_pumps_per_facility)
    boundaries = boundary_fixtures()
    for row in boundaries:
        row["validator_passed"] = str(row["lower_limit"] <= row["value"] <= row["upper_limit"]).lower()
    write_csv(out / "negative_fixtures.csv", edge_cases, ["case_id", "case", "entity", "observed", "ground_truth_issue", "is_process_fault", "validator_rule", "validator_flagged"])
    write_csv(out / "boundary_fixtures.csv", boundaries, ["boundary_id", "case", "metric", "value", "unit", "lower_limit", "upper_limit", "expected_validator_result", "scenario_coverage", "validator_passed"])
    config = {"seed": seed, "noise_relative_sigma": NOISE_RELATIVE_SIGMA, "detectability_sigma": DETECTABILITY_SIGMA, "noise_note": "Synthetic independent Gaussian sensor noise; assumptions only, not measured plant noise."}
    run_ids = {x["sim_run_id"] for x in runs}
    telemetry_ids = {x["telemetry_id"] for x in all_telemetry}
    equipment_ids = {r[k] for r, k in [(row, "tank_id") for row in tanks] + [(row, "pump_id") for row in pumps] + [(row, "valve_id") for row in valves] + [(row, "pipe_id") for row in pipes]}
    max_true_residual = max(abs(r["true_supply_minus_leak_minus_storage_m3_h"]) for r in all_balances)
    measured_residuals = sorted(abs(r["measured_supply_minus_leak_minus_storage_m3_h"]) for r in all_balances)
    flow_balance_tolerance = 2.576 * math.sqrt(2 * max_pumps_per_facility) * NOISE_RELATIVE_SIGMA["flow"] * 130
    fault_run_ids = {r["sim_run_id"] for r in truth}
    fault_free_balances = [r for r in all_balances if r["sim_run_id"] not in fault_run_ids]
    fault_free_over_tolerance = sum(abs(r["measured_supply_minus_leak_minus_storage_m3_h"]) > flow_balance_tolerance for r in fault_free_balances)
    alarm_run_ids = {r["sim_run_id"] for r in alarms}
    alarm_signal_pairs = [(r["detectable"] == "true", r["sim_run_id"] in alarm_run_ids) for r in truth]
    alarm_detectability = {
        "true_positive": sum(expected and actual for expected, actual in alarm_signal_pairs),
        "false_positive": sum(not expected and actual for expected, actual in alarm_signal_pairs),
        "false_negative": sum(expected and not actual for expected, actual in alarm_signal_pairs),
        "true_negative": sum(not expected and not actual for expected, actual in alarm_signal_pairs),
    }
    alarm_detectability["agreement_rate"] = sum(expected == actual for expected, actual in alarm_signal_pairs) / len(alarm_signal_pairs) if alarm_signal_pairs else 1.0
    edge_cases_flagged = all(r["validator_flagged"] == "true" for r in edge_cases)
    line_bridge_consistent = all(
        ln["valve_id"] == max((v for v in valves if v["line_id"] == ln["line_id"]), key=lambda v: v["sequence_order"])["valve_id"]
        and ln["pipe_id"] == max((q for q in pipes if q["line_id"] == ln["line_id"]), key=lambda q: q["sequence_order"])["pipe_id"]
        for ln in lines
    )
    boundary_runs = [r for r in runs if json.loads(r["config_json"]).get("boundary_case", "none") != "none"]
    pump_edge_run_ids = {r["sim_run_id"] for r in runs if json.loads(r["config_json"]).get("boundary_case") == "boundary_pump_edge"}
    pump_edge_ratios = [
        (b["q_in_true_m3_h"] / lines_per_facility) / math.sqrt(max((50.0 - (b["destination_level_m"] - b["source_level_m"])), 0.0) / 0.0015)
        for b in all_balances if b["sim_run_id"] in pump_edge_run_ids and 50.0 > (b["destination_level_m"] - b["source_level_m"])
    ]
    summary = {
        "facility_count": facility_count, "pump_count": len(pumps), "tank_count": len(tanks), "valve_count": len(valves), "lines_per_facility": lines_per_facility, "valves_per_pump_average": valve_count / pump_count, "valves_per_line_range": {"min": min(len([v for v in valves if v["line_id"] == l["line_id"]]) for l in lines), "max": max(len([v for v in valves if v["line_id"] == l["line_id"]]) for l in lines)}, "run_count": len(runs),
        "telemetry_rows_target": telemetry_rows_target, "telemetry_rows_exact": len(all_telemetry) == telemetry_rows_target, "telemetry_rows_difference": len(all_telemetry) - telemetry_rows_target, "time_steps_per_run_range": {"min": min(json.loads(r["config_json"])["time_steps"] for r in runs), "max": max(json.loads(r["config_json"])["time_steps"] for r in runs)}, "step_seconds": step_seconds,
        "telemetry_rows": len(all_telemetry), "ground_truth_rows": len(truth), "event_rows": len(events),
        "primary_keys_unique": all(len(rows) == len({r[key] for r in rows}) for rows, key in [(facilities,"facility_id"),(tanks,"tank_id"),(pumps,"pump_id"),(valves,"valve_id"),(pipes,"pipe_id"),(lines,"line_id"),(sensors,"sensor_id"),(runs,"sim_run_id")]),
        "foreign_keys_valid": all(r["source_tank_id"] in equipment_ids and r["destination_tank_id"] in equipment_ids and r["pump_id"] in equipment_ids and r["valve_id"] in equipment_ids and r["pipe_id"] in equipment_ids for r in lines) and all((r["entity_id"] in equipment_ids if r["entity_id"] else r["pipe_id"] in equipment_ids) for r in sensors) and all(r["sensor_id"] in {s["sensor_id"] for s in sensors} and r["operating_mode_id"] == "MODE-001" for r in all_telemetry) and all(r["telemetry_id"] in telemetry_ids for r in all_process_truth),
        "facility_graphs_connected": all(topology_is_connected(f["facility_id"], tanks, pumps, valves, pipes) for f in facilities),
        "pipe_node_references_valid": pipe_node_references_valid(tanks, pumps, valves, pipes),
        "line_terminal_bridges_consistent": line_bridge_consistent,
        "all_run_ids_on_telemetry": all(r["sim_run_id"] in run_ids for r in all_telemetry),
        "event_and_truth_run_ids_valid": all(r["sim_run_id"] in run_ids for r in events + truth),
        "all_scenarios_have_ground_truth": len(truth) == facility_count * len(FAULT_SCENARIOS),
        "sensor_fault_is_not_process_fault": all(r["is_process_fault"] == "false" for r in truth if r["issue_type"] == "sensor_fault"),
        "max_true_network_residual_m3_h": max_true_residual,
        "true_network_balance_reconciles": max_true_residual < 1e-6,
        "negative_fixture_count": len(edge_cases),
        "all_negative_fixtures_flagged": edge_cases_flagged,
        "boundary_fixture_count": len(boundaries),
        "all_boundary_fixtures_pass_range_checks": all(r["validator_passed"] == "true" for r in boundaries),
        "compound_fault_runs": sum(1 for r in truth if r["issue_type"] == "compound_fault"),
        "fault_free_run_count": len(runs) - len(truth),
        "fault_run_count": len(truth),
        "boundary_run_count": len(boundary_runs),
        "pump_edge_run_count": len(pump_edge_run_ids),
        "pump_edge_mean_flow_fraction_of_available_runout": sum(pump_edge_ratios)/len(pump_edge_ratios) if pump_edge_ratios else None,
        "tank_level_range_m": {"min": min(min(r["source_level_m"],r["destination_level_m"]) for r in all_balances), "max": max(max(r["source_level_m"],r["destination_level_m"]) for r in all_balances)},
        "all_boundary_tanks_within_capacity": all(0 <= r["source_level_m"] <= 50 and 0 <= r["destination_level_m"] <= 50 for r in all_balances),
        "alarm_count": len(alarms),
        "alarm_vs_detectable_on_labeled_windows": alarm_detectability,
        "alarm_telemetry_references_valid": all(r["trigger_telemetry_id"] in telemetry_ids for r in alarms),
        "measured_network_residual_abs_m3_h": {"mean": sum(measured_residuals)/len(measured_residuals), "p95": measured_residuals[min(len(measured_residuals)-1, int(0.95*len(measured_residuals)))], "max": measured_residuals[-1]},
        "flow_balance_fixture_noise_tolerance_m3_h": flow_balance_tolerance,
        "flow_balance_fixture_injected_residual_m3_h": 3 * flow_balance_tolerance,
        "flow_balance_fixture_clearance_ratio": 3.0,
        "flow_balance_tolerance_method": "Two-sided 99% Gaussian envelope from propagated independent inlet/outlet flow-sensor noise summed across the facility; not an empirically calibrated 3-sigma residual limit.",
        "fault_free_residual_false_positive_count": fault_free_over_tolerance,
        "fault_free_residual_false_positive_rate": fault_free_over_tolerance / len(fault_free_balances) if fault_free_balances else 0.0,
        "fault_free_residual_sample_count": len(fault_free_balances),
        "config": config,
    }
    (out / "network_validation_summary.json").write_text(json.dumps(stable_values(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    command_output = "sample-data" if telemetry_rows_target < 100000 else "data"
    generator_command = f"python src/network_expansion.py --out {command_output} --seed {seed} --facilities {facility_count} --pumps {pump_count} --tanks {tank_count} --valves {valve_count} --telemetry-rows {telemetry_rows_target}"
    if noise_pct != {"flow": 2.0, "pressure": 1.0, "level": 0.5}:
        generator_command += f" --flow-noise-pct {noise_pct['flow']} --pressure-noise-pct {noise_pct['pressure']} --level-noise-pct {noise_pct['level']}"
    if step_seconds != 60:
        generator_command += f" --step-seconds {step_seconds}"
    if explicit_time_steps or legacy_line_count:
        generator_command += f" --time-steps {time_steps}"
    build_exports(out, seed, generator_command, stable_values(summary))
    import hashlib
    row_counts = {}
    hashes = {}
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "source_manifest.json":
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            if path.suffix == ".csv":
                with path.open(encoding="utf-8", newline="") as f:
                    row_counts[path.name] = max(0, sum(1 for _ in f) - 1)
    manifest = {"provenance": "All generated plant values are synthetic; no external operational data used.", "seed": seed, "generator_command": generator_command, "files_sha256": hashes, "csv_row_counts": row_counts}
    (out / "source_manifest.json").write_text(json.dumps(stable_values(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def expected_signs(scenario):
    rules = [
        {"issue_type":"leak", "location":"inlet_flow", "signal":"q_in", "expected_sign":"slightly_up", "meaning":"Leak increases line draw at inlet."},
        {"issue_type":"leak", "location":"outlet_flow", "signal":"q_out", "expected_sign":"down", "meaning":"Less flow reaches destination."},
        {"issue_type":"leak", "location":"paired_flows", "signal":"q_in-q_out", "expected_sign":"up", "meaning":"Flow gap estimates leak flow."},
        {"issue_type":"leak", "location":"pump_discharge_pressure", "signal":"pressure", "expected_sign":"down", "meaning":"Modeled discharge pressure falls slightly."},
        {"issue_type":"blockage", "location":"pump_discharge_pressure", "signal":"pressure", "expected_sign":"up", "meaning":"Pressure rises upstream of pipe restriction."},
        {"issue_type":"blockage", "location":"pipe_across_taps", "signal":"pressure_drop", "expected_sign":"up", "meaning":"Pressure loss across restricted pipe increases."},
        {"issue_type":"pump_degradation", "location":"pump_discharge_pressure", "signal":"pressure", "expected_sign":"down", "meaning":"Reduced pump head lowers discharge pressure."},
        {"issue_type":"valve_partial", "location":"valve_across_taps", "signal":"pressure_drop", "expected_sign":"up", "meaning":"Pressure loss across partially closed valve increases."},
        {"issue_type":"valve_partial", "location":"pipe_pressure_drop", "signal":"pressure_drop", "expected_sign":"down", "meaning":"Lower line flow reduces pipe friction loss."},
        {"issue_type":"sensor_fault", "location":"faulty_sensor", "signal":"measurement_error", "expected_sign":"depends_on_fault", "meaning":"Process truth is unchanged; reading alone is faulty."},
        {"issue_type":"sensor_fault", "location":"paired_flows", "signal":"apparent_flow_gap", "expected_sign":"may_be_nonzero", "meaning":"Stuck inlet sensor can mimic a leak in measured data."},
        {"issue_type":"compound_fault", "location":"paired_flows", "signal":"q_in-q_out", "expected_sign":"up", "meaning":"Concurrent leak and blockage produce a flow gap."},
        {"issue_type":"compound_fault", "location":"pipe_across_taps", "signal":"pressure_drop", "expected_sign":"up", "meaning":"Concurrent blockage increases pipe pressure loss."},
    ]
    return {f"{r['issue_type']}:{r['location']}": r for r in rules}


def edge_case_fixtures(flow_noise_sigma=0.02, max_pumps_per_facility=7):
    """Build isolated invalid examples and run each through its named validator rule."""
    fixtures = [
        {"case_id":"EDGE-001", "case":"pipe references missing node", "entity":"Pipe", "observed":"to_node_id=NODE-MISSING", "ground_truth_issue":"missing_node_reference", "is_process_fault":"false", "validator_rule":"foreign_key_exists", "_data":{"to_node_id":"NODE-MISSING"}},
        {"case_id":"EDGE-002", "case":"tank level above capacity", "entity":"Tank", "observed":"level_pct=101; maximum_pct=100", "ground_truth_issue":"tank_over_capacity", "is_process_fault":"true", "validator_rule":"level_within_capacity", "_data":{"level_pct":101,"maximum_pct":100}},
        {"case_id":"EDGE-003", "case":"flow conservation beyond tolerance", "entity":"NetworkBalance", "observed":"", "ground_truth_issue":"flow_balance_violation", "is_process_fault":"true", "validator_rule":"residual_within_noise_tolerance", "_data":{}},
        {"case_id":"EDGE-004", "case":"simulation output missing input config", "entity":"SimulationRun", "observed":"config_json=", "ground_truth_issue":"missing_run_configuration", "is_process_fault":"false", "validator_rule":"configuration_present", "_data":{"config_json":""}},
        {"case_id":"EDGE-005", "case":"sensor fault mislabeled as process fault", "entity":"GroundTruth", "observed":"issue_type=sensor_fault; is_process_fault=true", "ground_truth_issue":"sensor_fault_label_mismatch", "is_process_fault":"false", "validator_rule":"sensor_fault_not_process_fault", "_data":{"issue_type":"sensor_fault","is_process_fault":True}},
    ]
    for row in fixtures:
        data = row.pop("_data")
        case_id = row["case_id"]
        if case_id == "EDGE-001": flagged = data["to_node_id"] not in {"TANK-001", "PUMP-001", "VALVE-001"}
        elif case_id == "EDGE-002": flagged = data["level_pct"] > data["maximum_pct"]
        elif case_id == "EDGE-003":
            # Two-sided 99% envelope from propagated independent sensor noise; inject a 3x violation.
            data["tolerance_m3_h"] = 2.576 * math.sqrt(2 * max_pumps_per_facility) * flow_noise_sigma * 130
            data["residual_m3_h"] = 3 * data["tolerance_m3_h"]
            row["observed"] = f"residual_m3_h={data['residual_m3_h']:.3f}; noise_tolerance_m3_h={data['tolerance_m3_h']:.3f}"
            flagged = abs(data["residual_m3_h"]) > data["tolerance_m3_h"]
        elif case_id == "EDGE-004": flagged = not bool(data["config_json"])
        else: flagged = data["issue_type"] == "sensor_fault" and data["is_process_fault"]
        row["validator_flagged"] = str(flagged).lower()
    return fixtures


def boundary_fixtures():
    """Valid records close to operating limits; expected to pass range validation."""
    return [
        {"boundary_id":"BND-001", "case":"tank near empty", "metric":"fill_pct", "value":0.5, "unit":"%", "lower_limit":0.0, "upper_limit":100.0, "expected_validator_result":"pass_boundary", "scenario_coverage":"tank_low_level"},
        {"boundary_id":"BND-002", "case":"tank near full", "metric":"fill_pct", "value":99.5, "unit":"%", "lower_limit":0.0, "upper_limit":100.0, "expected_validator_result":"pass_boundary", "scenario_coverage":"tank_high_level"},
        {"boundary_id":"BND-003", "case":"pump near runout curve edge", "metric":"flow_fraction_of_runout", "value":0.99, "unit":"fraction", "lower_limit":0.0, "upper_limit":1.0, "expected_validator_result":"pass_boundary", "scenario_coverage":"pump_curve_edge"},
    ]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("network-preview"))
    p.add_argument("--seed", type=int, default=20261022)
    p.add_argument("--facilities", type=int, default=3)
    p.add_argument("--pumps", type=int, default=20)
    p.add_argument("--tanks", type=int, default=30)
    p.add_argument("--valves", type=int, default=60)
    p.add_argument("--telemetry-rows", type=int, default=100000)
    p.add_argument("--time-steps", type=int)
    p.add_argument("--step-seconds", type=int, default=60)
    p.add_argument("--flow-noise-pct", type=float, default=2.0)
    p.add_argument("--pressure-noise-pct", type=float, default=1.0)
    p.add_argument("--level-noise-pct", type=float, default=0.5)
    p.add_argument("--detectability-sigma", type=float, default=3.0)
    args = p.parse_args()
    if args.facilities < 1 or args.pumps < args.facilities or args.tanks < 2 * args.facilities or args.valves < args.pumps or args.telemetry_rows < 1 or args.step_seconds < 1 or (args.time_steps is not None and args.time_steps < 1) or args.detectability_sigma <= 0:
        p.error("counts must support connected facilities and at least one valve per line; telemetry and step sizes must be positive")
    global DETECTABILITY_SIGMA
    DETECTABILITY_SIGMA = args.detectability_sigma
    summary = write_network(args.out, args.seed, args.facilities, noise_pct={"flow": args.flow_noise_pct, "pressure": args.pressure_noise_pct, "level": args.level_noise_pct}, pump_count=args.pumps, tank_count=args.tanks, valve_count=args.valves, telemetry_rows_target=args.telemetry_rows, time_steps=args.time_steps, step_seconds=args.step_seconds)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
