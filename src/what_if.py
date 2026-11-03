"""Compare a baseline pump line with a changed valve opening."""
import argparse
import csv
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

try:
    from src.line_physics import Line, TANK_AREA_M2, simulate
except ModuleNotFoundError:
    from line_physics import Line, TANK_AREA_M2, simulate


STARTED_AT = "2026-01-01T00:00:00Z"


def _simulation_run(run_id, config):
    config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return {
        "sim_run_id": run_id,
        "facility_id": "FAC-WHATIF-001",
        "seed": 0,
        "config_hash": hashlib.sha256(config_json.encode("utf-8")).hexdigest(),
        "config_json": config_json,
        "started_at_utc": STARTED_AT,
        "status": "complete",
    }


def run_what_if(out: Path, valve_opening=0.8, hours=24, step_seconds=60):
    """Write paired baseline/valve-change SimulationRuns and their deltas."""
    if not 0.01 <= valve_opening <= 1.0:
        raise ValueError("valve_opening must be in [0.01, 1.0]; 0.0 (fully closed) is unsupported")
    if hours <= 0 or step_seconds <= 0 or hours * 3600 % step_seconds:
        raise ValueError("hours and step_seconds must be positive and divide evenly")

    base_line = Line()
    changed_line = replace(base_line, valve_open=valve_opening)
    baseline = simulate(base_line, "baseline", hours=hours, step_seconds=step_seconds)
    changed = simulate(changed_line, "baseline", hours=hours, step_seconds=step_seconds)

    pair_config = json.dumps(
        {"valve_opening": valve_opening, "hours": hours, "step_seconds": step_seconds},
        sort_keys=True,
        separators=(",", ":"),
    )
    pair_id = f"WIF-{hashlib.sha256(pair_config.encode('utf-8')).hexdigest()[:10].upper()}"
    baseline_id, changed_id = f"SIM-{pair_id}-BASE", f"SIM-{pair_id}-CHANGE"
    shared_inputs = {"hours": hours, "step_seconds": step_seconds}
    runs = [
        _simulation_run(baseline_id, {
            "run_type": "what_if_baseline", "what_if_pair_id": pair_id,
            "input_config": shared_inputs, "line_parameters": asdict(base_line), "noise_model": "none",
        }),
        _simulation_run(changed_id, {
            "run_type": "what_if_operating_change", "what_if_pair_id": pair_id,
            "input_config": shared_inputs, "line_parameters": asdict(changed_line), "noise_model": "none",
        }),
    ]

    series = []
    for base_row, changed_row in zip(baseline, changed):
        series.append({
            "timestamp_utc": base_row["timestamp_utc"],
            "baseline_sim_run_id": baseline_id,
            "what_if_sim_run_id": changed_id,
            "valve_opening_baseline": 1.0,
            "valve_opening_what_if": valve_opening,
            "q_in_baseline_m3_h": base_row["q_in_m3_h"],
            "q_in_what_if_m3_h": changed_row["q_in_m3_h"],
            "delta_q_in_m3_h": changed_row["q_in_m3_h"] - base_row["q_in_m3_h"],
            "q_out_baseline_m3_h": base_row["q_out_m3_h"],
            "q_out_what_if_m3_h": changed_row["q_out_m3_h"],
            "delta_q_out_m3_h": changed_row["q_out_m3_h"] - base_row["q_out_m3_h"],
            "p_discharge_baseline_kpa_gauge": base_row["p_discharge_kpa_gauge"],
            "p_discharge_what_if_kpa_gauge": changed_row["p_discharge_kpa_gauge"],
            "delta_p_discharge_kpa": changed_row["p_discharge_kpa_gauge"] - base_row["p_discharge_kpa_gauge"],
            "source_level_baseline_m": base_row["source_level_m"],
            "source_level_what_if_m": changed_row["source_level_m"],
            "delta_source_level_m": changed_row["source_level_m"] - base_row["source_level_m"],
            "destination_level_baseline_m": base_row["destination_level_m"],
            "destination_level_what_if_m": changed_row["destination_level_m"],
            "delta_destination_level_m": changed_row["destination_level_m"] - base_row["destination_level_m"],
        })

    out.mkdir(parents=True, exist_ok=True)
    with (out / "simulation_runs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(runs[0]))
        writer.writeheader()
        writer.writerows(runs)
    with (out / "what_if_timeseries.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(series[0]))
        writer.writeheader()
        writer.writerows({key: (f"{value:.10f}" if isinstance(value, float) else value) for key, value in row.items()} for row in series)

    summary = {
        "what_if_pair_id": pair_id,
        "baseline_sim_run_id": baseline_id,
        "what_if_sim_run_id": changed_id,
        "changed_parameter": "valve_opening",
        "valve_opening_baseline": 1.0,
        "valve_opening_what_if": valve_opening,
        "hours": hours,
        "step_seconds": step_seconds,
        "steps": len(series),
        "mean_deltas": {},
    }
    delta_keys = {
        "q_in_m3_h": "delta_q_in_m3_h",
        "q_out_m3_h": "delta_q_out_m3_h",
        "p_discharge_kpa": "delta_p_discharge_kpa",
        "source_level_m": "delta_source_level_m",
        "destination_level_m": "delta_destination_level_m",
    }
    summary["mean_deltas"] = {name: sum(row[key] for row in series) / len(series) for name, key in delta_keys.items()}
    step_hours = step_seconds / 3600.0
    source_volume_delta = -sum(row["delta_q_in_m3_h"] for row in series) * step_hours
    destination_volume_delta = sum(row["delta_q_out_m3_h"] for row in series) * step_hours
    summary["tank_area_m2"] = TANK_AREA_M2
    summary["tank_volume_deltas_m3"] = {
        "source": source_volume_delta,
        "destination": destination_volume_delta,
    }
    summary["end_level_deltas_m"] = {
        "source": source_volume_delta / TANK_AREA_M2,
        "destination": destination_volume_delta / TANK_AREA_M2,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("what-if-output"))
    parser.add_argument("--valve-opening", type=float, default=0.8)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--step-seconds", type=int, default=60)
    args = parser.parse_args()
    try:
        result = run_what_if(args.out, args.valve_opening, args.hours, args.step_seconds)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
