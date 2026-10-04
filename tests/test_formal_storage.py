import json

import pytest

from experiment.formal_storage import FormalStore, StorageError


@pytest.fixture
def manifest():
    return {"experiment_id": "formal-v1", "tasks": [
        {"requirement_id": f"REQ_{i:03}", "method": method}
        for i in range(28) for method in ("baseline", "proposed")
    ]}


def test_full_atomic_records(tmp_path, manifest):
    store = FormalStore(tmp_path / "run")
    store.initialize(manifest)
    for task in manifest["tasks"]:
        store.start_attempt(task, {"source": task["method"]})
        store.record_call(task)
        store.finish_attempt(task, {"status": "succeeded", "initial_cases": []})
        store.verify()
    assert store.summary()["actual_provider_calls"] == 56
    assert store.summary()["succeeded"] == 56


def test_restart_and_duplicate(tmp_path, manifest):
    path = tmp_path / "run"
    store = FormalStore(path)
    store.initialize(manifest)
    with pytest.raises(StorageError, match="manual recovery"):
        FormalStore(path).initialize(manifest)
    task = manifest["tasks"][0]
    with pytest.raises(StorageError):
        store.record_call(task)
    store.start_attempt(task, {})
    with pytest.raises(StorageError):
        store.start_attempt(task, {})
    store.record_call(task)
    with pytest.raises(StorageError):
        store.record_call(task)


def test_tamper_and_mapping(tmp_path, manifest):
    store = FormalStore(tmp_path / "run")
    store.initialize(manifest)
    with pytest.raises(StorageError):
        store.start_attempt({"requirement_id": "unknown", "method": "baseline"}, {})
    with pytest.raises(StorageError):
        store.start_attempt({**manifest["tasks"][0], "attempt": 2}, {})
    (store.path / "manifest.json").write_text("{}")
    with pytest.raises(StorageError):
        store.verify()


def test_writer_failure_preserves_running(tmp_path, manifest, monkeypatch):
    store = FormalStore(tmp_path / "run")
    store.initialize(manifest)
    task = manifest["tasks"][0]
    store.start_attempt(task, {})
    store.record_call(task)
    def broken(*args, **kwargs):
        raise OSError("secret exception")
    monkeypatch.setattr(store, "_write", broken)
    with pytest.raises(StorageError) as caught:
        store.finish_attempt(task, {"status": "succeeded"})
    assert "secret" not in str(caught.value)
    store.fail(task, "writer_error")
    assert json.loads((store.path / "state.json").read_text())["pairs"]["REQ_000__baseline"]["status"] == "running"


def test_jsonl_corruption_and_immutable(tmp_path, manifest):
    store = FormalStore(tmp_path / "run")
    store.initialize(manifest)
    task = manifest["tasks"][0]
    store.start_attempt(task, {})
    store.record_call(task)
    store.finish_attempt(task, {"status": "failed"})
    outcome = store.path / "attempts" / "REQ_000__baseline" / "outcome.json"
    before = outcome.read_bytes()
    with pytest.raises(StorageError):
        store.finish_attempt(task, {"status": "succeeded"})
    assert outcome.read_bytes() == before
    (store.path / "baseline" / "generation_records.jsonl").write_text('{"broken":')
    with pytest.raises(StorageError):
        store.verify()


def test_os_replace_failure_before_running(tmp_path, manifest, monkeypatch):
    import os

    store = FormalStore(tmp_path / "run")
    store.initialize(manifest)
    original = os.replace

    def broken(source, destination):
        if destination.name == "state.json":
            raise OSError("sensitive disk detail")
        original(source, destination)

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(StorageError, match="start failed"):
        store.start_attempt(manifest["tasks"][0], {})
    assert (store.path / "attempts" / "REQ_000__baseline" / "started.json").exists()
    assert json.loads((store.path / "state.json").read_bytes())["dispatch_count"] == 0
    with pytest.raises(StorageError):
        store.record_call(manifest["tasks"][0])


def test_fixture_accounting_and_fail(tmp_path, manifest):
    manifest["execution_mode"] = "offline_fixture"
    store = FormalStore(tmp_path / "run")
    store.initialize(manifest)
    task = manifest["tasks"][0]
    store.start_attempt(task, {})
    store.record_call(task)
    store.fail(task, "secret raw exception")
    summary = store.summary()
    assert summary["actual_provider_calls"] == 0
    assert summary["provider_fake_calls"] == summary["dispatch_count"] == 1
    assert summary["framework_error"] == 1
    assert summary["formal_eligible"] is False
    assert "secret" not in (store.path / "framework_error.json").read_text()


def test_started_evidence_tamper(tmp_path, manifest):
    store = FormalStore(tmp_path / "run")
    store.initialize(manifest)
    store.start_attempt(manifest["tasks"][0], {"marker": "original"})
    path = store.path / "attempts" / "REQ_000__baseline" / "started.json"
    path.write_text(path.read_text().replace("original", "modified"))
    with pytest.raises(StorageError):
        store.verify()


@pytest.mark.parametrize("failed_name", ["outcome.json", "generation_records.jsonl", "state.json"])
def test_actual_finish_write_failure(tmp_path, manifest, monkeypatch, failed_name):
    store = FormalStore(tmp_path / "run")
    store.initialize(manifest)
    task = manifest["tasks"][0]
    store.start_attempt(task, {})
    store.record_call(task)
    original = store._write

    def broken(path, *args, **kwargs):
        if path.name == failed_name:
            raise OSError("secret filesystem detail")
        original(path, *args, **kwargs)

    monkeypatch.setattr(store, "_write", broken)
    with pytest.raises(StorageError, match="completion failed"):
        store.finish_attempt(task, {"status": "succeeded"})
    store.fail(task, "secret")
    summary = store.summary(verify=False)
    assert summary["integrity_verified"] is False
    assert summary["dispatch_count"] == 1
    assert (store.path / "attempts" / "REQ_000__baseline" / "started.json").exists()
    assert json.loads((store.path / "state.json").read_bytes())["pairs"]["REQ_000__baseline"]["status"] == "running"


def test_sequence_and_attempt_no_mapping(tmp_path, manifest):
    manifest["tasks"][0]["sequence"] = 1
    store = FormalStore(tmp_path / "run")
    store.initialize(manifest)
    task = manifest["tasks"][0]
    for changed in ({**task, "sequence": 2}, {**task, "attempt_no": 2}):
        with pytest.raises(StorageError):
            store.start_attempt(changed, {})


def test_unverified_summary_never_loads_tampered_state(tmp_path, manifest):
    store = FormalStore(tmp_path / "run")
    store.initialize(manifest)
    task = manifest["tasks"][0]
    state_path = store.path / "state.json"
    contaminated = json.loads(state_path.read_bytes())
    contaminated["pairs"]["REQ_000__baseline"]["error_message"] = "secret-state-sentinel"
    state_path.write_text(json.dumps(contaminated), encoding="utf-8")
    before = state_path.read_bytes()
    with pytest.raises(StorageError):
        store.start_attempt(task, {})
    store.fail(task, "unsafe detail")
    assert "secret-state-sentinel" not in json.dumps(store.summary(verify=False))
    assert state_path.read_bytes() == before
    assert (store.path / "framework_error.json").exists()
