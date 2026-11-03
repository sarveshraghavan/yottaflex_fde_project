"""Check that the generated feature and ground-truth JSON exports parse."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    args = parser.parse_args()
    for name in ("export.json", "ground_truth.json"):
        with (args.data / name).open(encoding="utf-8") as stream:
            json.load(stream)
    print("JSON valid")


if __name__ == "__main__":
    main()
