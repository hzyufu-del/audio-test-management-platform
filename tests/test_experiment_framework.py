import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORMAL = ROOT / "experiment" / "dataset"
PILOT = ROOT / "experiment" / "pilot_dataset"


def framework():
    return importlib.import_module("experiment.framework")


def test_formal_plan_is_balanced_and_does_not_contain_reference_answers():
    module = framework()
    dataset = module.load_dataset(FORMAL, role="formal_plan")
    plan = module.build_plan(dataset, role="formal_plan")
    assert len(plan["tasks"]) == 56
    assert plan["execution_mode"] == "dry_run"
    assert plan["formal_eligible"] is False
    assert plan["pilot_only"] is False
    assert plan["formal_experiment"] is False
    by_category = {}
    for item in plan["requirements"]:
        by_category.setdefault(item["category"], []).append(item["method_order"])
    assert all(orders == [["baseline", "proposed"], ["proposed", "baseline"]] * 2
               for orders in by_category.values())
    for pair in zip(plan["tasks"][::2], plan["tasks"][1::2]):
        assert pair[0]["input"] == pair[1]["input"]
        assert set(pair[0]["input"]) == {"title", "requirement_text"}
        assert "reference_scenarios" not in json.dumps(pair)


def test_corrupted_reference_is_rejected_before_any_execution(tmp_path):
    module = framework()
    for name in ("requirements.jsonl", "reference_scenarios.jsonl"):
        (tmp_path / name).write_bytes((FORMAL / name).read_bytes())
    path = tmp_path / "reference_scenarios.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    point = json.loads(lines[0])
    point["requirement_basis"] = "This rule does not exist."
    lines[0] = json.dumps(point)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(module.ExperimentError):
        module.load_dataset(tmp_path, role="formal_plan")


def test_pilot_has_separate_identifiers_and_no_formal_eligibility():
    module = framework()
    dataset = module.load_dataset(PILOT, role="pilot")
    plan = module.build_plan(dataset, role="pilot")
    assert len(plan["requirements"]) == 2 and len(plan["tasks"]) == 4
    assert all(r["requirement_id"].startswith("PILOT_")
               for r in plan["requirements"])
    assert plan["sample_role"] == "pilot" and not plan["formal_eligible"]
    with pytest.raises(module.ExperimentError):
        module.build_plan(dataset, role="pilot", selected_ids=["PILOT_AUTH_001"] * 2)


def test_execution_requires_explicit_gate_and_refuses_formal_plan(tmp_path):
    module = framework()
    plan = module.build_plan(module.load_dataset(PILOT, role="pilot"), role="pilot")
    invoked = []
    def factory(*args):
        return invoked.append(args)
    with pytest.raises(module.ExperimentError):
        module.execute_pilot(plan, tmp_path / "run", factory, {}, execute=False)
    assert not invoked and not (tmp_path / "run").exists()
    formal = module.build_plan(module.load_dataset(FORMAL, role="formal_plan"),
                               role="formal_plan")
    with pytest.raises(module.ExperimentError):
        module.execute_pilot(formal, tmp_path / "formal", factory, {}, execute=True)
    assert not invoked and not (tmp_path / "formal").exists()


def fake_factory(calls, outcomes=None):
    class Adapter:
        def __init__(self, method):
            self.method = method

        def generate(self, requirement):
            calls.append((requirement["requirement_id"], self.method,
                          requirement["title"], requirement["requirement_text"]))
            if outcomes and self.method in outcomes:
                result = outcomes[self.method]
                if isinstance(result, Exception):
                    raise result
                return result
            return {"status": "succeeded", "provider": "offline_fixture",
                    "returned_model": None, "prompt_tokens": None,
                    "completion_tokens": None, "total_tokens": None,
                    "latency_ms": None, "initial_text": "Demo unstructured output",
                    "initial_cases": [], "structured_output": None}

        def close(self):
            pass

    return lambda output, settings: {m: Adapter(m) for m in ("baseline", "proposed")}


def settings():
    return {"model": "demo-model", "base_url": "https://api.deepseek.com",
            "timeout_seconds": 20, "max_output_tokens": 2000,
            "api_key": "private-fixture-credential", "secret_key": "private-fixture-secret",
            "execute": True, "ai_enabled": True}


@pytest.mark.parametrize("mutation", ["extra_task", "different_input", "unsafe_id"])
def test_tampered_pilot_plan_is_rejected_before_output_or_factory(tmp_path, mutation):
    module = framework()
    plan = module.build_plan(module.load_dataset(PILOT, role="pilot"), role="pilot")
    if mutation == "extra_task":
        plan["tasks"].append(dict(plan["tasks"][0]))
    elif mutation == "different_input":
        plan["tasks"][0]["input"]["title"] = "Changed title"
    else:
        plan["requirements"][0]["requirement_id"] = "PILOT_../../outside"
    calls = []
    with pytest.raises(module.ExperimentError):
        module.execute_pilot(plan, tmp_path / "pilot", fake_factory(calls), settings(),
                             execute=True, execution_mode="offline_fixture")
    assert not calls and not (tmp_path / "pilot").exists()


def test_cli_explicit_zero_does_not_fall_back_to_config(monkeypatch):
    from argparse import Namespace
    from scripts.run_pilot import execution_settings
    import config
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(config, "load_ai_config", lambda: {
        "AI_ENABLED": True, "DEEPSEEK_API_KEY": "fixture-credential",
        "DEEPSEEK_MODEL": "demo-model", "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "AI_REQUEST_TIMEOUT_SECONDS": 20, "AI_MAX_OUTPUT_TOKENS": 2000,
    })
    result = execution_settings(Namespace(model=None, timeout_seconds=0, max_output_tokens=0))
    assert result["timeout_seconds"] == 0 and result["max_output_tokens"] == 0
    with pytest.raises(framework().ExperimentError):
        framework()._safe_parameters(result)


def test_fixture_execution_persists_started_outcomes_and_refuses_overwrite(tmp_path):
    module = framework()
    plan = module.build_plan(module.load_dataset(PILOT, role="pilot"), role="pilot")
    calls = []
    output = tmp_path / "pilot"
    summary = module.execute_pilot(plan, output, fake_factory(calls), settings(),
                                   execute=True, execution_mode="offline_fixture")
    assert len(calls) == 4 and summary["succeeded"] == 4
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["execution_mode"] == "offline_fixture"
    assert manifest["sample_role"] == "pilot" and not manifest["formal_eligible"]
    records = [json.loads(p.read_text(encoding="utf-8"))
               for p in sorted((output / "attempts").glob("*/outcome.json"))]
    assert len(records) == 4
    assert len(list((output / "attempts").glob("*/started.json"))) == 4
    assert all(r["execution_mode"] == "offline_fixture" and
               not r["formal_eligible"] and r["total_tokens"] is None for r in records)
    all_text = "".join(p.read_text(encoding="utf-8") for p in output.rglob("*")
                       if p.is_file() and p.suffix != ".sqlite")
    assert settings()["api_key"] not in all_text
    assert settings()["secret_key"] not in all_text
    with pytest.raises(module.ExperimentError):
        module.execute_pilot(plan, output, fake_factory(calls), settings(),
                             execute=True, execution_mode="offline_fixture")
    assert len(calls) == 4


def test_pilot_audit_markers_and_base_commit_are_persisted_before_calls(tmp_path, monkeypatch):
    module = framework()
    base_commit = "a" * 40
    monkeypatch.setattr(module, "_source_evidence", lambda: {
        "git_head": base_commit, "source_sha256": {}, "python_version": "fixture",
    })
    plan = module.build_plan(module.load_dataset(PILOT, role="pilot"), role="pilot")
    # Execution must use the source snapshot captured while building the plan.
    monkeypatch.setattr(module, "_source_evidence", lambda: {"git_head": "b" * 40})
    calls = []
    manifest_before_calls = []
    output = tmp_path / "pilot"

    def factory(directory, config):
        assert not calls
        manifest_before_calls.append(json.loads(
            (directory / "manifest.json").read_text(encoding="utf-8")))
        return fake_factory(calls)(directory, config)

    summary = module.execute_pilot(plan, output, factory, settings(),
                                   execute=True, execution_mode="offline_fixture")
    artifacts = [json.loads(path.read_text(encoding="utf-8"))
                 for path in sorted(output.rglob("*.json"))]
    assert len(calls) == 4 and len(artifacts) == 10
    for artifact in [plan, summary, *manifest_before_calls, *artifacts]:
        assert artifact["pilot_only"] is True
        assert artifact["formal_experiment"] is False
    assert plan["source_evidence"]["git_head"] == base_commit
    for artifact in [summary, *manifest_before_calls, *artifacts]:
        assert artifact["pilot_base_commit"] == base_commit


def test_adapter_exception_is_not_saved_or_retried_and_pair_is_preserved(tmp_path):
    module = framework()
    plan = module.build_plan(module.load_dataset(PILOT, role="pilot"), role="pilot")
    calls = []
    summary = module.execute_pilot(
        plan, tmp_path / "pilot", fake_factory(calls, {"baseline": RuntimeError(
            settings()["api_key"])}), settings(), execute=True,
        execution_mode="offline_fixture",
    )
    assert len(calls) == 4 and summary["unresolved"] == 2
    content = "".join(p.read_text(encoding="utf-8")
                      for p in (tmp_path / "pilot").rglob("*.json"))
    assert settings()["api_key"] not in content
    assert [method for _, method, _, _ in calls] == [
        "baseline", "proposed", "proposed", "baseline"]


def test_exported_secret_is_rejected_before_writing_content(tmp_path):
    module = framework()
    plan = module.build_plan(module.load_dataset(PILOT, role="pilot"), role="pilot")
    output = tmp_path / "pilot"
    calls = []
    module.execute_pilot(
        plan, output, fake_factory(calls, {"baseline": {
            "status": "succeeded", "initial_text": settings()["api_key"]}}),
        settings(), execute=True, execution_mode="offline_fixture",
    )
    text = "".join(p.read_text(encoding="utf-8")
                   for p in output.rglob("*.json"))
    assert settings()["api_key"] not in text
    assert "ExportSafetyError" in text


def test_nested_mapping_key_cannot_export_a_credential(tmp_path):
    module = framework()
    plan = module.build_plan(module.load_dataset(PILOT, role="pilot"), role="pilot")
    output = tmp_path / "pilot"
    module.execute_pilot(plan, output, fake_factory([], {"baseline": {
        "status": "succeeded", "structured_output": {settings()["api_key"]: "harmless"},
    }}), settings(), execute=True, execution_mode="offline_fixture")
    content = "".join(p.read_text(encoding="utf-8") for p in output.rglob("*.json"))
    assert settings()["api_key"] not in content
    assert "ExportSafetyError" in content


def test_rejected_content_keeps_safe_call_metadata(tmp_path):
    module = framework()
    plan = module.build_plan(module.load_dataset(PILOT, role="pilot"), role="pilot")
    output = tmp_path / "pilot"
    module.execute_pilot(plan, output, fake_factory([], {"baseline": {
        "status": "succeeded", "initial_text": settings()["api_key"],
        "prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18,
        "finish_reason": "stop", "latency_ms": 100,
        "latency_scope": "fixture", "returned_model": "demo-model",
    }}), settings(), execute=True, execution_mode="offline_fixture")
    record = json.loads(next((output / "attempts").glob("*baseline/outcome.json")).read_text(encoding="utf-8"))
    assert record["status"] == "failed" and record["initial_text"] is None
    assert record["total_tokens"] == 18 and record["latency_ms"] == 100
    assert record["returned_model"] == "demo-model" and record["finish_reason"] == "stop"


@pytest.mark.parametrize("script", ["run_pilot.py", "run_experiment.py"])
def test_cli_dry_run_works_without_credentials_and_has_no_outputs(tmp_path, script):
    import os
    env = dict(os.environ, DEEPSEEK_API_KEY="", AI_ENABLED="false",
               DATABASE_URI=f"sqlite:///{(tmp_path / 'must-not-exist.sqlite').as_posix()}")
    result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / script)],
                            cwd=tmp_path, env=env, text=True, capture_output=True,
                            encoding="utf-8", check=False)
    assert result.returncode == 0, result.stderr
    preview = json.loads(result.stdout)
    assert preview["execution_mode"] == "dry_run" and not preview["formal_eligible"]
    assert list(tmp_path.iterdir()) == []
