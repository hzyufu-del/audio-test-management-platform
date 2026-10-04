"""Fail-stop orchestration for the fixed formal batch; never auto-resume."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from experiment.formal_plan import validate_formal_plan
from experiment.formal_storage import FormalStore, StorageError
from experiment.framework import ExperimentError, ROOT

FORMAL_OUTPUT = ROOT / "experiment" / "formal_runs" / "formal-v1"


class FormalExecutionError(ExperimentError):
    """Only fixed public error messages may cross the CLI boundary."""


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _workspace_gate():
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       stderr=subprocess.DEVNULL, text=True).strip()
        changes = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True,
        ).splitlines()
        for line in changes:
            path = line[3:].strip('"').replace("\\", "/")
            audit_only = (line.startswith("?? ")
                          and path.startswith(("experiment/results/", "experiment/executor_validation/"))
                          and Path(path).suffix.lower() in {".json", ".jsonl", ".txt", ".md"})
            if not audit_only:
                raise ValueError
        if len(head) != 40:
            raise ValueError
        return head
    except (OSError, ValueError, subprocess.SubprocessError):
        raise FormalExecutionError("Formal execution requires a clean committed source workspace.") from None


def _output_gate(output, *, real):
    output = Path(output)
    if real and (output != FORMAL_OUTPUT or output.resolve() != output.absolute()):
        raise FormalExecutionError("Formal output must use the fixed canonical batch directory.")
    if output.exists():
        raise FormalExecutionError(
            "partial formal experiment detected; manual recovery authorization required")
    if any(output.resolve().is_relative_to((ROOT / protected).resolve())
           for protected in ("app", "instance", "experiment/dataset", "experiment/results")):
        raise FormalExecutionError("Formal output cannot use a protected directory.")


def load_execution_settings():
    """Reached only after both explicit flags and pure preflight gates."""
    import os
    from dotenv import load_dotenv
    from config import load_ai_config

    try:
        load_dotenv(ROOT / ".env", override=False)
        config = load_ai_config()
        if config["AI_PROVIDER"] != "deepseek" or config["DEEPSEEK_THINKING_ENABLED"]:
            raise ValueError
        return {"execute": True, "ai_enabled": config["AI_ENABLED"],
                "api_key": config["DEEPSEEK_API_KEY"], "secret_key": os.getenv("SECRET_KEY", ""),
                "model": config["DEEPSEEK_MODEL"], "base_url": config["DEEPSEEK_BASE_URL"],
                "timeout_seconds": 60, "max_output_tokens": 8000,
                "max_retries": 0, "thinking": "disabled", "temperature": None,
                "temperature_sent": False, "stream": False, "validation_diagnostics": True}
    except Exception:
        raise FormalExecutionError("Formal credentials or local configuration are invalid.") from None


def _settings_gate(settings, plan):
    from experiment.adapters import _settings

    try:
        checked = _settings(settings)
        params = plan["parameters"]
        for actual, expected in [(checked["model"], params["requested_model"]),
                                 (checked["base_url"], params["base_url"]),
                                 (checked["timeout_seconds"], params["timeout_seconds"]),
                                 (checked["max_output_tokens"], params["max_output_tokens"])]:
            if actual != expected:
                raise ValueError
        if (settings.get("max_retries") != 0 or settings.get("thinking") != "disabled"
                or settings.get("temperature") is not None
                or settings.get("temperature_sent") is not False or settings.get("stream") is not False):
            raise ValueError
        return checked
    except Exception:
        raise FormalExecutionError("Formal request parameters do not match the frozen controls.") from None


def _safe(value, settings):
    from experiment.adapters import _unsafe
    from experiment.framework import _is_safe

    config = {"DEEPSEEK_API_KEY": settings.get("api_key"), "SECRET_KEY": settings.get("secret_key")}
    return _is_safe(value, settings) and not _unsafe(value, config)


def audit_output_files(output, settings, *, verified_hashes=None):
    """Final readback includes all files and actual secrets in SQLite bytes."""
    from experiment.adapters import BASELINE_PROMPT
    from app.services.test_design.prompts import TEST_DESIGN_SYSTEM_PROMPT

    sensitive = [settings.get("api_key"), settings.get("secret_key"),
                 BASELINE_PROMPT, TEST_DESIGN_SYSTEM_PROMPT]
    needles = [value.encode("utf-8") for value in sensitive if value]
    cache = verified_hashes if verified_hashes is not None else {}
    try:
        for path in Path(output).rglob("*"):
            if not path.is_file():
                continue
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if cache.get(path) == digest:
                continue
            if any(value in raw for value in needles):
                raise ValueError
            if path.suffix in {".sqlite", ".sqlite3", ".db"}:
                cache[path] = digest
                continue
            if path.suffix == ".json":
                value = json.loads(raw)
            elif path.suffix == ".jsonl":
                if not raw.endswith(b"\n"):
                    raise ValueError
                value = [json.loads(line) for line in raw.splitlines()]
            else:
                value = raw.decode("utf-8")
            if not _safe(value, settings):
                raise ValueError
            cache[path] = digest
    except (OSError, UnicodeError, ValueError, TypeError):
        raise FormalExecutionError("Formal output readback failed the integrity or credential safety gate.") from None


def _validate_result(result, task, plan):
    if not isinstance(result, dict):
        raise FormalExecutionError("Formal adapter result is invalid.")
    if result.get("failure_origin") == "framework" or result.get("status") == "framework_error":
        raise FormalExecutionError("Formal adapter reported a framework failure.")
    if (result.get("status") not in {"succeeded", "failed"} or result.get("sdk_calls") != 1
            or result.get("provider") != "deepseek"
            or result.get("requested_model") != plan["parameters"]["requested_model"]
            or result.get("requirement_hash") != task["requirement_hash"]
            or result.get("prompt_version") != plan["prompt_versions"][task["method"]]
            or result.get("prompt_hash") != plan["prompt_hashes"][task["method"]]):
        raise FormalExecutionError("Formal result does not match its frozen pair.")
    if result["status"] == "failed" and result.get("failure_origin") != "method":
        raise FormalExecutionError("Formal failure origin is unresolved.")
    if task["method"] == "proposed" and result["status"] == "succeeded":
        run_id, session_id = result.get("generation_run_id"), result.get("session_id")
        if type(run_id) is not int or type(session_id) is not int or min(run_id, session_id) < 1:
            raise FormalExecutionError("Formal Proposed association is incomplete.")
        for draft in result.get("initial_cases", []):
            if (draft.get("generation_run_id") != run_id or draft.get("session_id") != session_id
                    or draft.get("status") != "pending" or draft.get("accepted_test_case_id") is not None):
                raise FormalExecutionError("Formal Proposed draft association is invalid.")


def _manifest(plan, mode):
    manifest = json.loads(json.dumps(plan))
    manifest.update(experiment_id="formal-v1", execution_mode=mode,
                    formal_experiment=True, formal_eligible=mode == "execute",
                    provider_calls_allowed=mode == "execute", created_at=_utc(),
                    base_commit=plan["source_evidence"]["git_head"],
                    execution_order=[{k: t[k] for k in ("sequence_no", "requirement_id", "method", "attempt_no")}
                                     for t in plan["tasks"]],
                    reference_scenarios_leaked_to_provider=False,
                    experiment_design_sha256=hashlib.sha256(
                        (ROOT / "docs/experiment-design.md").read_bytes()).hexdigest())
    parameters = plan["parameters"]
    manifest.update(provider=parameters["provider"], requested_model=parameters["requested_model"],
                    endpoint_safe_identifier=parameters["endpoint_safe_identifier"],
                    max_tokens=parameters["max_output_tokens"], timeout=parameters["timeout_seconds"],
                    thinking=parameters["thinking"], temperature=None, temperature_sent=False, retry=0,
                    dataset_hash=plan["dataset_sha256"]["requirements.jsonl"],
                    reference_hash=plan["dataset_sha256"]["reference_scenarios.jsonl"])
    return manifest


def _run(plan, output, settings, adapter_factory, *, mode, dataset_dir=None):
    validate_formal_plan(plan, dataset_dir)
    _output_gate(output, real=mode == "execute")
    settings = _settings_gate(settings, plan)
    manifest = _manifest(plan, mode)
    if not _safe(manifest, settings):
        raise FormalExecutionError("Formal manifest failed the export safety gate.")
    store = FormalStore(output)
    store.initialize(manifest)
    current = None
    adapters = None
    halted = False
    incident_code = None
    verified_export_hashes = {}

    def before_call():
        if current is None:
            raise FormalExecutionError("No running formal pair is available.")
        validate_formal_plan(plan, dataset_dir)
        store.verify()
        store.record_call(current)

    try:
        adapters = adapter_factory(Path(output), settings, before_call)
        for task in plan["tasks"]:
            current = task
            validate_formal_plan(plan, dataset_dir)
            store.verify()
            evidence = {"experiment_id": manifest["experiment_id"],
                        "requirement_id": task["requirement_id"], "method": task["method"],
                        "attempt_no": 1, "requirement_hash": task["requirement_hash"],
                        "prompt_version": plan["prompt_versions"][task["method"]],
                        "prompt_hash": plan["prompt_hashes"][task["method"]],
                        "requested_model": settings["model"], "planned_order_index": task["sequence_no"],
                        "started_at": _utc(), "status": "running"}
            store.start_attempt(task, evidence)
            result = adapters.generate(task["method"], **task["input"])
            if not _safe(result, settings):
                raise FormalExecutionError("Formal export failed the credential safety gate.")
            _validate_result(result, task, plan)
            audit_output_files(output, settings, verified_hashes=verified_export_hashes)
            result = {**result, **{key: evidence[key] for key in (
                "experiment_id", "requirement_id", "method", "attempt_no", "planned_order_index")},
                "formal_experiment": True, "formal_eligible": mode == "execute",
                "execution_mode": mode, "usage_source": "provider_usage" if mode == "execute" else "offline_fixture"}
            store.finish_attempt(task, result)
            store.verify()
            audit_output_files(output, settings, verified_hashes=verified_export_hashes)
            validate_formal_plan(plan, dataset_dir)
        current = None
        validate_formal_plan(plan, dataset_dir)
        store.verify()
    except BaseException as error:
        halted = True
        incident_code = ("interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit))
                         else "formal_framework_error")
        store.fail(current, incident_code)
    finally:
        if adapters is not None:
            try:
                adapters.close()
            except BaseException:
                halted = True
                incident_code = "formal_cleanup_error"
                store.fail(current, incident_code)
    try:
        audit_output_files(output, settings)
        summary = store.summary()
    except (StorageError, OSError, ValueError):
        halted = True
        incident_code = incident_code or "formal_output_audit_error"
        store.fail(current, "formal_output_audit_error")
        summary = store.summary(verify=False)
    summary.update(experiment_id=manifest["experiment_id"], execution_mode=mode,
                   status="framework_error" if halted else "completed",
                   generation_collection_completed=not halted and summary["succeeded"] + summary["failed"] == 56,
                   human_evaluation_completed=False, formal_results_conclusion_available=False,
                   unexpected_retries=0, execution_finished_at=_utc(), incident_code=incident_code,
                   reference_scenarios_leaked_to_provider=False)
    try:
        if not _safe(summary, settings):
            raise ValueError
        store._write(Path(output) / "integrity_report.json", summary, immutable=True)
    except BaseException:
        if not _safe(summary, settings):
            # Never return tainted disk data, even on the reporting path.
            # Unknown counts remain null instead of being invented.
            summary = {"experiment_id": manifest["experiment_id"], "formal_experiment": True,
                       "execution_mode": mode, "planned_pairs": 56,
                       "actual_provider_calls": 0 if mode == "offline_fixture" else None,
                       "provider_fake_calls": None if mode == "offline_fixture" else 0,
                       "integrity_verified": False, "human_evaluation_completed": False,
                       "formal_results_conclusion_available": False}
        summary.update(status="framework_error", generation_collection_completed=False,
                       incident_code="formal_audit_write_error")
        store.fail(None, "formal_audit_write_error")
    return summary


def execute_formal(plan, *, execute=False, confirm_formal=False):
    """The only production entry: fixed output, no injected real-mode bypass."""
    if execute is not True or confirm_formal is not True:
        raise FormalExecutionError("Both explicit --execute and --confirm-formal are required.")
    validate_formal_plan(plan)
    _output_gate(FORMAL_OUTPUT, real=True)
    if _workspace_gate() != plan["source_evidence"]["git_head"]:
        raise FormalExecutionError("Formal source baseline changed.")
    settings = load_execution_settings()
    from experiment.formal_adapters import FormalAdapters
    return _run(plan, FORMAL_OUTPUT, settings, FormalAdapters, mode="execute")


def run_offline_fixture(plan, output, adapter_factory, *, dataset_dir=None):
    """Explicit test seam; no configuration loader or default real adapter."""
    if not callable(adapter_factory):
        raise FormalExecutionError("An explicit offline fixture factory is required.")
    if Path(output).resolve().is_relative_to((ROOT / "experiment/formal_runs").resolve()):
        raise FormalExecutionError("Offline fixtures cannot use the formal evidence directory.")
    settings = {"execute": True, "ai_enabled": True, "api_key": "offline-fixture-key",
                "secret_key": "offline-fixture-session", "model": "deepseek-v4-pro",
                "base_url": "https://api.deepseek.com", "timeout_seconds": 60,
                "max_output_tokens": 8000, "max_retries": 0, "thinking": "disabled",
                "temperature": None, "temperature_sent": False, "stream": False,
                "validation_diagnostics": True}
    return _run(plan, output, settings, adapter_factory, mode="offline_fixture", dataset_dir=dataset_dir)
