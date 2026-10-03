"""Independent plans and durable, explicitly requested Pilot execution.

Importing this module does not import Flask, load .env or open a database.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import subprocess
from collections import Counter
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from test_design_contract import PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ("用户认证", "信息管理", "查询搜索", "文件上传", "权限管理", "订单流程", "系统设置")
RULE_FIELDS = ("business_rules", "input_constraints", "exception_conditions", "boundary_conditions")
REQUIREMENT_FIELDS = {"requirement_id", "dataset_version", "category", "title",
                      "requirement_text", *RULE_FIELDS}
REFERENCE_FIELDS = {"requirement_id", "point_id", "scenario_type",
                    "trigger_condition", "expected_behavior", "requirement_basis"}
METHODS = ("baseline", "proposed")
PILOT_VERSIONS = frozenset({"pilot-v1", "pilot-v2", "pilot-v3"})
RESULT_FIELDS = {
    "status", "provider", "requested_model", "provider_model", "returned_model",
    "model_evidence_source", "prompt_version", "prompt_hash", "requirement_hash",
    "started_at", "finished_at", "latency_ms", "latency_scope", "prompt_tokens",
    "completion_tokens", "total_tokens", "finish_reason", "input_chars",
    "output_chars", "error_type", "error_message", "error_stage",
    "initial_text", "initial_cases", "structured_output", "generation_run_id",
    "session_id", "project_id", "version_id", "schema_validation",
    "closed_loop_validated", "run_status",
}


class ExperimentError(ValueError):
    """An operational failure with a fixed, safe public message."""


def text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _jsonl(path):
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
            raise ValueError
        lines = raw.decode("utf-8").splitlines()
        if not lines or any(not line.strip() for line in lines):
            raise ValueError
        return [json.loads(line) for line in lines], hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError, ValueError):
        raise ExperimentError("Dataset JSONL is missing or invalid.") from None


def load_dataset(directory, *, role):
    if role not in {"formal_plan", "pilot"}:
        raise ExperimentError("Unsupported dataset role.")
    directory = Path(directory)
    requirements, req_hash = _jsonl(directory / "requirements.jsonl")
    references, ref_hash = _jsonl(directory / "reference_scenarios.jsonl")
    try:
        ids = set()
        versions = set()
        for item in requirements:
            if set(item) != REQUIREMENT_FIELDS:
                raise ValueError
            for key in REQUIREMENT_FIELDS - set(RULE_FIELDS):
                if not isinstance(item[key], str) or not item[key].strip():
                    raise ValueError
            identifier = item["requirement_id"]
            prefix = "REQ_" if role == "formal_plan" else "PILOT_"
            if not re.fullmatch(prefix + r"[A-Z]+_00[1-9]", identifier) or identifier in ids:
                raise ValueError
            ids.add(identifier)
            versions.add(item["dataset_version"])
            body, title = item["requirement_text"], item["title"]
            if not 200 <= len(body) <= 800 or body != body.strip():
                raise ValueError
            if not 1 <= len(title) <= 200 or title != title.strip() or "Demo" not in body:
                raise ValueError
            if item["category"] not in CATEGORIES:
                raise ValueError
            for field in RULE_FIELDS:
                rules = item[field]
                if not isinstance(rules, list) or not rules:
                    raise ValueError
                if any(not isinstance(rule, str) or not rule or rule not in body for rule in rules):
                    raise ValueError
        expected_version = "v1.0" if role == "formal_plan" else next(iter(versions), None)
        if versions != {expected_version} or (
            role == "pilot" and expected_version not in PILOT_VERSIONS
        ):
            raise ValueError
        if role == "formal_plan" and (
            len(requirements) != 28 or
            Counter(r["category"] for r in requirements) != Counter({c: 4 for c in CATEGORIES})
        ):
            raise ValueError
        if role == "pilot" and not 1 <= len(requirements) <= 3:
            raise ValueError
        by_id = {r["requirement_id"]: r for r in requirements}
        points, per_requirement = set(), {i: Counter() for i in ids}
        for point in references:
            if set(point) != REFERENCE_FIELDS or any(
                not isinstance(v, str) or not v.strip() for v in point.values()
            ):
                raise ValueError
            identifier, point_id = point["requirement_id"], point["point_id"]
            if identifier not in ids or point_id in points:
                raise ValueError
            if not re.fullmatch(re.escape(identifier) + r"_P0[1-6]", point_id):
                raise ValueError
            expected_type = ("normal", "normal", "negative", "negative", "boundary", "boundary")
            if point["scenario_type"] != expected_type[int(point_id[-1]) - 1]:
                raise ValueError
            rules = [rule for field in RULE_FIELDS for rule in by_id[identifier][field]]
            if point["requirement_basis"] not in rules:
                raise ValueError
            points.add(point_id)
            per_requirement[identifier][point["scenario_type"]] += 1
        if len(references) != len(requirements) * 6 or any(
            counts != Counter(normal=2, negative=2, boundary=2)
            for counts in per_requirement.values()
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ExperimentError("Dataset fields, identifiers or reference coverage are inconsistent.") from None
    return {"requirements": requirements, "reference_scenarios": references,
            "dataset_version": expected_version,
            "dataset_sha256": {"requirements.jsonl": req_hash, "reference_scenarios.jsonl": ref_hash}}


def _source_evidence():
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL,
            text=True, timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        revision = None
    paths = [ROOT / "config.py", ROOT / "requirements.txt", ROOT / "test_design_contract.py"]
    paths.extend((ROOT / "app").rglob("*.py"))
    paths.extend((ROOT / "experiment").glob("*.py"))
    paths.extend([ROOT / "scripts" / "run_pilot.py", ROOT / "scripts" / "run_experiment.py"])
    source = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(set(paths)) if p.is_file()}
    return {"git_head": revision, "source_sha256": source,
            "python_version": platform.python_version()}


def build_plan(dataset, *, role, selected_ids=None):
    if role not in {"formal_plan", "pilot"}:
        raise ExperimentError("Unsupported plan role.")
    version = dataset.get("dataset_version")
    allowed_versions = {"v1.0"} if role == "formal_plan" else PILOT_VERSIONS
    if not isinstance(version, str) or version not in allowed_versions:
        raise ExperimentError("Dataset version does not match the requested plan role.")
    rows = dataset["requirements"]
    requested = list(selected_ids) if selected_ids is not None else [r["requirement_id"] for r in rows]
    if not requested or len(requested) != len(set(requested)):
        raise ExperimentError("Requirement selections must be unique and nonempty.")
    by_id = {r["requirement_id"]: r for r in rows}
    if any(identifier not in by_id for identifier in requested):
        raise ExperimentError("A selected requirement does not exist.")
    if role == "pilot" and (len(requested) > 3 or any(not i.startswith("PILOT_") for i in requested)):
        raise ExperimentError("Pilot accepts at most three independent PILOT requirements.")
    if role == "formal_plan" and any(not i.startswith("REQ_") for i in requested):
        raise ExperimentError("Formal preview requires formal identifiers.")
    category_order = {category: i for i, category in enumerate(CATEGORIES)}
    # Order is based on the whole dataset, not renumbered after subset selection.
    ordered = sorted(rows, key=lambda r: (category_order[r["category"]], r["requirement_id"]))
    positions = Counter()
    planned, tasks = [], []
    for row in ordered:
        category = row["category"]
        position = positions[category]
        positions[category] += 1
        if row["requirement_id"] not in requested:
            continue
        order = list(METHODS if position % 2 == 0 else reversed(METHODS))
        # For a two-category Pilot, alternate order globally to exercise both paths.
        if role == "pilot":
            order = list(METHODS if len(planned) % 2 == 0 else reversed(METHODS))
        item = {"requirement_id": row["requirement_id"], "category": category,
                "method_order": order, "requirement_hash": text_hash(row["requirement_text"]),
                "input": {"title": row["title"], "requirement_text": row["requirement_text"]}}
        planned.append(item)
        for method in order:
            tasks.append({"sequence_no": len(tasks) + 1, "requirement_id": row["requirement_id"],
                          "method": method, "attempt_no": 1, "input": dict(item["input"]),
                          "requirement_hash": item["requirement_hash"]})
    return {"plan_version": "experiment-runner-v1", "sample_role": role,
            "execution_mode": "dry_run", "formal_eligible": False,
            "pilot_only": role == "pilot", "formal_experiment": False,
            "dataset_version": dataset["dataset_version"],
            **({"pilot_version": version} if role == "pilot" else {}),
            "dataset_sha256": dict(dataset["dataset_sha256"]),
            "requirements": planned, "tasks": tasks,
            "reference_scenarios": [p for p in dataset["reference_scenarios"]
                                    if p["requirement_id"] in requested],
            "source_evidence": _source_evidence(),
            "prompt_versions": {"baseline": "baseline-v1", "proposed": PROMPT_VERSION}}


def _safe_parameters(settings):
    if not settings.get("execute") or not settings.get("ai_enabled"):
        raise ExperimentError("Explicit execution and AI_ENABLED=true are required.")
    if not settings.get("api_key") or not settings.get("model"):
        raise ExperimentError("A local model credential and model identifier are required.")
    model, endpoint = settings["model"], settings.get("base_url", "")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", model):
        raise ExperimentError("The model identifier is invalid.")
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        raise ExperimentError("The endpoint must be a plain HTTPS endpoint.")
    timeout, tokens = settings.get("timeout_seconds"), settings.get("max_output_tokens")
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise ExperimentError("Timeout must be an integer from 1 to 120.")
    if type(tokens) is not int or not 100 <= tokens <= 8000:
        raise ExperimentError("Output budget must be an integer from 100 to 8000.")
    return {"requested_model": model, "base_url": endpoint, "timeout_seconds": timeout,
            "max_output_tokens": tokens, "thinking": "disabled", "temperature_sent": False,
            "temperature": None, "max_retries": 0, "stream": False}


def _is_safe(value, settings):
    from app.services.test_design.security import contains_forbidden_content
    config = {"DEEPSEEK_API_KEY": settings.get("api_key"), "SECRET_KEY": settings.get("secret_key")}
    def key_and_scalar_texts(item):
        if isinstance(item, dict):
            for key, nested in item.items():
                yield str(key)
                # Preserve sensitive key markers such as "Authorization":
                # while keeping every key separate from all field values.
                yield json.dumps(key, ensure_ascii=False) + ":"
                yield from key_and_scalar_texts(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                yield from key_and_scalar_texts(nested)
        elif not isinstance(item, str):
            # String values are checked in the original tree below; other
            # scalars must also be checked as they will appear in JSON.
            yield json.dumps(item, ensure_ascii=False, allow_nan=False)
    try:
        # Validate JSON compatibility without joining unrelated fields for
        # content detection (an ISO timestamp plus an INFO label is no log).
        json.dumps(value, ensure_ascii=False, allow_nan=False)
        return (not contains_forbidden_content(value, config=config)
                and not any(contains_forbidden_content(text, config=config)
                            for text in key_and_scalar_texts(value)))
    except (TypeError, ValueError):
        return False


def _write_json(path, value):
    # New files are never replaced; an interrupted file is retained for diagnosis.
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ValueError, TypeError):
        raise ExperimentError("Experiment evidence could not be saved; do not retry this attempt.") from None


def _write_templates(output, plan):
    directory = output / "evaluation"
    directory.mkdir()
    with (directory / "coverage.csv").open("x", encoding="utf-8", newline="") as stream:
        fields = ["requirement_id", "method", "content_stage", "point_id",
                  "scenario_type", "trigger_condition", "expected_behavior",
                  "requirement_basis", "reviewer_code", "judgment_kind", "covered", "reason"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for reference in plan["reference_scenarios"]:
            for method in METHODS:
                writer.writerow({**reference, "method": method, "content_stage": "initial"})
    with (directory / "human_scores.csv").open("x", encoding="utf-8", newline="") as stream:
        fields = ["requirement_id", "method", "content_stage", "reviewer_code",
                  "goal_score", "steps_score", "expected_score", "negative_score",
                  "boundary_score", "total_score", "reason"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in plan["requirements"]:
            for method in METHODS:
                writer.writerow({"requirement_id": row["requirement_id"],
                                 "method": method, "content_stage": "initial"})


def _validate_pilot_plan(plan):
    """Recheck the paired request boundary before creating any execution files."""
    try:
        rows = plan["requirements"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
            raise ValueError
        version = plan["dataset_version"]
        if version not in PILOT_VERSIONS or plan["formal_eligible"] is not False:
            raise ValueError
        # Historical v1 plans predate this explicit tag; later versions require it.
        if plan.get("pilot_version", version if version == "pilot-v1" else None) != version:
            raise ValueError
        ids, tasks = set(), []
        for index, row in enumerate(rows):
            identifier, request = row["requirement_id"], row["input"]
            if not re.fullmatch(r"PILOT_[A-Z]+_00[1-9]", identifier) or identifier in ids:
                raise ValueError
            ids.add(identifier)
            if set(request) != {"title", "requirement_text"}:
                raise ValueError
            if not isinstance(request["title"], str) or not 1 <= len(request["title"]) <= 200:
                raise ValueError
            body = request["requirement_text"]
            if not isinstance(body, str) or not 200 <= len(body) <= 800:
                raise ValueError
            if row["requirement_hash"] != text_hash(body):
                raise ValueError
            order = list(METHODS if index % 2 == 0 else reversed(METHODS))
            if row["method_order"] != order:
                raise ValueError
            for method in order:
                tasks.append({"sequence_no": len(tasks) + 1, "requirement_id": identifier,
                              "method": method, "attempt_no": 1, "input": dict(request),
                              "requirement_hash": row["requirement_hash"]})
        if plan["tasks"] != tasks:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ExperimentError("Pilot plan must contain one immutable pair per independent requirement.") from None


def execute_pilot(plan, output_dir, adapter_factory, settings, *,
                  execute=False, execution_mode="real_api"):
    if not execute or plan.get("sample_role") != "pilot":
        raise ExperimentError("Only an explicitly requested independent Pilot can execute.")
    if execution_mode not in {"real_api", "offline_fixture"}:
        raise ExperimentError("Unsupported execution mode.")
    _validate_pilot_plan(plan)
    parameters = _safe_parameters(settings)
    if not _is_safe(plan, settings) or not _is_safe(parameters, settings):
        raise ExperimentError("Input or metadata failed the experiment safety check.")
    output = Path(output_dir).resolve()
    for protected in (ROOT / "app", ROOT / "instance", ROOT / "experiment" / "dataset"):
        if output.is_relative_to(protected.resolve()):
            raise ExperimentError("Output cannot be placed in a protected project directory.")
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError:
        raise ExperimentError("A new output directory is required; existing runs cannot be resumed or overwritten.") from None
    manifest = {k: v for k, v in plan.items() if k != "reference_scenarios"}
    manifest.update(execution_mode=execution_mode, sample_role="pilot", formal_eligible=False,
                    pilot_only=True, formal_experiment=False,
                    pilot_version=plan["dataset_version"],
                    prompt_version=plan["prompt_versions"]["proposed"],
                    pilot_base_commit=plan["source_evidence"]["git_head"],
                    experiment_id=output.name, parameters=parameters,
                    safety_policy_version="existing-test-design-security",
                    validation_diagnostics_enabled=settings.get("validation_diagnostics") is True,
                    created_at=datetime.now(timezone.utc).isoformat())
    if plan["dataset_version"] == "pilot-v3":
        manifest.update(purpose="final_technical_readiness_gate",
                        base_commit=manifest["pilot_base_commit"])
    _write_json(output / "manifest.json", manifest)
    attempts = output / "attempts"
    attempts.mkdir()
    diagnostics_enabled = manifest["validation_diagnostics_enabled"]
    if diagnostics_enabled:
        (output / "audit").mkdir()
    _write_templates(output, plan)
    adapters = {}
    outcomes = Counter()
    try:
        adapters = adapter_factory(output, settings)
        if set(adapters) != set(METHODS):
            raise ExperimentError("Both independent method adapters are required.")
        for task in plan["tasks"]:
            name = f'{task["sequence_no"]:03d}_{task["requirement_id"]}_{task["method"]}'
            attempt = attempts / name
            attempt.mkdir()
            tags = {"sample_role": "pilot", "execution_mode": execution_mode,
                    "formal_eligible": False, "experiment_id": output.name,
                    "pilot_only": True, "formal_experiment": False,
                    "pilot_base_commit": manifest["pilot_base_commit"],
                    "requirement_id": task["requirement_id"], "method": task["method"],
                    "sequence_no": task["sequence_no"], "attempt_no": 1,
                    "requirement_hash": task["requirement_hash"],
                    "pilot_version": plan["dataset_version"],
                    "dataset_version": plan["dataset_version"]}
            started = {**tags, "status": "started",
                       "started_at": datetime.now(timezone.utc).isoformat(),
                       "input": task["input"]}
            _write_json(attempt / "started.json", started)
            diagnostic = None
            try:
                result = adapters[task["method"]].generate(
                    {"requirement_id": task["requirement_id"], **task["input"]})
                if not isinstance(result, dict):
                    raise TypeError
                result = dict(result)
                candidate = result.pop("validation_diagnostic", None)
                if diagnostics_enabled and task["method"] == "proposed":
                    from app.services.test_design.diagnostics import sanitize_validation_summary
                    diagnostic = sanitize_validation_summary(candidate)
                result = {key: value for key, value in result.items() if key in RESULT_FIELDS}
                if result.get("status") not in {"succeeded", "failed", "pre_call_failed", "running", "unresolved"}:
                    raise TypeError
            except Exception:
                result = {"status": "unresolved", "error_stage": "adapter",
                          "error_type": "AdapterExecutionError",
                          "error_message": "Attempt outcome requires inspection; no automatic retry.",
                          "initial_text": None, "initial_cases": [], "structured_output": None}
            if not _is_safe(result, settings):
                # Keep independently safe call evidence even if the content is withheld.
                metadata = {key: value for key, value in result.items()
                            if key not in {"initial_text", "initial_cases", "structured_output",
                                           "error_type", "error_message", "status"}
                            and _is_safe({key: value}, settings)}
                result = {**metadata, "status": "failed", "error_stage": "export",
                          "error_type": "ExportSafetyError",
                          "error_message": "Unsafe output was withheld from experiment files.",
                          "initial_text": None, "initial_cases": [], "structured_output": None}
            # Invariant tags win over any adapter metadata.
            record = {**result, **tags,
                      "usage_source": "offline_fixture" if execution_mode == "offline_fixture" else "provider_usage",
                      "prompt_tokens": result.get("prompt_tokens"),
                      "completion_tokens": result.get("completion_tokens"),
                      "total_tokens": result.get("total_tokens")}
            _write_json(attempt / "outcome.json", record)
            if diagnostic is not None:
                # Preserve request evidence first. A failed audit write stops
                # the run; callers must inspect it, never replay this request.
                identifiers = {
                    key: value if type(value) is int and 1 <= value <= 2**63 - 1 else None
                    for key in ("generation_run_id", "session_id")
                    for value in (record.get(key),)
                }
                audit = {**tags, **identifiers, "validation_summary": diagnostic}
                if not _is_safe(audit, settings):
                    raise ExperimentError("Validation audit could not be saved safely; do not retry this attempt.")
                _write_json(output / "audit" / f"{name}.validation.json", audit)
            outcomes[record["status"]] += 1
        summary = {"sample_role": "pilot", "execution_mode": execution_mode,
                   "formal_eligible": False, "planned_attempts": len(plan["tasks"]),
                   "pilot_only": True, "formal_experiment": False,
                   "pilot_version": plan["dataset_version"],
                   "pilot_base_commit": manifest["pilot_base_commit"],
                   "recorded_outcomes": sum(outcomes.values()),
                   **{name: outcomes[name] for name in ("succeeded", "failed", "pre_call_failed", "running", "unresolved")},
                   "evaluation_status": "not_evaluated"}
        _write_json(output / "summary.json", summary)
        return summary
    finally:
        for adapter in adapters.values():
            with suppress(Exception):
                adapter.close()
