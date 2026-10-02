"""Preview a separate Pilot by default; --execute is required for real calls."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def make_adapters(output, settings):
    from experiment.adapters import BaselineAdapter, ProposedAdapter

    baseline = BaselineAdapter(settings)
    try:
        proposed = ProposedAdapter(settings, output / "proposed.sqlite")
    except Exception:
        baseline.close()
        raise
    return {"baseline": baseline, "proposed": proposed}


def execution_settings(args):
    from dotenv import load_dotenv
    from config import load_ai_config

    load_dotenv(ROOT / ".env", override=False)
    try:
        config = load_ai_config()
    except Exception:
        from experiment.framework import ExperimentError
        raise ExperimentError("Local AI settings are invalid.") from None
    return {
        "execute": True, "ai_enabled": config["AI_ENABLED"],
        "api_key": config["DEEPSEEK_API_KEY"], "secret_key": os.getenv("SECRET_KEY", ""),
        "model": args.model or config["DEEPSEEK_MODEL"],
        "base_url": config["DEEPSEEK_BASE_URL"],
        "timeout_seconds": (args.timeout_seconds if args.timeout_seconds is not None
                            else config["AI_REQUEST_TIMEOUT_SECONDS"]),
        "max_output_tokens": (args.max_output_tokens if args.max_output_tokens is not None
                              else config["AI_MAX_OUTPUT_TOKENS"]),
        "validation_diagnostics": getattr(args, "validation_diagnostics", False),
    }


def main(argv=None):
    from experiment.framework import ExperimentError, build_plan, execute_pilot, load_dataset

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=ROOT / "experiment" / "pilot_dataset")
    parser.add_argument("--requirement-id", action="append")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--validation-diagnostics", action="store_true",
                        help="Save safe Proposed validation summaries for a new Pilot only.")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--max-output-tokens", type=int)
    args = parser.parse_args(argv)
    try:
        dataset = load_dataset(args.dataset_dir, role="pilot")
        plan = build_plan(dataset, role="pilot", selected_ids=args.requirement_id)
        if not args.execute:
            sys.stdout.reconfigure(encoding="utf-8")
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        settings = execution_settings(args)
        output_root = (ROOT / "experiment" / "pilot_runs").resolve()
        output = args.output_dir or output_root / (
            datetime.now(timezone.utc).strftime("pilot-%Y%m%dT%H%M%SZ-") + uuid4().hex[:8])
        if not output.resolve().is_relative_to(output_root) or output.resolve() == output_root:
            raise ExperimentError("Pilot output must be a new child of experiment/pilot_runs.")
        summary = execute_pilot(plan, output, make_adapters, settings, execute=True)
    except ExperimentError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        print("Pilot could not finish. Inspect its safe evidence before any new attempt.",
              file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["succeeded"] == summary["planned_attempts"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
