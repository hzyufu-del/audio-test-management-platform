"""Print the formal experiment plan only; no database or model is opened."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    from experiment.framework import ExperimentError, build_plan, load_dataset

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=ROOT / "experiment" / "dataset")
    parser.add_argument("--requirement-id", action="append")
    args = parser.parse_args(argv)
    try:
        dataset = load_dataset(args.dataset_dir, role="formal_plan")
        plan = build_plan(dataset, role="formal_plan", selected_ids=args.requirement_id)
    except ExperimentError as error:
        print(str(error), file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

