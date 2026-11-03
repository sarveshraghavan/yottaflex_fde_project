"""Small deterministic pump-line model for comparing baseline and fault cases.

All flows are m3/h, heads are m, tank volume is m3, and each step is one minute.
This is a transparent prototype model, not a calibrated hydraulic solver.
"""
import argparse
import csv
import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

TANK_AREA_M2 = 2_000.0


@dataclass(frozen=True)
class Line:
    h0_m: float = 50.0
    pump_a_m_per_m3h2: float = 0.0015
    pipe_k_m_per_m3h2: float = 0.0010
    valve_k_m_per_m3h2: float = 0.0005
    valve_open: float = 1.0
    leak_cl_m3h_per_sqrt_m: float = 0.0
    leak_pos: float = 0.5


@dataclass(frozen=True)
class Tank:
    capacity_m3: float
    area_m2: float
    elevation_m: float
    volume_m3: float

    @property
    def level_m(self):
        return self.volume_m3 / self.area_m2

    @property
    def head_m(self):
        return self.elevation_m + self.level_m


def solve_line(line: Line, source_head_m: float, destination_head_m: float):
    """Solve the steady line operating point using a bracketed bisection method."""
    def stopped(discharge_head):
        return {"q_in": 0.0, "q_out": 0.0, "q_leak": 0.0, "h_discharge": discharge_head, "valve_drop_m": 0.0, "pipe_drop_m": 0.0}

    if line.h0_m <= 0 or line.valve_open < 0.01 or source_head_m <= 0:
        return stopped(source_head_m)
    if not 0 <= line.leak_pos <= 1 or line.leak_cl_m3h_per_sqrt_m < 0:
        raise ValueError("Leak position must be in [0, 1] and leak coefficient nonnegative")

    valve_k = line.valve_k_m_per_m3h2 / line.valve_open**2
    k_up = valve_k + line.leak_pos * line.pipe_k_m_per_m3h2
    k_down = (1.0 - line.leak_pos) * line.pipe_k_m_per_m3h2
    static = destination_head_m - source_head_m

    def components(q_in):
        pump_head = max(line.h0_m - line.pump_a_m_per_m3h2 * q_in**2, 0.0)
        leak_head = max(pump_head - k_up * q_in**2, 0.0)
        q_leak = line.leak_cl_m3h_per_sqrt_m * math.sqrt(leak_head)
        q_out = max(q_in - q_leak, 0.0)
        discharge = source_head_m + pump_head
        valve_drop = valve_k * q_in**2
        pipe_drop = line.leak_pos * line.pipe_k_m_per_m3h2 * q_in**2 + (1.0 - line.leak_pos) * line.pipe_k_m_per_m3h2 * q_out**2
        residual = pump_head - k_up * q_in**2 - k_down * q_out**2 - static
        return q_out, q_leak, discharge, residual, valve_drop, pipe_drop

    def residual(q):
        return components(q)[3]

    # Include the static head offset so the upper bound still brackets flow when
    # the destination tank is below the source tank.
    lo, hi = 0.0, math.sqrt(max(line.h0_m - static, 0.0) / max(line.pump_a_m_per_m3h2, 1e-15))
    if residual(lo) <= 0:
        return stopped(source_head_m + line.h0_m)
    if residual(hi) > 0:  # Bracket defensively even for unusual parameter combinations.
        return stopped(source_head_m + line.h0_m)
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if residual(mid) > 0:
            lo = mid
        else:
            hi = mid
    q_in = (lo + hi) / 2.0
    q_out, q_leak, discharge, _, valve_drop, pipe_drop = components(q_in)
    return {"q_in": q_in, "q_out": q_out, "q_leak": q_leak, "h_discharge": discharge, "valve_drop_m": valve_drop, "pipe_drop_m": pipe_drop}


def simulate(line: Line, scenario: str, hours=24, step_seconds=60):
    """Run one scenario from shared initial conditions and return process truth rows."""
    if scenario not in {"baseline", "leak", "blockage", "pump_degradation", "valve_partial"}:
        raise ValueError(f"Unknown scenario: {scenario}")
    if hours <= 0 or step_seconds <= 0:
        raise ValueError("hours and step_seconds must be positive")
    if scenario == "leak":
        line = replace(line, leak_cl_m3h_per_sqrt_m=5.0, leak_pos=0.5)
    elif scenario == "blockage":
        line = replace(line, pipe_k_m_per_m3h2=line.pipe_k_m_per_m3h2 * 3.0)
    elif scenario == "pump_degradation":
        line = replace(line, h0_m=line.h0_m * 0.90)
    elif scenario == "valve_partial":
        line = replace(line, valve_open=0.65)

    source = Tank(capacity_m3=100_000, area_m2=TANK_AREA_M2, elevation_m=0, volume_m3=60_000)
    destination = Tank(capacity_m3=100_000, area_m2=TANK_AREA_M2, elevation_m=0, volume_m3=56_000)
    dt_hours = step_seconds / 3600.0
    steps = hours * 3600 // step_seconds
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for step in range(int(steps)):
        result = solve_line(line, source.head_m, destination.head_m)
        source_next = source.volume_m3 - result["q_in"] * dt_hours
        destination_next = destination.volume_m3 + result["q_out"] * dt_hours
        event = ""
        if source_next < 0:
            source_next, event = 0.0, "source_tank_empty"
        if destination_next > destination.capacity_m3:
            destination_next, event = destination.capacity_m3, "destination_tank_overflow"
        source2 = replace(source, volume_m3=source_next)
        destination2 = replace(destination, volume_m3=destination_next)
        # Process closure includes the explicitly modeled leak; observed end-flow difference exposes it.
        mass_residual = result["q_in"] - result["q_out"] - result["q_leak"]
        measured_residual = result["q_in"] - result["q_out"]
        rows.append({
            "timestamp_utc": (start + timedelta(seconds=step * step_seconds)).isoformat().replace("+00:00", "Z"),
            "scenario": scenario,
            "q_in_m3_h": result["q_in"], "q_out_m3_h": result["q_out"], "q_leak_m3_h": result["q_leak"],
            "h_discharge_m": result["h_discharge"], "p_discharge_kpa_gauge": (result["h_discharge"] - source.head_m) * 9.81,
            "p_valve_inlet_kpa_gauge": (result["h_discharge"] - source.head_m) * 9.81,
            "p_valve_outlet_kpa_gauge": (result["h_discharge"] - source.head_m - result["valve_drop_m"]) * 9.81,
            "p_valve_drop_kpa": result["valve_drop_m"] * 9.81,
            "p_pipe_inlet_kpa_gauge": (result["h_discharge"] - source.head_m - result["valve_drop_m"]) * 9.81,
            "p_pipe_outlet_kpa_gauge": (result["h_discharge"] - source.head_m - result["valve_drop_m"] - result["pipe_drop_m"]) * 9.81,
            "p_pipe_drop_kpa": result["pipe_drop_m"] * 9.81,
            "source_level_m": source.level_m, "destination_level_m": destination.level_m,
            "mass_balance_residual_m3_h": mass_residual,
            "measured_flow_residual_m3_h": measured_residual,
            "event": event,
        })
        source, destination = source2, destination2
    return rows


def write_results(out: Path, hours=24, step_seconds=60, noise_floor_pct=2.0):
    out.mkdir(parents=True, exist_ok=True)
    base_line = Line()
    all_rows = []
    scenarios = ("baseline", "leak", "blockage", "pump_degradation", "valve_partial")
    for scenario in scenarios:
        all_rows.extend(simulate(base_line, scenario, hours, step_seconds))
    fields = list(all_rows[0])
    with (out / "line_physics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: (f"{v:.10f}" if isinstance(v, float) else v) for k, v in row.items()})
    summaries = {}
    for scenario in scenarios:
        rows = [r for r in all_rows if r["scenario"] == scenario]
        summaries[scenario] = {key: sum(r[key] for r in rows) / len(rows) for key in ("q_in_m3_h", "q_out_m3_h", "q_leak_m3_h", "h_discharge_m", "p_discharge_kpa_gauge", "p_valve_outlet_kpa_gauge", "p_valve_drop_kpa", "p_pipe_drop_kpa", "mass_balance_residual_m3_h", "measured_flow_residual_m3_h")}
        summaries[scenario].update({
            "q_in_start_m3_h": rows[0]["q_in_m3_h"], "q_in_end_m3_h": rows[-1]["q_in_m3_h"],
            "q_out_start_m3_h": rows[0]["q_out_m3_h"], "q_out_end_m3_h": rows[-1]["q_out_m3_h"],
            "source_level_start_m": rows[0]["source_level_m"], "source_level_end_m": rows[-1]["source_level_m"],
            "destination_level_start_m": rows[0]["destination_level_m"], "destination_level_end_m": rows[-1]["destination_level_m"],
        })
    baseline = [r for r in all_rows if r["scenario"] == "baseline"]
    dynamics = {}
    for scenario in scenarios[1:]:
        rows = [r for r in all_rows if r["scenario"] == scenario]
        dynamics[scenario] = {
            "extra_source_level_drop_vs_baseline_m": (baseline[-1]["source_level_m"] - baseline[0]["source_level_m"]) - (rows[-1]["source_level_m"] - rows[0]["source_level_m"]),
            "destination_level_rise_difference_vs_baseline_m": (rows[-1]["destination_level_m"] - rows[0]["destination_level_m"]) - (baseline[-1]["destination_level_m"] - baseline[0]["destination_level_m"]),
            "end_inflow_difference_vs_baseline_m3_h": rows[-1]["q_in_m3_h"] - baseline[-1]["q_in_m3_h"],
            "end_outflow_difference_vs_baseline_m3_h": rows[-1]["q_out_m3_h"] - baseline[-1]["q_out_m3_h"],
        }
    leak_sensitivity = {}
    leak_coefficients = (0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 5.0)
    paired_noise_limit = math.sqrt(2.0) * noise_floor_pct / 100.0 * summaries["baseline"]["q_in_m3_h"]
    for coefficient in leak_coefficients:
        rows = simulate(replace(base_line, leak_cl_m3h_per_sqrt_m=coefficient, leak_pos=0.5), "baseline", hours, step_seconds)
        avg_qin = sum(r["q_in_m3_h"] for r in rows) / len(rows)
        avg_qout = sum(r["q_out_m3_h"] for r in rows) / len(rows)
        avg_leak = sum(r["q_leak_m3_h"] for r in rows) / len(rows)
        leak_sensitivity[str(coefficient)] = {
            "mean_leak_flow_m3_h": avg_leak,
            "mean_outflow_reduction_pct": 100.0 * (summaries["baseline"]["q_out_m3_h"] - avg_qout) / summaries["baseline"]["q_out_m3_h"],
            "mean_inflow_change_pct": 100.0 * (avg_qin - summaries["baseline"]["q_in_m3_h"]) / summaries["baseline"]["q_in_m3_h"],
            "mean_discharge_pressure_change_kpa": sum(r["p_discharge_kpa_gauge"] for r in rows) / len(rows) - summaries["baseline"]["p_discharge_kpa_gauge"],
            "signals_above_assumed_noise_floor": {
                "inlet_flow": abs(100.0 * (avg_qin - summaries["baseline"]["q_in_m3_h"]) / summaries["baseline"]["q_in_m3_h"]) > noise_floor_pct,
                "outlet_flow": abs(100.0 * (avg_qout - summaries["baseline"]["q_out_m3_h"]) / summaries["baseline"]["q_out_m3_h"]) > noise_floor_pct,
                "discharge_pressure": abs(100.0 * (sum(r["p_discharge_kpa_gauge"] for r in rows) / len(rows) - summaries["baseline"]["p_discharge_kpa_gauge"]) / summaries["baseline"]["p_discharge_kpa_gauge"]) > noise_floor_pct,
                "paired_flow_difference": avg_leak > paired_noise_limit,
            },
            "paired_flow_difference_m3_h": avg_leak,
            "assumed_paired_flow_noise_limit_m3_h": paired_noise_limit,
        }
    blockage_sensitivity = {}
    blockage_factors = (1.1, 1.25, 1.5, 2.0, 3.0)
    for factor in blockage_factors:
        rows = simulate(replace(base_line, pipe_k_m_per_m3h2=base_line.pipe_k_m_per_m3h2 * factor), "baseline", hours, step_seconds)
        means = {key: sum(r[key] for r in rows) / len(rows) for key in ("q_in_m3_h", "q_out_m3_h", "p_discharge_kpa_gauge", "p_pipe_drop_kpa", "p_valve_drop_kpa")}
        blockage_sensitivity[str(factor)] = {
            "mean_inflow_change_pct": 100.0 * (means["q_in_m3_h"] - summaries["baseline"]["q_in_m3_h"]) / summaries["baseline"]["q_in_m3_h"],
            "mean_outflow_change_pct": 100.0 * (means["q_out_m3_h"] - summaries["baseline"]["q_out_m3_h"]) / summaries["baseline"]["q_out_m3_h"],
            "mean_discharge_pressure_change_pct": 100.0 * (means["p_discharge_kpa_gauge"] - summaries["baseline"]["p_discharge_kpa_gauge"]) / summaries["baseline"]["p_discharge_kpa_gauge"],
            "mean_pipe_drop_change_pct": 100.0 * (means["p_pipe_drop_kpa"] - summaries["baseline"]["p_pipe_drop_kpa"]) / summaries["baseline"]["p_pipe_drop_kpa"],
            "mean_valve_drop_change_pct": 100.0 * (means["p_valve_drop_kpa"] - summaries["baseline"]["p_valve_drop_kpa"]) / summaries["baseline"]["p_valve_drop_kpa"],
            "signals_above_assumed_noise_floor": {
                "inlet_flow": abs(100.0 * (means["q_in_m3_h"] - summaries["baseline"]["q_in_m3_h"]) / summaries["baseline"]["q_in_m3_h"]) > noise_floor_pct,
                "outlet_flow": abs(100.0 * (means["q_out_m3_h"] - summaries["baseline"]["q_out_m3_h"]) / summaries["baseline"]["q_out_m3_h"]) > noise_floor_pct,
                "discharge_pressure": abs(100.0 * (means["p_discharge_kpa_gauge"] - summaries["baseline"]["p_discharge_kpa_gauge"]) / summaries["baseline"]["p_discharge_kpa_gauge"]) > noise_floor_pct,
            },
        }
    tau = {
        "assumed_noise_floor_pct": noise_floor_pct,
        "paired_flow_noise_limit_m3_h": paired_noise_limit,
        "paired_flow_noise_model": "Independent inlet and outlet sensor noise; differential standard deviation = sqrt(2) times the single-sensor noise, each expressed as a percent of nominal flow.",
        "interpretation": "Illustrative process-signal cutoff only; crossing intervals are bounded by adjacent tested grid points. Replace with measured sensor-noise distributions before claiming detectability.",
        "smallest_leak_coefficient_above_floor_by_signal": {},
        "smallest_blockage_factor_above_floor_by_signal": {},
        "leak_crossing_interval_by_signal": {},
        "blockage_crossing_interval_by_signal": {},
    }
    def crossing_interval(sweep, signal):
        ordered = list(sweep.items())
        for index, (parameter, result) in enumerate(ordered):
            if result["signals_above_assumed_noise_floor"][signal]:
                if index == 0:
                    return {"status": "at_or_below_tested_minimum", "tested_minimum": float(parameter), "upper_inclusive": float(parameter)}
                return {"status": "crossing_bracketed", "lower_exclusive": float(ordered[index - 1][0]), "upper_inclusive": float(parameter)}
        return {"status": "not_crossed_in_grid", "tested_maximum": float(ordered[-1][0])}

    for signal in ("inlet_flow", "outlet_flow", "discharge_pressure", "paired_flow_difference"):
        tau["smallest_leak_coefficient_above_floor_by_signal"][signal] = next((float(k) for k, v in leak_sensitivity.items() if v["signals_above_assumed_noise_floor"][signal]), None)
        tau["leak_crossing_interval_by_signal"][signal] = crossing_interval(leak_sensitivity, signal)
    for signal in ("inlet_flow", "outlet_flow", "discharge_pressure"):
        tau["smallest_blockage_factor_above_floor_by_signal"][signal] = next((float(k) for k, v in blockage_sensitivity.items() if v["signals_above_assumed_noise_floor"][signal]), None)
        tau["blockage_crossing_interval_by_signal"][signal] = crossing_interval(blockage_sensitivity, signal)

    degradation_sensitivity = {}
    for h0_factor in (0.99, 0.98, 0.95, 0.90):
        rows = simulate(replace(base_line, h0_m=base_line.h0_m * h0_factor), "baseline", hours, step_seconds)
        mean_flow = sum(r["q_out_m3_h"] for r in rows) / len(rows)
        mean_pressure = sum(r["p_discharge_kpa_gauge"] for r in rows) / len(rows)
        degradation_sensitivity[str(h0_factor)] = {
            "mean_outflow_change_pct": 100.0 * (mean_flow - summaries["baseline"]["q_out_m3_h"]) / summaries["baseline"]["q_out_m3_h"],
            "mean_discharge_pressure_change_pct": 100.0 * (mean_pressure - summaries["baseline"]["p_discharge_kpa_gauge"]) / summaries["baseline"]["p_discharge_kpa_gauge"],
            "paired_flow_difference_m3_h": 0.0,
        }

    separation = {}
    for coefficient in leak_coefficients:
        item = leak_sensitivity[str(coefficient)]
        separation[str(coefficient)] = {
            "leak_outflow_change_pct": item["mean_outflow_reduction_pct"] * -1.0,
            "leak_pressure_change_kpa": item["mean_discharge_pressure_change_kpa"],
            "paired_flow_gap_m3_h": item["paired_flow_difference_m3_h"],
            "paired_gap_snr": item["paired_flow_difference_m3_h"] / paired_noise_limit if paired_noise_limit else None,
            "paired_gap_clears_assumed_noise": item["signals_above_assumed_noise_floor"]["paired_flow_difference"],
            "interpretation": "Leak/degradation separation by the paired-flow gap is not noise-robust unless paired_gap_clears_assumed_noise is true.",
        }
    summaries["dynamics_vs_baseline"] = dynamics
    summaries["leak_sensitivity"] = leak_sensitivity
    summaries["blockage_sensitivity"] = blockage_sensitivity
    summaries["pump_degradation_sensitivity"] = degradation_sensitivity
    summaries["leak_vs_degradation_at_small_sizes"] = separation
    summaries["tau_estimate"] = tau
    summaries["interpretation"] = {
        "mass_balance_residual": "Algebraic line-flow closure (q_in - q_out - q_leak); it is zero by the solver bookkeeping and does not independently validate hydraulic realism.",
        "sensor_noise": "Not modeled; sensitivity values are process-signal changes only and do not establish detectability under noisy sensors.",
    }
    (out / "line_physics_summary.json").write_text(__import__("json").dumps(summaries, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("line-physics-preview"))
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--step-seconds", type=int, default=60)
    parser.add_argument("--noise-floor-pct", type=float, default=2.0, help="Illustrative process-signal cutoff; replace with measured sensor noise")
    args = parser.parse_args()
    if args.noise_floor_pct < 0:
        parser.error("--noise-floor-pct cannot be negative")
    summary = write_results(args.out, args.hours, args.step_seconds, args.noise_floor_pct)
    scenarios = ("baseline", "leak", "blockage", "pump_degradation", "valve_partial")
    base, leak, blockage = (summary[x] for x in ("baseline", "leak", "blockage"))
    degradation, valve_partial = summary["pump_degradation"], summary["valve_partial"]
    checks = {
        "baseline_residual_below_1e-6": abs(base["mass_balance_residual_m3_h"]) < 1e-6,
        "leak_outflow_down": leak["q_out_m3_h"] < base["q_out_m3_h"],
        "leak_inflow_slightly_up": leak["q_in_m3_h"] > base["q_in_m3_h"],
        "leak_flow_positive": leak["q_leak_m3_h"] > 0,
        "leak_measured_residual_matches_leak": abs(leak["measured_flow_residual_m3_h"] - leak["q_leak_m3_h"]) < 1e-6,
        "blockage_flow_down": blockage["q_in_m3_h"] < base["q_in_m3_h"] and blockage["q_out_m3_h"] < base["q_out_m3_h"],
        "blockage_pressure_up": blockage["p_discharge_kpa_gauge"] > base["p_discharge_kpa_gauge"],
        "fault_signatures_separable": leak["p_discharge_kpa_gauge"] < base["p_discharge_kpa_gauge"] < blockage["p_discharge_kpa_gauge"],
        "pump_degradation_pressure_down": degradation["p_discharge_kpa_gauge"] < base["p_discharge_kpa_gauge"],
        "pump_degradation_flow_down": degradation["q_out_m3_h"] < base["q_out_m3_h"],
        "degradation_distinct_from_blockage_by_pressure": degradation["p_discharge_kpa_gauge"] < base["p_discharge_kpa_gauge"] < blockage["p_discharge_kpa_gauge"],
        "partial_valve_flow_down": valve_partial["q_out_m3_h"] < base["q_out_m3_h"],
        "partial_valve_drop_up": valve_partial["p_valve_drop_kpa"] > base["p_valve_drop_kpa"],
        "blockage_pipe_drop_up": blockage["p_pipe_drop_kpa"] > base["p_pipe_drop_kpa"],
        "valve_vs_blockage_pressure_locations_distinguish": valve_partial["p_valve_drop_kpa"] > base["p_valve_drop_kpa"] and blockage["p_pipe_drop_kpa"] > base["p_pipe_drop_kpa"],
        "effects_in_plausible_range": 0.01 < (base["q_out_m3_h"] - leak["q_out_m3_h"]) / base["q_out_m3_h"] < 0.50 and 0.01 < (base["q_out_m3_h"] - blockage["q_out_m3_h"]) / base["q_out_m3_h"] < 0.50,
        "tank_limits_respected": all(not r["event"] for scenario in scenarios for r in simulate(Line(), scenario, args.hours, args.step_seconds)),
    }
    print(__import__("json").dumps({"checks": checks, "summary": summary}, indent=2, sort_keys=True))
    (args.out / "line_physics_checks.json").write_text(__import__("json").dumps(checks, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not all(checks.values()):
        raise SystemExit("Physics prototype failed one or more checks")


if __name__ == "__main__":
    main()
