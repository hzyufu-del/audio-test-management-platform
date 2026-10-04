"""Preview the formal plan; two explicit flags are required to execute."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    from experiment.formal_plan import build_formal_plan
    from experiment.framework import ExperimentError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-formal", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = build_formal_plan()
        if not (args.execute and args.confirm_formal):
            plan = {**plan, "execute_preflight_required": True,
                    "ready_scope": "static_plan_and_executor; runtime_preflight_still_required"}
            if (ROOT / "experiment/formal_runs/formal-v1").exists():
                plan.update(ready_to_execute=False,
                            stop_reason="partial formal experiment detected; manual recovery authorization required")
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        from experiment.formal_runner import execute_formal
        result = execute_formal(plan, execute=True, confirm_formal=True)
    except ExperimentError as error:
        print(str(error), file=sys.stderr)
        return 2
    except BaseException:
        print("Formal execution stopped; preserve evidence and request manual recovery authorization.", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["generation_collection_completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
