import unittest
import json
from pathlib import Path

from src.line_physics import Line, simulate, solve_line


class LinePhysicsTests(unittest.TestCase):
    def setUp(self):
        self.line = Line()
        self.rows = {name: simulate(self.line, name, hours=1) for name in ("baseline", "leak", "blockage")}
        self.mean = {name: {key: sum(r[key] for r in rows) / len(rows) for key in ("q_in_m3_h", "q_out_m3_h", "q_leak_m3_h", "h_discharge_m", "p_discharge_kpa_gauge", "mass_balance_residual_m3_h", "measured_flow_residual_m3_h")} for name, rows in self.rows.items()}

    def test_baseline_closes_mass_balance(self):
        self.assertLess(abs(self.mean["baseline"]["mass_balance_residual_m3_h"]), 1e-6)

    def test_leak_signature_and_mass_balance(self):
        base, leak = self.mean["baseline"], self.mean["leak"]
        self.assertLess(leak["q_out_m3_h"], base["q_out_m3_h"])
        self.assertGreater(leak["q_in_m3_h"], base["q_in_m3_h"])
        self.assertGreater(leak["q_leak_m3_h"], 0)
        self.assertAlmostEqual(leak["measured_flow_residual_m3_h"], leak["q_leak_m3_h"], places=6)
        self.assertLess(leak["p_discharge_kpa_gauge"], base["p_discharge_kpa_gauge"])

    def test_blockage_signature(self):
        base, blocked = self.mean["baseline"], self.mean["blockage"]
        self.assertLess(blocked["q_in_m3_h"], base["q_in_m3_h"])
        self.assertLess(blocked["q_out_m3_h"], base["q_out_m3_h"])
        self.assertGreater(blocked["p_discharge_kpa_gauge"], base["p_discharge_kpa_gauge"])
        self.assertEqual(blocked["q_leak_m3_h"], 0)

    def test_fault_magnitudes_are_material_but_not_extreme(self):
        base = self.mean["baseline"]["q_out_m3_h"]
        for scenario in ("leak", "blockage"):
            change = abs(self.mean[scenario]["q_out_m3_h"] - base) / base
            self.assertGreater(change, 0.01)
            self.assertLess(change, 0.50)

    def test_tank_bounds_and_determinism(self):
        first = simulate(self.line, "baseline", hours=1)
        second = simulate(self.line, "baseline", hours=1)
        self.assertEqual(first, second)
        for rows in self.rows.values():
            self.assertTrue(all(not r["event"] for r in rows))
            self.assertTrue(all(r["source_level_m"] >= 0 and r["destination_level_m"] >= 0 for r in rows))

    def test_leak_changes_tank_trajectories_vs_baseline(self):
        base, leak = self.rows["baseline"], self.rows["leak"]
        self.assertLess(leak[-1]["source_level_m"], base[-1]["source_level_m"])
        self.assertLess(leak[-1]["destination_level_m"], base[-1]["destination_level_m"])
        self.assertLess(leak[-1]["q_out_m3_h"], leak[0]["q_out_m3_h"])

    def test_pump_degradation_and_blockage_have_opposite_pressure_signs(self):
        base = self.mean["baseline"]
        degraded = simulate(self.line, "pump_degradation", hours=1)
        blocked = self.rows["blockage"]
        mean_pressure = lambda rows: sum(r["p_discharge_kpa_gauge"] for r in rows) / len(rows)
        mean_flow = lambda rows: sum(r["q_out_m3_h"] for r in rows) / len(rows)
        self.assertLess(mean_pressure(degraded), base["p_discharge_kpa_gauge"])
        self.assertLess(mean_flow(degraded), base["q_out_m3_h"])
        self.assertGreater(mean_pressure(blocked), base["p_discharge_kpa_gauge"])

    def test_partial_valve_reduces_flow(self):
        partial = simulate(self.line, "valve_partial", hours=1)
        mean_flow = sum(r["q_out_m3_h"] for r in partial) / len(partial)
        self.assertLess(mean_flow, self.mean["baseline"]["q_out_m3_h"])
        mean_valve_drop = sum(r["p_valve_drop_kpa"] for r in partial) / len(partial)
        base_valve_drop = sum(r["p_valve_drop_kpa"] for r in self.rows["baseline"]) / len(self.rows["baseline"])
        mean_pipe_drop = sum(r["p_pipe_drop_kpa"] for r in partial) / len(partial)
        base_pipe_drop = sum(r["p_pipe_drop_kpa"] for r in self.rows["baseline"]) / len(self.rows["baseline"])
        self.assertGreater(mean_valve_drop, base_valve_drop)
        self.assertLess(mean_pipe_drop, base_pipe_drop)

    def test_blockage_increases_pipe_drop(self):
        blocked = self.rows["blockage"]
        self.assertGreater(sum(r["p_pipe_drop_kpa"] for r in blocked), sum(r["p_pipe_drop_kpa"] for r in self.rows["baseline"]))

    def test_small_leak_vs_degradation_under_combined_sensor_noise(self):
        baseline = simulate(self.line, "baseline", hours=1)
        small_leak = simulate(Line(leak_cl_m3h_per_sqrt_m=0.5), "baseline", hours=1)
        small_degradation = simulate(Line(h0_m=self.line.h0_m * 0.99), "baseline", hours=1)
        base_flow = sum(r["q_in_m3_h"] for r in baseline) / len(baseline)
        gap = sum(r["q_in_m3_h"] - r["q_out_m3_h"] for r in small_leak) / len(small_leak)
        paired_noise = (2 ** 0.5) * 0.02 * base_flow
        self.assertGreater(gap, 0)
        self.assertLess(gap, paired_noise)  # Direction differs, but this small case is not noise-robust.
        self.assertEqual(sum(r["q_in_m3_h"] - r["q_out_m3_h"] for r in small_degradation), 0)

    def test_golden_means_are_stable(self):
        fixture = Path(__file__).parent / "fixtures" / "line_physics_golden.json"
        golden = json.loads(fixture.read_text(encoding="utf-8"))
        for scenario, expected in golden.items():
            rows = simulate(self.line, scenario, hours=24)
            for key, value in expected.items():
                observed = sum(row[key] for row in rows) / len(rows)
                self.assertAlmostEqual(observed, value, places=6, msg=f"{scenario}.{key}")

    def test_solver_handles_closed_valve_and_insufficient_head(self):
        closed = solve_line(Line(valve_open=0.0), 30.0, 20.0)
        low_head = solve_line(Line(), 20.0, 80.0)
        self.assertEqual(closed["q_in"], 0.0)
        self.assertEqual(low_head["q_in"], 0.0)


if __name__ == "__main__":
    unittest.main()
