"""Offline adapter contracts: no real transport, and only tmp_path databases."""

import importlib
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from test_design_contract import PROMPT_VERSION


SETTINGS = {
    "execute": True, "ai_enabled": True, "api_key": "demo-private-key",
    "secret_key": "demo-session-private", "model": "demo-request-model",
    "base_url": "https://api.deepseek.com", "timeout_seconds": 5,
    "max_output_tokens": 1200,
}
REQUIREMENT = {
    "requirement_id": "REQ_AUTH_001", "title": "Demo login requirement",
    "requirement_text": "Demo virtual login: require an enabled sample account and matching input.",
}
PAYLOAD = {
    "summary": "Demo sample design requiring human review.",
    "test_points": [{"category": "functional", "title": "Demo valid login",
                     "description": "Check the declared sample response.", "priority": "P1"}],
    "case_drafts": [{"suggested_code": "TC_DEMO_LOGIN", "title": "Demo valid login",
                     "module": "Demo", "priority": "P1", "case_type": "checklist",
                     "scenario_type": "normal", "precondition": "A demo account is enabled.",
                     "steps": "1. Submit matching sample input.\n2. Observe the response.",
                     "expected_result": "The demo response displays the expected role."}],
    "limitations": ["Demo only; human review is required."],
}
FIELDS = {
    "status", "provider", "requested_model", "returned_model", "model_evidence_source",
    "prompt_version", "prompt_hash", "requirement_hash", "started_at", "finished_at",
    "latency_ms", "latency_scope", "prompt_tokens", "completion_tokens", "total_tokens",
    "finish_reason", "input_chars", "output_chars", "error_type", "error_message",
    "initial_text", "initial_cases", "structured_output", "generation_run_id",
    "session_id", "project_id", "version_id",
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbid(*args, **kwargs):
        raise AssertionError("Real network transport is forbidden in adapter tests.")
    monkeypatch.setattr(httpx.Client, "send", forbid)


def adapters():
    return importlib.import_module("experiment.adapters")


def reply(content=None, *, model="demo-response-model", usage=True, finish_reason="stop"):
    result = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish_reason,
                                 message=SimpleNamespace(content=content))],
    )
    if model is not None:
        result.model = model
    if usage is True:
        result.usage = SimpleNamespace(prompt_tokens=12, completion_tokens=9, total_tokens=21)
    elif usage is not False:
        result.usage = usage
    return result


class FakeFactory:
    def __init__(self, outcome):
        self.outcome = outcome
        self.constructions = []
        self.calls = []
        self.closed = 0

    def __call__(self, **kwargs):
        self.constructions.append(kwargs)
        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)),
            close=self.close,
        )

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) > 1:
            raise AssertionError("Adapter retried an explicit single attempt.")
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def close(self):
        self.closed += 1


def make(kind, tmp_path, factory, **settings):
    config = {**SETTINGS, **settings}
    if kind == "baseline":
        return adapters().BaselineAdapter(config, client_factory=factory)
    return adapters().ProposedAdapter(config, tmp_path / "runs" / "proposed.sqlite",
                                      client_factory=factory)


def test_adapter_module_exposes_contract():
    assert importlib.util.find_spec("experiment.adapters") is not None, "Adapter module is missing"
    module = adapters()
    assert callable(module.BaselineAdapter) and callable(module.ProposedAdapter)


def test_runner_with_both_real_adapters_uses_only_fake_clients_and_new_database(tmp_path):
    from experiment.framework import ROOT, build_plan, execute_pilot, load_dataset

    plan = build_plan(load_dataset(ROOT / "experiment" / "pilot_dataset", role="pilot"),
                      role="pilot")
    clients = {"baseline": [], "proposed": []}

    def client_factory(method):
        def create(**kwargs):
            content = "Demo ordinary initial text" if method == "baseline" else json.dumps(PAYLOAD)
            factory = FakeFactory(reply(content))
            clients[method].append(factory)
            return factory(**kwargs)
        return create

    def adapter_factory(output, settings):
        return {"baseline": adapters().BaselineAdapter(settings, client_factory("baseline")),
                "proposed": adapters().ProposedAdapter(
                    settings, output / "proposed.sqlite", client_factory("proposed"))}

    output = tmp_path / "pilot"
    summary = execute_pilot(plan, output, adapter_factory, SETTINGS,
                            execute=True, execution_mode="offline_fixture")
    assert summary["succeeded"] == summary["recorded_outcomes"] == 4
    assert all(len(group) == 2 for group in clients.values())
    for index, requirement in enumerate(plan["requirements"]):
        expected = requirement["input"]
        for method in ("baseline", "proposed"):
            factory = clients[method][index]
            assert len(factory.calls) == factory.closed == 1
            call = factory.calls[0]
            user_content = call["messages"][-1]["content"]
            if method == "baseline":
                user_content = user_content.removeprefix(adapters().BASELINE_PROMPT + "\n")
            assert json.loads(user_content) == expected
            assert call["model"] == SETTINGS["model"]
            assert call["max_tokens"] == SETTINGS["max_output_tokens"]
            assert "temperature" not in call and call["stream"] is False
            assert factory.constructions[0]["max_retries"] == 0
    connection = sqlite3.connect(output / "proposed.sqlite")
    try:
        assert connection.execute("SELECT COUNT(*) FROM generation_run").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM review_record").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0
    finally:
        connection.close()
    outcomes = [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted((output / "attempts").glob("*/outcome.json"))]
    assert all(r["usage_source"] == "offline_fixture" and not r["formal_eligible"] for r in outcomes)
    assert [r["method"] for r in outcomes] == ["baseline", "proposed", "proposed", "baseline"]


@pytest.mark.parametrize("kind", ["baseline", "proposed"])
@pytest.mark.parametrize("field,value", [("execute", False), ("execute", None),
                                        ("ai_enabled", False), ("api_key", ""), ("model", "")])
def test_disabled_or_unconfigured_adapter_has_no_client_or_database(tmp_path, kind, field, value):
    factory = FakeFactory(reply("Demo ordinary text"))
    with pytest.raises(ValueError):
        make(kind, tmp_path, factory, **{field: value})
    assert factory.constructions == factory.calls == []
    assert not (tmp_path / "runs").exists()


def test_baseline_accepts_safe_unstructured_text_without_schema_or_quantity_filter(tmp_path):
    text = "One ordinary case: submit valid input; observe the expected result."
    factory = FakeFactory(reply(text))
    adapter = make("baseline", tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record.keys() >= FIELDS
    assert record["status"] == "succeeded" and record["initial_text"] == text
    assert record["structured_output"] is None and record["initial_cases"] == []
    assert record["requested_model"] == "demo-request-model"
    assert record["returned_model"] == "demo-response-model"
    assert record["prompt_version"] == "baseline-v1"
    assert len(record["prompt_hash"]) == len(record["requirement_hash"]) == 64
    assert record["started_at"].endswith("+00:00") and record["finished_at"].endswith("+00:00")
    assert record["latency_ms"] >= 0
    call = factory.calls[0]
    assert len(factory.calls) == 1 and factory.constructions[0]["max_retries"] == 0
    assert call["stream"] is False and call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "response_format" not in call and "temperature" not in call
    assert REQUIREMENT["title"] in call["messages"][-1]["content"]
    assert REQUIREMENT["requirement_text"] in call["messages"][-1]["content"]
    assert record["total_tokens"] == 21 and factory.closed == 1


@pytest.mark.parametrize("kind", ["baseline", "proposed"])
def test_usage_and_returned_model_absence_are_not_estimated_or_filled(tmp_path, kind):
    content = "Safe ordinary text" if kind == "baseline" else json.dumps(PAYLOAD)
    factory = FakeFactory(reply(content, model=None, usage=False, finish_reason=None))
    adapter = make(kind, tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "succeeded"
    assert record["returned_model"] is None
    assert record["model_evidence_source"] != "provider_response_metadata"
    assert record["prompt_tokens"] is record["completion_tokens"] is record["total_tokens"] is None
    assert record["finish_reason"] is None
    if kind == "proposed":
        assert record["provider_model"] == SETTINGS["model"]


@pytest.mark.parametrize("kind", ["baseline", "proposed"])
def test_length_failure_retains_usage_but_not_unvalidated_output(tmp_path, kind):
    factory = FakeFactory(reply("truncated", finish_reason="length"))
    adapter = make(kind, tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "failed" and record["finish_reason"] == "length"
    assert record["total_tokens"] == 21 and len(factory.calls) == 1
    assert record["initial_text"] is record["structured_output"] is None
    assert record["initial_cases"] == []


@pytest.mark.parametrize("kind", ["baseline", "proposed"])
def test_sdk_exception_cannot_escape_safe_record(tmp_path, kind):
    private = "Authorization: Bearer SDK-private-value " + SETTINGS["api_key"]
    factory = FakeFactory(RuntimeError(private))
    adapter = make(kind, tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "failed" and record["error_type"] == "AIProviderError"
    rendered = json.dumps(record, ensure_ascii=False)
    assert SETTINGS["api_key"] not in rendered and "SDK-private-value" not in rendered
    assert record["total_tokens"] is None and len(factory.calls) == 1


@pytest.mark.parametrize("kind", ["baseline", "proposed"])
@pytest.mark.parametrize("unsafe", ["Authorization: Bearer leaked-private-value",
                                    SETTINGS["api_key"], SETTINGS["secret_key"],
                                    "You are a constrained test design assistant"])
def test_unsafe_output_is_neither_returned_nor_stored(tmp_path, kind, unsafe):
    if kind == "baseline":
        content = "Demo " + unsafe
    else:
        content = json.dumps({**PAYLOAD, "summary": "Demo " + unsafe})
    factory = FakeFactory(reply(content))
    adapter = make(kind, tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "failed" and record["error_type"] == "AIResponseError"
    assert record["initial_text"] is record["structured_output"] is None
    assert record["initial_cases"] == [] and unsafe not in json.dumps(record)
    if kind == "proposed":
        with sqlite3.connect(tmp_path / "runs" / "proposed.sqlite") as connection:
            assert connection.execute("SELECT COUNT(*) FROM test_case_draft").fetchone()[0] == 0
            assert connection.execute("SELECT structured_output_json FROM generation_run").fetchone()[0] is None


@pytest.mark.parametrize("kind", ["baseline", "proposed"])
def test_sensitive_input_fails_before_client_or_database(tmp_path, kind):
    factory = FakeFactory(reply("Demo safe text"))
    adapter = make(kind, tmp_path, factory)
    record = adapter.generate({**REQUIREMENT, "requirement_text": "Demo " + SETTINGS["api_key"]})
    adapter.close()
    assert record["status"] == "pre_call_failed"
    assert factory.constructions == factory.calls == []
    assert not (tmp_path / "runs").exists()
    assert SETTINGS["api_key"] not in json.dumps(record)


def test_proposed_exports_durable_run_and_matching_pending_draft(tmp_path):
    factory = FakeFactory(reply(json.dumps(PAYLOAD)))
    adapter = make("proposed", tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record.keys() >= FIELDS and record["status"] == "succeeded"
    assert record["structured_output"] == PAYLOAD
    assert record["initial_cases"][0]["suggested_code"] == "TC_DEMO_LOGIN"
    assert record["initial_cases"][0]["generation_run_id"] == record["generation_run_id"]
    assert record["initial_cases"][0]["session_id"] == record["session_id"]
    assert record["initial_cases"][0]["status"] == "pending"
    assert record["initial_cases"][0]["accepted_test_case_id"] is None
    assert record["returned_model"] == "demo-response-model"
    assert record["model_evidence_source"] == "provider_response_metadata"
    assert record["prompt_version"] == PROMPT_VERSION
    assert record["latency_scope"] == "test_design_service"
    assert len(factory.calls) == 1 and factory.calls[0]["response_format"] == {"type": "json_object"}
    with sqlite3.connect(tmp_path / "runs" / "proposed.sqlite") as connection:
        run = connection.execute("SELECT id,status,session_id,structured_output_json FROM generation_run").fetchone()
        assert run[:3] == (record["generation_run_id"], "succeeded", record["session_id"])
        assert json.loads(run[3]) == PAYLOAD
        assert connection.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0


def test_proposed_schema_failure_keeps_one_failed_run(tmp_path):
    factory = FakeFactory(reply('{"summary":"Demo incomplete shape"}'))
    adapter = make("proposed", tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "failed" and record["error_type"] == "AIResponseError"
    assert record["generation_run_id"] is not None and record["session_id"] is None
    assert record["structured_output"] is None and record["total_tokens"] == 21
    with sqlite3.connect(tmp_path / "runs" / "proposed.sqlite") as connection:
        assert connection.execute("SELECT COUNT(*) FROM generation_run").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM test_design_session").fetchone()[0] == 0


def test_proposed_rejects_existing_database_before_client_or_touching_bytes(tmp_path):
    path = tmp_path / "existing.sqlite"
    path.write_bytes(b"unrelated existing database marker")
    factory = FakeFactory(reply(json.dumps(PAYLOAD)))
    with pytest.raises(ValueError):
        adapters().ProposedAdapter(SETTINGS, path, client_factory=factory)
    assert path.read_bytes() == b"unrelated existing database marker"
    assert factory.constructions == []


def test_proposed_rejects_original_instance_namespace_without_connecting():
    path = Path(__file__).resolve().parents[1] / "instance" / "must_not_create.sqlite"
    factory = FakeFactory(reply(json.dumps(PAYLOAD)))
    with pytest.raises(ValueError):
        adapters().ProposedAdapter(SETTINGS, path, client_factory=factory)
    assert factory.constructions == [] and not path.exists()


def test_default_client_factory_resolves_monkeypatched_openai_at_call_time(tmp_path, monkeypatch):
    factory = FakeFactory(reply("Safe ordinary text"))
    adapter = adapters().BaselineAdapter(SETTINGS)
    monkeypatch.setattr(adapters(), "OpenAI", factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "succeeded" and len(factory.calls) == 1


def test_proposed_blocks_baseline_prompt_leak_before_business_persistence(tmp_path):
    prompt = adapters().BASELINE_PROMPT
    factory = FakeFactory(reply(json.dumps({**PAYLOAD, "summary": prompt})))
    adapter = make("proposed", tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "failed" and record["structured_output"] is None
    with sqlite3.connect(tmp_path / "runs" / "proposed.sqlite") as connection:
        assert connection.execute("SELECT COUNT(*) FROM test_case_draft").fetchone()[0] == 0
        row = connection.execute("SELECT status,structured_output_json FROM generation_run").fetchone()
        assert row == ("failed", None)


def test_proposed_business_save_failure_retains_safe_validated_snapshot(tmp_path, monkeypatch):
    from app.extensions import db
    from app.services.test_design_service import TestDesignService
    from sqlalchemy.exc import OperationalError
    original = TestDesignService.create_session

    def fail_business_save(service, **kwargs):
        def fail():
            raise OperationalError("private SQL statement", {}, RuntimeError(SETTINGS["api_key"]))
        with monkeypatch.context() as patch:
            patch.setattr(db.session, "commit", fail)
            return original(service, **kwargs)

    monkeypatch.setattr(TestDesignService, "create_session", fail_business_save)
    factory = FakeFactory(reply(json.dumps(PAYLOAD)))
    adapter = make("proposed", tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "failed" and record["error_type"] == "WorkflowPersistenceError"
    assert record["structured_output"] == PAYLOAD and record["initial_cases"] == []
    assert record["session_id"] is None and record["total_tokens"] == 21
    assert SETTINGS["api_key"] not in json.dumps(record) and len(factory.calls) == 1


def test_initial_audit_failure_never_calls_provider(tmp_path, monkeypatch):
    from app.services.test_design.evidence import GenerationRecorder
    from app.services.workflow_errors import WorkflowPersistenceError

    def fail(*args, **kwargs):
        raise WorkflowPersistenceError("private initial audit failure")

    monkeypatch.setattr(GenerationRecorder, "start", fail)
    factory = FakeFactory(reply(json.dumps(PAYLOAD)))
    adapter = make("proposed", tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "pre_call_failed" and record["generation_run_id"] is None
    assert record["error_type"] == "WorkflowPersistenceError"
    assert factory.calls == [] and "private initial audit failure" not in json.dumps(record)


def test_proposed_never_connects_to_original_app_database_or_uses_app_factory(tmp_path, monkeypatch):
    import app
    from sqlalchemy.engine import Engine
    target = (tmp_path / "runs" / "proposed.sqlite").resolve()
    connect = Engine.connect
    seen = []

    def isolated_connect(engine, *args, **kwargs):
        physical = Path(engine.url.database).resolve()
        assert physical == target, "Adapter attempted to access a nonexperiment database"
        seen.append(physical)
        return connect(engine, *args, **kwargs)

    def no_app_factory(*args, **kwargs):
        raise AssertionError("Production app factory must not run")

    monkeypatch.setattr(Engine, "connect", isolated_connect)
    monkeypatch.setattr(app, "create_app", no_app_factory)
    factory = FakeFactory(reply(json.dumps(PAYLOAD)))
    adapter = make("proposed", tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "succeeded" and seen and set(seen) == {target}


def test_proposed_does_not_open_file_created_after_adapter_construction(tmp_path):
    factory = FakeFactory(reply(json.dumps(PAYLOAD)))
    adapter = make("proposed", tmp_path, factory)
    path = tmp_path / "runs" / "proposed.sqlite"
    path.parent.mkdir()
    path.write_bytes(b"unrelated marker")
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "pre_call_failed" and factory.constructions == []
    assert path.read_bytes() == b"unrelated marker"


@pytest.mark.parametrize("kind", ["baseline", "proposed"])
def test_malformed_usage_and_unsafe_model_namespace_are_sanitized(tmp_path, kind):
    usage = SimpleNamespace(prompt_tokens=True, completion_tokens=-1, total_tokens="21")
    content = "Safe ordinary text" if kind == "baseline" else json.dumps(PAYLOAD)
    factory = FakeFactory(reply(content, usage=usage, model=SETTINGS["api_key"]))
    adapter = make(kind, tmp_path, factory)
    record = adapter.generate(REQUIREMENT)
    adapter.close()
    assert record["status"] == "succeeded" and record["returned_model"] is None
    assert record["prompt_tokens"] is record["completion_tokens"] is record["total_tokens"] is None
    assert SETTINGS["api_key"] not in json.dumps(record)


def test_proposed_attempts_are_separate_versions_runs_and_initial_sources(tmp_path):
    class TwoCalls(FakeFactory):
        def create(self, **kwargs):
            self.calls.append(kwargs)
            return self.outcome
    factory = TwoCalls(reply(json.dumps(PAYLOAD)))
    adapter = make("proposed", tmp_path, factory)
    first = adapter.generate(REQUIREMENT)
    second = adapter.generate({**REQUIREMENT, "title": "Demo independent second requirement"})
    adapter.close()
    adapter.close()
    assert first["status"] == second["status"] == "succeeded" and len(factory.calls) == 2
    assert first["generation_run_id"] != second["generation_run_id"]
    assert first["session_id"] != second["session_id"] and first["version_id"] != second["version_id"]
    assert first["project_id"] == second["project_id"] and factory.closed == 2
