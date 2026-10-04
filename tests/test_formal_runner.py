"""Formal orchestration tests: temporary stores, explicit fake boundary only."""
import importlib
import importlib.util
import json
from pathlib import Path

import pytest


def runner():
    return importlib.import_module("experiment.formal_runner")


def plan():
    return importlib.import_module("experiment.formal_plan").build_formal_plan()


class FakeAdapters:
    def __init__(self, execution_plan, before_call, calls, fault=None):
        self.plan = execution_plan
        self.before_call = before_call
        self.calls = calls
        self.fault = fault

    def generate(self, method, *, title, requirement_text):
        task = self.plan["tasks"][len(self.calls)]
        assert task["input"] == {"title": title, "requirement_text": requirement_text}
        assert task["method"] == method
        self.before_call()
        self.calls.append((task["requirement_id"], method))
        if self.fault and len(self.calls) == 10:
            if self.fault in {KeyboardInterrupt, SystemExit, RuntimeError}:
                raise self.fault("private fixture exception must never be exported")
            if self.fault == "duplicate":
                self.before_call()
        status = "failed" if self.fault == "schema" and len(self.calls) == 10 else "succeeded"
        result = {
            "status": status, "failure_origin": "method" if status == "failed" else None,
            "sdk_calls": 1, "provider": "deepseek",
            "requested_model": "deepseek-v4-pro", "returned_model": "demo-response",
            "model_evidence_source": "provider_response_metadata",
            "requirement_hash": task["requirement_hash"],
            "prompt_version": self.plan["prompt_versions"][method],
            "prompt_hash": self.plan["prompt_hashes"][method],
            "initial_text": "Demo safe case" if method == "baseline" else None,
            "initial_cases": [], "structured_output": None,
            "latency_ms": 1, "prompt_tokens": 1, "completion_tokens": 2,
            "total_tokens": 3, "finish_reason": "stop",
            "started_at": "2026-10-03T00:00:00+00:00",
            "finished_at": "2026-10-03T00:00:01+00:00",
            "error_type": "AIResponseError" if status == "failed" else None,
            "error_message": "AI output failed validation." if status == "failed" else None,
        }
        if method == "proposed":
            result.update(generation_run_id=len(self.calls), session_id=len(self.calls),
                          closed_loop_validated=True)
        if self.fault == "source" and len(self.calls) == 10:
            result["requirement_hash"] = "0" * 64
        if self.fault == "secret" and len(self.calls) == 10:
            result["initial_text"] = "Authorization: Bearer fixture-private-credential-value"
        return result

    def close(self):
        pass


def factory(execution_plan, calls, fault=None):
    return lambda output, settings, before_call: FakeAdapters(execution_plan, before_call, calls, fault)


def test_formal_runner_contract_exists():
    assert importlib.util.find_spec("experiment.formal_runner") is not None


def test_all_56_fake_pairs_complete_once(tmp_path):
    module = runner()
    execution_plan = plan()
    calls = []
    summary = module.run_offline_fixture(execution_plan, tmp_path / "formal", factory(execution_plan, calls))
    assert len(calls) == len(set(calls)) == 56
    assert summary["succeeded"] == 56 and summary["not_started"] == 0
    assert summary["provider_fake_calls"] == 56
    assert summary["actual_provider_calls"] == 0
    assert summary["generation_collection_completed"] is True


def test_method_failure_at_10_continues(tmp_path):
    execution_plan = plan()
    calls = []
    summary = runner().run_offline_fixture(execution_plan, tmp_path / "formal", factory(execution_plan, calls, "schema"))
    assert len(calls) == 56
    assert summary["failed"] == 1 and summary["succeeded"] == 55
    assert summary["framework_error"] == 0


@pytest.mark.parametrize("fault", ["source", "secret", "duplicate", KeyboardInterrupt, SystemExit, RuntimeError])
def test_framework_error_or_interrupt_at_10_stops(tmp_path, fault):
    execution_plan = plan()
    calls = []
    output = tmp_path / "formal"
    summary = runner().run_offline_fixture(execution_plan, output, factory(execution_plan, calls, fault))
    assert len(calls) == 10
    assert summary["not_started"] == 46
    assert summary["framework_error"] + summary["running"] == 1
    assert summary["generation_collection_completed"] is False
    assert all("private fixture exception" not in p.read_text(encoding="utf-8") for p in output.rglob("*.json"))
    with pytest.raises(Exception, match="partial formal experiment detected"):
        runner().run_offline_fixture(execution_plan, output, factory(execution_plan, calls))
    assert len(calls) == 10


def test_writer_failure_at_10_stops_after_call(tmp_path, monkeypatch):
    from experiment.formal_storage import FormalStore
    original = FormalStore.finish_attempt
    def broken(self, task, result):
        if task["sequence_no"] == 10:
            raise OSError("private fixture write error")
        return original(self, task, result)
    monkeypatch.setattr(FormalStore, "finish_attempt", broken)
    execution_plan = plan()
    calls = []
    summary = runner().run_offline_fixture(execution_plan, tmp_path / "formal", factory(execution_plan, calls))
    assert len(calls) == 10
    assert summary["not_started"] == 46 and summary["framework_error"] == 1


def test_running_write_failure_prevents_provider(tmp_path, monkeypatch):
    from experiment.formal_storage import FormalStore
    def broken(*args):
        raise OSError("fixture cannot save running")
    monkeypatch.setattr(FormalStore, "start_attempt", broken)
    execution_plan = plan()
    calls = []
    runner().run_offline_fixture(execution_plan, tmp_path / "formal", factory(execution_plan, calls))
    assert calls == []


def test_tampered_plan_refused_before_creating_store(tmp_path):
    execution_plan = plan()
    execution_plan["tasks"][1] = execution_plan["tasks"][0]
    calls = []
    with pytest.raises(Exception):
        runner().run_offline_fixture(execution_plan, tmp_path / "formal", factory(execution_plan, calls))
    assert calls == [] and not (tmp_path / "formal").exists()


def test_dataset_change_before_request_stops_without_call(tmp_path, monkeypatch):
    module = runner()
    execution_plan = plan()
    original = module.validate_formal_plan
    count = 0
    def changed(*args, **kwargs):
        nonlocal count
        count += 1
        if count >= 2:
            raise ValueError("fixture hash changed")
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "validate_formal_plan", changed)
    calls = []
    summary = module.run_offline_fixture(execution_plan, tmp_path / "formal", factory(execution_plan, calls))
    assert calls == [] and not summary["generation_collection_completed"]


def test_real_entry_requires_both_gates_before_configuration(monkeypatch):
    module = runner()
    def forbidden():
        pytest.fail("Configuration must not be loaded without both explicit flags")
    monkeypatch.setattr(module, "load_execution_settings", forbidden)
    for execute, confirm in [(False, False), (True, False), (False, True)]:
        with pytest.raises(Exception, match="explicit"):
            module.execute_formal(plan(), execute=execute, confirm_formal=confirm)


def test_cli_default_and_missing_confirmation_are_side_effect_free(monkeypatch, capsys):
    from scripts import run_experiment
    def forbidden(*args, **kwargs):
        pytest.fail("Missing confirmation must never dispatch execution")
    monkeypatch.setattr(runner(), "execute_formal", forbidden)
    for argv in [[], ["--execute"], ["--confirm-formal"]]:
        assert run_experiment.main(argv) == 0
        manifest = json.loads(capsys.readouterr().out)
        assert manifest["formal_experiment"] is True
        assert manifest["execution_mode"] == "dry_run"
        assert manifest["provider_calls_allowed"] is False
        assert manifest["provider_calls"] == 0


def test_real_output_path_is_fixed():
    assert Path(__file__).resolve().parents[1] / "experiment/formal_runs/formal-v1" == runner().FORMAL_OUTPUT


@pytest.mark.parametrize("content", ['{"header":"Authorization: Bearer fixture-credential-value"}', '{"broken":'])
def test_final_output_scan_rejects_unsafe_or_partial_json(tmp_path, content):
    (tmp_path / "unexpected.json").write_text(content, encoding="utf-8")
    with pytest.raises(runner().FormalExecutionError):
        runner().audit_output_files(tmp_path, {"api_key": "fixture-private-key", "secret_key": ""})


def test_final_output_scan_includes_actual_values_in_binary_database(tmp_path):
    (tmp_path / "proposed.sqlite3").write_bytes(b"SQLite binary fixture\x00fixture-private-key\x00")
    with pytest.raises(runner().FormalExecutionError):
        runner().audit_output_files(tmp_path, {"api_key": "fixture-private-key", "secret_key": ""})


@pytest.mark.parametrize("target", ["extra_file", "state"])
def test_credential_tampering_at_10_stops_without_returning_secret(tmp_path, target):
    execution_plan = plan()
    calls = []
    output = tmp_path / "formal"
    def adapter_factory(directory, settings, marker):
        adapter = FakeAdapters(execution_plan, marker, calls)
        original = adapter.generate
        def generate(method, **context):
            result = original(method, **context)
            if len(calls) == 10:
                if target == "extra_file":
                    (directory / "unexpected.json").write_text(
                        json.dumps({"extra": "offline-fixture-key"}), encoding="utf-8")
                else:
                    path = directory / "state.json"
                    state = json.loads(path.read_text(encoding="utf-8"))
                    next(iter(state["pairs"].values()))["extra"] = "offline-fixture-key"
                    path.write_text(json.dumps(state), encoding="utf-8")
            return result
        adapter.generate = generate
        return adapter
    summary = runner().run_offline_fixture(execution_plan, output, adapter_factory)
    assert len(calls) == 10
    assert summary["status"] == "framework_error"
    assert "offline-fixture-key" not in json.dumps(summary)
    assert summary["incident_code"] is not None
