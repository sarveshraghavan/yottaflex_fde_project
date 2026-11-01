"""Generate the network twice and compare written row counts and SHA-256 hashes."""
import argparse
import json
import tempfile
from pathlib import Path

try:
    from src.network_expansion import write_network
except ModuleNotFoundError:
    from network_expansion import write_network


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261022)
    parser.add_argument("--facilities", type=int, default=3)
    parser.add_argument("--pumps", type=int, default=20)
    parser.add_argument("--tanks", type=int, default=30)
    parser.add_argument("--valves", type=int, default=60)
    parser.add_argument("--telemetry-rows", type=int, default=100000)
    parser.add_argument("--time-steps", type=int)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="network-repro-") as tmp:
        root = Path(tmp)
        left, right = root / "first", root / "second"
        kwargs = {"pump_count": args.pumps, "tank_count": args.tanks, "valve_count": args.valves, "telemetry_rows_target": args.telemetry_rows, "time_steps": args.time_steps}
        write_network(left, seed=args.seed, facility_count=args.facilities, **kwargs)
        write_network(right, seed=args.seed, facility_count=args.facilities, **kwargs)
        first = json.loads((left / "source_manifest.json").read_text(encoding="utf-8"))
        second = json.loads((right / "source_manifest.json").read_text(encoding="utf-8"))
        same_hashes = first["files_sha256"] == second["files_sha256"]
        same_counts = first["csv_row_counts"] == second["csv_row_counts"]
        result = {"reproducible": same_hashes and same_counts, "same_row_counts": same_counts, "same_sha256": same_hashes, "output_file_count": len(first["files_sha256"]), "csv_file_count": len(first["csv_row_counts"]), "telemetry_rows": first["csv_row_counts"].get("telemetry.csv"), "sql_seed_sha256_equal": first["files_sha256"].get("seed.sql") == second["files_sha256"].get("seed.sql"), "feature_json_sha256_equal": first["files_sha256"].get("export.json") == second["files_sha256"].get("export.json"), "truth_json_sha256_equal": first["files_sha256"].get("ground_truth.json") == second["files_sha256"].get("ground_truth.json"), "seed": args.seed, "scale": {"facilities": args.facilities, "pumps": args.pumps, "tanks": args.tanks, "valves": args.valves}}
        print(json.dumps(result, indent=2, sort_keys=True))
        if not result["reproducible"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
