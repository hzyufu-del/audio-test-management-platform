"""Complete 56-call fixtures exercise real adapters/service/storage, offline."""
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import httpx
import pytest

from experiment.formal_adapters import FormalAdapters
from experiment.formal_plan import build_formal_plan
from experiment.formal_runner import run_offline_fixture
from test_experiment_adapters import PAYLOAD

BASELINE = """## 用例 1
编号：tc_demo_1
标题：Demo sample valid operation
模块：Demo
优先级：高
用例类型：checklist
场景类型：normal
前置条件：Use a Demo sample.
测试步骤：1. Submit matching sample input.
2. Observe the response.
预期结果：The Demo response displays the expected result.
"""


@pytest.fixture(autouse=True)
def deny_real_transport(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Formal integration fixtures must never access network")
    monkeypatch.setattr(httpx.Client, "send", denied)


class FixtureClients:
    def __init__(self, plan, output, fault=None):
        self.plan = plan
        self.output = output
        self.fault = fault
        self.calls = []

    def __call__(self, **settings):
        assert settings["max_retries"] == 0 and settings["timeout"] == 60
        return SimpleNamespace(max_retries=0, chat=SimpleNamespace(
            completions=SimpleNamespace(create=self.create)), close=lambda: None)

    def create(self, **request):
        task = self.plan["tasks"][len(self.calls)]
        state = json.loads((self.output / "state.json").read_text(encoding="utf-8"))
        key = task["requirement_id"] + "__" + task["method"]
        assert state["pairs"][key]["status"] == "running"
        started = json.loads((self.output / "attempts" / key / "started.json").read_text(encoding="utf-8"))
        assert started["evidence"]["requirement_hash"] == task["requirement_hash"]
        assert started["evidence"]["prompt_hash"] == self.plan["prompt_hashes"][task["method"]]
        assert (self.output / "attempts" / key / "call.json").exists()
        user = request["messages"][-1]["content"]
        if task["method"] == "baseline":
            from experiment.adapters import BASELINE_PROMPT
            user = user.removeprefix(BASELINE_PROMPT + "\n")
        assert json.loads(user) == task["input"]
        assert "DO_NOT_LEAK_REFERENCE_SENTINEL" not in str(request)
        assert request["model"] == "deepseek-v4-pro" and request["max_tokens"] == 8000
        assert "temperature" not in request
        self.calls.append((task["requirement_id"], task["method"]))
        content = BASELINE if task["method"] == "baseline" else json.dumps(PAYLOAD)
        if len(self.calls) == 10 and self.fault == "schema":
            content = '{"unexpected": "Demo invalid schema"}'
        if len(self.calls) == 10 and self.fault == "interrupt":
            raise KeyboardInterrupt
        return SimpleNamespace(model="demo-response", usage=SimpleNamespace(
            prompt_tokens=12, completion_tokens=9, total_tokens=21),
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))])


def test_real_business_chain_all_56_and_reference_sentinel(tmp_path, monkeypatch):
    from experiment import formal_plan
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    for name in ["requirements.jsonl", "reference_scenarios.jsonl", "DATASET_README.md"]:
        (dataset / name).write_bytes((formal_plan.DEFAULT_DATASET_DIR / name).read_bytes())
    reference_path = dataset / "reference_scenarios.jsonl"
    rows = [json.loads(line) for line in reference_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["trigger_condition"] += " DO_NOT_LEAK_REFERENCE_SENTINEL"
    reference_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    new_hash = hashlib.sha256(reference_path.read_bytes()).hexdigest()
    old_hash = formal_plan.EXPECTED_DATASET_HASHES["reference_scenarios.jsonl"]
    readme = dataset / "DATASET_README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace(old_hash, new_hash), encoding="utf-8")
    monkeypatch.setattr(formal_plan, "EXPECTED_DATASET_HASHES", {
        **formal_plan.EXPECTED_DATASET_HASHES, "reference_scenarios.jsonl": new_hash})
    plan = build_formal_plan(dataset)
    assert "DO_NOT_LEAK_REFERENCE_SENTINEL" not in json.dumps(plan)
    output = tmp_path / "run"
    clients = FixtureClients(plan, output)
    result = run_offline_fixture(plan, output,
        lambda path, settings, marker: FormalAdapters(path, settings, marker, client_factory=clients),
        dataset_dir=dataset)
    assert len(clients.calls) == len(set(clients.calls)) == 56
    assert result["succeeded"] == 56 and result["failed"] == 0
    assert result["actual_provider_calls"] == 0 and result["provider_fake_calls"] == 56
    assert result["generation_collection_completed"]
    with sqlite3.connect(output / "proposed.sqlite3") as db:
        for table, count in [("generation_run", 28), ("test_design_session", 28),
                             ("test_case_draft", 28), ("review_record", 0), ("test_case", 0)]:
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == count
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    initial = [json.loads(line) for line in (output / "baseline/initial_cases.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(initial) == 28
    assert all(len(row["initial_cases"]) == 1 for row in initial)
    assert all(row["initial_cases"][0]["priority"] == "高" for row in initial)
    for path in output.rglob("*.json*"):
        text = path.read_text(encoding="utf-8")
        assert "offline-fixture-key" not in text and "offline-fixture-session" not in text
    assert not (output / "evaluation").exists()


@pytest.mark.parametrize("fault,expected_calls", [("schema", 56), ("interrupt", 10)])
def test_real_adapters_schema_failure_continues_and_interrupt_stops(tmp_path, fault, expected_calls):
    plan = build_formal_plan()
    output = tmp_path / "run"
    clients = FixtureClients(plan, output, fault)
    result = run_offline_fixture(plan, output,
        lambda path, settings, marker: FormalAdapters(path, settings, marker, client_factory=clients))
    assert len(clients.calls) == expected_calls
    assert result["actual_provider_calls"] == 0
    if fault == "schema":
        assert result["failed"] == 1 and result["succeeded"] == 55
    else:
        assert result["not_started"] == 46
        with pytest.raises(Exception, match="partial formal experiment"):
            run_offline_fixture(plan, output, lambda *args: pytest.fail("Must refuse restart before factory"))
        assert len(clients.calls) == 10


def test_real_source_association_error_at_10_stops(tmp_path, monkeypatch):
    from experiment.formal_adapters import _Proposed
    from app.extensions import db
    plan = build_formal_plan()
    output = tmp_path / "run"
    clients = FixtureClients(plan, output)
    original = _Proposed._export
    def mismatched(self, record, run, context, version_id):
        if len(clients.calls) == 10:
            from sqlalchemy import text
            # The ORM intentionally protects terminal Runs; SQL deliberately
            # damages only this fixture to test the independent readback gate.
            db.session.execute(text("UPDATE generation_run SET requirement_hash=:value WHERE id=:identifier"),
                               {"value": "0" * 64, "identifier": run.id})
            db.session.commit()
            db.session.expire(run, ["requirement_hash"])
        return original(self, record, run, context, version_id)
    monkeypatch.setattr(_Proposed, "_export", mismatched)
    result = run_offline_fixture(plan, output,
        lambda path, settings, marker: FormalAdapters(path, settings, marker, client_factory=clients))
    assert len(clients.calls) == 10
    assert result["framework_error"] == 1 and result["not_started"] == 46
    with sqlite3.connect(output / "proposed.sqlite3") as connection:
        # Deliberately damaged fixture evidence remains; runner never repairs it.
        assert connection.execute("SELECT COUNT(*) FROM generation_run WHERE requirement_hash=?",
                                  ("0" * 64,)).fetchone()[0] == 1
