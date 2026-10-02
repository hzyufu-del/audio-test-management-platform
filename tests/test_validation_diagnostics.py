"""Synthetic offline candidates, never captured historical Pilot responses."""

import copy
import importlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.services.ai.exceptions import AIProviderError, AIResponseError
from app.services.test_design.deepseek_provider import DeepSeekTestDesignProvider
from app.services.test_design.prompts import TEST_DESIGN_JSON_EXAMPLE
from app.services.test_design.schemas import TestDesignContext as Context, TestDesignResult as Result


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {
    "execute": True, "ai_enabled": True, "api_key": "fixture-private-key",
    "secret_key": "fixture-private-secret", "model": "demo-request-model",
    "base_url": "https://api.deepseek.com", "timeout_seconds": 5,
    "max_output_tokens": 1200,
}
CONTEXT = Context(
    title="Demo authentication", requirement_text="Demo virtual login accepts enabled sample accounts only.",
)


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbid(*args, **kwargs):
        raise AssertionError("Real network transport forbidden in diagnostic tests")
    monkeypatch.setattr(httpx.Client, "send", forbid)


def payload():
    return copy.deepcopy(TEST_DESIGN_JSON_EXAMPLE)


def response(content, finish_reason="stop"):
    return SimpleNamespace(
        model="demo-returned-model", usage=SimpleNamespace(
            prompt_tokens=12, completion_tokens=9, total_tokens=21),
        choices=[SimpleNamespace(finish_reason=finish_reason,
                                 message=SimpleNamespace(content=content))],
    )


class FakeFactory:
    def __init__(self, *results):
        self.results = iter(results)
        self.calls = []
        self.constructions = []

    def __call__(self, **kwargs):
        self.constructions.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)),
                               close=lambda: None)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def provider(factory):
    return DeepSeekTestDesignProvider(api_key=SETTINGS["api_key"], model=SETTINGS["model"],
        base_url=SETTINGS["base_url"], timeout_seconds=5, max_output_tokens=1200,
        client_factory=factory)


def summary(value):
    result = getattr(value, "last_validation_summary", None)
    assert isinstance(result, dict), "Missing safe validation diagnostic summary"
    assert set(result) == {"stage", "error_categories", "field_paths", "error_count", "schema_error_codes"}
    return result


@pytest.mark.parametrize("mutation,code,path", [
    ("abnormal", "enum", "case_drafts[0].scenario_type"),
    ("edge", "enum", "case_drafts[0].scenario_type"),
    ("high", "enum", "test_points[0].priority"),
    ("functional_case", "enum", "case_drafts[0].case_type"),
    ("steps_array", "string_type", "case_drafts[0].steps"),
    ("null_precondition", "string_type", "case_drafts[0].precondition"),
    ("empty_limitations", "too_short", "limitations"),
    ("empty_module", "string_too_short", "case_drafts[0].module"),
    ("long_module", "string_too_long", "case_drafts[0].module"),
    ("numeric", "string_type", "summary"),
    ("extra", "extra_forbidden", "extra_field"),
    ("missing", "missing", "limitations"),
    ("too_many_points", "too_long", "test_points"),
    ("too_many_drafts", "too_long", "case_drafts"),
])
def test_schema_failures_have_safe_codes_and_paths_without_values(mutation, code, path):
    value = payload()
    draft = value["case_drafts"][0]
    if mutation in {"abnormal", "edge"}:
        draft["scenario_type"] = mutation
    elif mutation == "high":
        value["test_points"][0]["priority"] = "high"
    elif mutation == "functional_case":
        draft["case_type"] = "functional"
    elif mutation == "steps_array":
        draft["steps"] = ["private-invalid-step"]
    elif mutation == "null_precondition":
        draft["precondition"] = None
    elif mutation == "empty_limitations":
        value["limitations"] = []
    elif mutation == "empty_module":
        draft["module"] = "  "
    elif mutation == "long_module":
        draft["module"] = "M" * 81
    elif mutation == "numeric":
        value["summary"] = 123
    elif mutation == "extra":
        value["Authorization: Bearer injected-private-value"] = SETTINGS["api_key"]
    elif mutation == "missing":
        del value["limitations"]
    elif mutation == "too_many_points":
        value["test_points"] *= 7
    else:
        value["case_drafts"] *= 7
    factory = FakeFactory(response(json.dumps(value)))
    engine = provider(factory)
    with pytest.raises(AIResponseError):
        engine.generate(CONTEXT)
    diagnostic = summary(engine)
    assert diagnostic["stage"] == "schema"
    assert code in diagnostic["schema_error_codes"] and path in diagnostic["field_paths"]
    assert diagnostic["error_count"] >= 1 and len(factory.calls) == 1
    text = json.dumps(diagnostic)
    assert SETTINGS["api_key"] not in text and "injected-private-value" not in text
    assert "private-invalid-step" not in text and "input" not in diagnostic


@pytest.mark.parametrize("content,reason,stage", [
    ('{"summary":', "stop", "json_parse"),
    ('Explanation: {}', "stop", "json_parse"),
    ("", "stop", "response_content"),
    (None, "stop", "response_content"),
    ('{}', "length", "output_limit"),
])
def test_non_schema_stages_preserve_usage_without_repair_or_retry(content, reason, stage):
    factory = FakeFactory(response(content, reason))
    engine = provider(factory)
    with pytest.raises(AIResponseError):
        engine.generate(CONTEXT)
    diagnostic = summary(engine)
    assert diagnostic["stage"] == stage and diagnostic["error_count"] == 1
    if stage == "json_parse":
        assert diagnostic["schema_error_codes"] == ["json_invalid"]
    assert engine.last_call_metadata.total_tokens == 21 and len(factory.calls) == 1
    assert factory.constructions[0]["max_retries"] == 0


def test_each_call_resets_summary_and_valid_json_fence_behavior_is_unchanged():
    factory = FakeFactory(response('{}'), response('```json\n' + json.dumps(payload()) + '\n```'),
                          RuntimeError("Authorization: Bearer injected-private-value"))
    engine = provider(factory)
    with pytest.raises(AIResponseError):
        engine.generate(CONTEXT)
    assert summary(engine)["stage"] == "schema"
    assert engine.generate(CONTEXT).model_dump(mode="json") == payload()
    assert getattr(engine, "last_validation_summary", "missing") is None
    with pytest.raises(AIProviderError):
        engine.generate(CONTEXT)
    assert summary(engine)["stage"] == "api"
    assert "injected-private-value" not in json.dumps(summary(engine))
    assert len(factory.calls) == 3


def test_validation_error_excludes_input_context_message_and_untrusted_key(monkeypatch):
    value = payload()
    value["case_drafts"][0]["Authorization: Bearer private-extra-key"] = "private-input"
    value["case_drafts"][0]["steps"] = ["private-invalid-value"]
    with pytest.raises(ValidationError) as captured:
        Result.model_validate(value)
    assert importlib.util.find_spec("app.services.test_design.diagnostics") is not None
    module = importlib.import_module("app.services.test_design.diagnostics")
    original = ValidationError.errors
    options = []
    def errors(self, **kwargs):
        options.append(kwargs)
        return original(self, **kwargs)
    monkeypatch.setattr(ValidationError, "errors", errors)
    diagnostic = module.summarize_validation_error(captured.value)
    assert options == [{"include_input": False, "include_context": False, "include_url": False}]
    assert diagnostic["field_paths"] == ["case_drafts[0].steps", "case_drafts[0].extra_field"]
    assert "private" not in json.dumps(diagnostic)


@pytest.mark.parametrize("index,expected_path", [
    (-1, "extra_field"),
    (10000, "extra_field"),
    (0, "case_drafts[0].title"),
    (19, "case_drafts[19].title"),
    (9999, "case_drafts[9999].title"),
], ids=["negative", "over_bound", "zero", "valid_item", "max_supported"])
def test_synthetic_validation_locator_masks_unsupported_index_without_inventing_zero(index, expected_path):
    module = importlib.import_module("app.services.test_design.diagnostics")
    error = ValidationError.from_exception_data("Synthetic locator candidate", [
        {"type": "string_type", "loc": ("case_drafts", index, "title"), "input": None},
    ])
    diagnostic = module.summarize_validation_error(error)
    assert diagnostic["field_paths"] == [expected_path]
    assert diagnostic["schema_error_codes"] == ["string_type"]
    assert diagnostic["error_categories"] == ["invalid_type"]
    assert diagnostic["error_count"] == 1
    if index < 0 or index > 9999:
        assert "[0]" not in diagnostic["field_paths"][0]


def test_summary_export_sanitizer_bounds_types_codes_and_malicious_paths():
    assert importlib.util.find_spec("app.services.test_design.diagnostics") is not None
    module = importlib.import_module("app.services.test_design.diagnostics")
    injected = {"stage": "private-stage", "error_count": 10**100,
        "error_categories": ["private-category"] * 100,
        "schema_error_codes": ["private-code", "enum"] * 100,
        "field_paths": ["case_drafts[0].scenario_type", "private-key", "case_drafts[10000000].title"] * 100,
        "input": "private-body", "msg": "private-message", "ctx": {"private": "value"}}
    safe = module.sanitize_validation_summary(injected)
    assert set(safe) == {"stage", "error_count", "error_categories", "schema_error_codes", "field_paths"}
    assert safe["stage"] == "unknown" and safe["error_count"] <= 10000
    assert all(len(safe[key]) <= 20 for key in ("error_categories", "schema_error_codes", "field_paths"))
    assert "private" not in json.dumps(safe) and "10000000" not in json.dumps(safe)
    assert module.sanitize_validation_summary("private raw value") is None


@pytest.mark.parametrize("candidate,stage,category", [
    ("synthetic_schema_candidate_not_captured", "schema", "invalid_enum"),
    ("synthetic_safety_candidate_not_captured", "output_safety", "sensitive_content"),
])
def test_synthetic_candidates_match_generic_historical_failure_envelope_only(tmp_path, candidate, stage, category):
    """Envelope compatibility is not recovery of either historical return."""
    from experiment.adapters import ProposedAdapter
    value = payload()
    if "schema" in candidate:
        value["case_drafts"][0]["scenario_type"] = "abnormal"
    else:
        value["summary"] = "Demo Authorization: Bearer synthetic-private-output"
    factory = FakeFactory(response(json.dumps(value)))
    database = tmp_path / "proposed.sqlite"
    adapter = ProposedAdapter({**SETTINGS, "validation_diagnostics": True}, database, client_factory=factory)
    record = adapter.generate(CONTEXT.model_dump(mode="json"))
    adapter.close()
    assert record["status"] == "failed" and record["error_type"] == "AIResponseError"
    assert record["error_message"] == "AI test design output failed validation."
    assert record["returned_model"] == "demo-returned-model" and record["total_tokens"] == 21
    assert record["finish_reason"] == "stop" and record["session_id"] is None
    assert record["structured_output"] is None and record["initial_cases"] == []
    diagnostic = record.get("validation_diagnostic")
    assert isinstance(diagnostic, dict) and diagnostic["stage"] == stage
    assert category in diagnostic["error_categories"]
    assert len(factory.calls) == 1 and "synthetic-private-output" not in json.dumps(record)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM test_design_session").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM test_case_draft").fetchone()[0] == 0
        assert connection.execute("SELECT structured_output_json FROM generation_run").fetchone()[0] is None
    assert b"synthetic-private-output" not in database.read_bytes()


@pytest.mark.parametrize("enabled", [False, True])
def test_pilot_diagnostic_export_is_opt_in_proposed_only_and_resanitized(tmp_path, enabled):
    from experiment import framework
    plan = framework.build_plan(framework.load_dataset(ROOT / "experiment/pilot_dataset", role="pilot"), role="pilot")
    calls = []
    class Adapter:
        def generate(self, requirement):
            calls.append(requirement)
            return {"status": "failed", "generation_run_id": 1, "session_id": None,
                "total_tokens": 21, "finish_reason": "stop", "validation_diagnostic": {
                    "stage": "schema", "error_count": 2, "error_categories": ["invalid_enum", "private"],
                    "schema_error_codes": ["enum", "private"],
                    "field_paths": ["case_drafts[0].scenario_type", "Authorization: private"],
                    "input": SETTINGS["api_key"]}}
        def close(self):
            pass
    directory = tmp_path / "pilot"
    config = {**SETTINGS, "validation_diagnostics": enabled}
    framework.execute_pilot(plan, directory, lambda *args: {"baseline": Adapter(), "proposed": Adapter()},
        config, execute=True, execution_mode="offline_fixture")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("validation_diagnostics_enabled") is enabled
    records = [json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("attempts/*/outcome.json")]
    assert all("validation_diagnostic" not in record for record in records)
    files = list(directory.glob("audit/*.validation.json"))
    assert len(files) == (2 if enabled else 0)
    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["method"] == "proposed" and record["sample_role"] == "pilot"
        assert record["generation_run_id"] == 1 and record["session_id"] is None
        assert record["validation_summary"]["stage"] == "schema"
        assert "private" not in json.dumps(record)
    assert len(calls) == 4 and SETTINGS["api_key"] not in "".join(
        path.read_text(encoding="utf-8") for path in directory.rglob("*.json"))


def test_diagnostic_write_failure_preserves_outcome_and_stops_without_replay(tmp_path, monkeypatch):
    from experiment import framework
    plan = framework.build_plan(framework.load_dataset(ROOT / "experiment/pilot_dataset", role="pilot"), role="pilot")
    writes = framework._write_json
    calls = []
    def write(path, value):
        if path.name.endswith(".validation.json"):
            raise framework.ExperimentError("Diagnostic fixture write failure; do not retry")
        writes(path, value)
    monkeypatch.setattr(framework, "_write_json", write)
    class Adapter:
        def generate(self, requirement):
            calls.append(requirement)
            return {"status": "failed", "total_tokens": 21, "validation_diagnostic": {
                "stage": "schema", "error_count": 1, "error_categories": ["missing_field"],
                "field_paths": ["limitations"], "schema_error_codes": ["missing"]}}
        def close(self):
            pass
    directory = tmp_path / "pilot"
    with pytest.raises(framework.ExperimentError, match="do not retry"):
        framework.execute_pilot(plan, directory, lambda *args: {"baseline": Adapter(), "proposed": Adapter()},
            {**SETTINGS, "validation_diagnostics": True}, execute=True, execution_mode="offline_fixture")
    assert len(calls) == 2 and len(list(directory.glob("attempts/*/started.json"))) == 2
    assert len(list(directory.glob("attempts/*/outcome.json"))) == 2
    assert not (directory / "summary.json").exists()


def test_diagnostic_flag_dry_run_does_not_load_settings_client_or_database(monkeypatch, capsys, tmp_path):
    from scripts import run_pilot
    def forbidden(*args, **kwargs):
        pytest.fail("Dry run accessed execution settings")
    monkeypatch.setattr(run_pilot, "execution_settings", forbidden)
    monkeypatch.setattr(run_pilot, "make_adapters", forbidden)
    monkeypatch.setattr(run_pilot.sys.stdout, "reconfigure", lambda **kwargs: None, raising=False)
    assert run_pilot.main(["--validation-diagnostics", "--output-dir", str(tmp_path / "unused")]) == 0
    assert json.loads(capsys.readouterr().out)["execution_mode"] == "dry_run"
    assert not list(tmp_path.iterdir())


@pytest.fixture()
def isolated_catalog(tmp_path):
    from flask import Flask
    from app.extensions import db
    from app.models import Project, Version
    app = Flask("safe_diagnostics_fixture")
    app.config.update(SQLALCHEMY_DATABASE_URI=f"sqlite:///{(tmp_path / 'fixture.sqlite').as_posix()}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False, SECRET_KEY=SETTINGS["secret_key"],
        DEEPSEEK_API_KEY=SETTINGS["api_key"])
    db.init_app(app)
    with app.app_context():
        db.create_all()
        project = Project(name="Demo offline fixture", code="DEMO-DIAGNOSTIC")
        db.session.add(project)
        db.session.flush()
        version = Version(project_id=project.id, name="Demo fixture version", code="DEMO-V1")
        db.session.add(version)
        db.session.commit()
        yield app, {"project_id": project.id, "version_id": version.id,
                    **CONTEXT.model_dump(mode="json")}
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize("failure,stage,category", [
    ("raw_result", "schema", "missing_field"),
    ("raised_validation_error", "schema", "missing_field"),
    ("missing_demo", "output_safety", "missing_demo_scope"),
    ("sensitive", "output_safety", "sensitive_content"),
])
def test_service_third_party_failures_are_safely_summarized(isolated_catalog, failure, stage, category):
    import re
    from app.extensions import db
    from app.models import GenerationRun, TestCaseDraft as Draft, TestDesignSession as Session
    from app.services.test_design_service import TestDesignService as Service
    app, context = isolated_catalog
    class ThirdParty:
        provider_name = "mock"
        provider_model = None
        is_demo = True
        def generate(self, _context):
            if failure == "raised_validation_error":
                return Result.model_validate({"Authorization: Bearer private-key": "private-input"})
            if failure == "raw_result":
                return {}
            value = payload()
            if failure == "sensitive":
                value["summary"] = "Demo " + SETTINGS["secret_key"]
            else:
                def remove_scope(item):
                    if isinstance(item, str):
                        return re.sub(r"\b(?:mock|demo|sample)\b", "Virtual", item, flags=re.I)
                    if isinstance(item, dict):
                        return {key: remove_scope(val) for key, val in item.items()}
                    if isinstance(item, list):
                        return [remove_scope(val) for val in item]
                    return item
                value = remove_scope(value)
            return value
    engine = ThirdParty()
    with pytest.raises(AIResponseError):
        Service(app.config, engine).create_session(**context)
    diagnostic = summary(engine)
    assert diagnostic["stage"] == stage and category in diagnostic["error_categories"]
    assert "private" not in json.dumps(diagnostic)
    run = db.session.get(GenerationRun, 1)
    assert run.status == "failed" and run.structured_output_json is None and run.session_id is None
    assert Draft.query.count() == Session.query.count() == 0


def test_service_persistence_failure_has_separate_diagnostic_stage(isolated_catalog, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from app.extensions import db
    from app.models import GenerationRun
    from app.services.test_design_service import TestDesignService as Service
    from app.services.workflow_errors import WorkflowPersistenceError
    app, context = isolated_catalog
    factory = FakeFactory(response(json.dumps(payload())))
    engine = provider(factory)
    def fail(*args):
        raise OperationalError("private SQL", {}, RuntimeError("private database message"))
    monkeypatch.setattr(Service, "_update_session_status", fail)
    with pytest.raises(WorkflowPersistenceError):
        Service(app.config, engine).create_session(**context)
    diagnostic = summary(engine)
    assert diagnostic["stage"] == "business_persistence"
    assert diagnostic["error_categories"] == ["persistence_failure"]
    assert "private" not in json.dumps(diagnostic) and len(factory.calls) == 1
    run = db.session.get(GenerationRun, 1)
    assert run.status == "failed" and json.loads(run.structured_output_json) == payload()


def test_optional_summary_does_not_break_slotted_third_party_success(isolated_catalog):
    from app.services.test_design_service import TestDesignService as Service
    app, context = isolated_catalog
    class SlottedProvider:
        __slots__ = ("last_call_metadata",)
        provider_name = "mock"
        provider_model = None
        is_demo = True
        def generate(self, _context):
            return payload()
    session = Service(app.config, SlottedProvider()).create_session(**context)
    assert session.status == "generated" and len(session.drafts) == 3
