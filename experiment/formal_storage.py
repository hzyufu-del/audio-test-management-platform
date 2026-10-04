"""Exclusive, fail-stop formal evidence storage; no network or application imports."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path


class StorageError(ValueError):
    """Fixed safe storage failure."""


class FormalStore:
    def __init__(self, path):
        self.path = Path(path)
        self._manifest_bytes = None
        self._state = None
        self._saved_state = None

    @staticmethod
    def _bytes(value):
        return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")

    def _write(self, path, value, *, immutable=False, raw=False):
        payload = value if raw else self._bytes(value)
        temporary = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if immutable:
                os.link(temporary, path)
            else:
                os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _key(task):
        requirement = task["requirement_id"]
        method = task["method"]
        if (not isinstance(requirement, str) or not requirement
                or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for c in requirement)
                or method not in {"baseline", "proposed"} or task.get("attempt", 1) != 1
                or task.get("attempt_no", 1) != 1):
            raise StorageError("Formal storage integrity check failed.")
        return f"{requirement}__{method}"

    def initialize(self, manifest):
        try:
            self.path.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise StorageError("partial formal experiment detected; manual recovery authorization required") from None
        except OSError:
            raise StorageError("Formal storage write failed.") from None
        try:
            tasks = manifest["tasks"]
            keys = [self._key(task) for task in tasks]
            if len(keys) != 56 or len(set(keys)) != 56 or not manifest["experiment_id"]:
                raise ValueError
            self._manifest_bytes = self._bytes(manifest)
            self._write(self.path / "manifest.json", self._manifest_bytes, immutable=True, raw=True)
            self._write(self.path / "manifest.sha256", hashlib.sha256(self._manifest_bytes).hexdigest().encode(), immutable=True, raw=True)
            self._state = {"formal_experiment": True,
                           "formal_eligible": manifest.get("execution_mode") != "offline_fixture",
                           "dispatch_count": 0, "pairs": {
                               key: {"requirement_id": task["requirement_id"], "method": task["method"],
                                     "attempt": 1, "attempt_no": 1, "status": "not_started", "calls": 0}
                               for key, task in zip(keys, tasks)}}
            self._save()
        except (OSError, ValueError, KeyError, TypeError):
            raise StorageError("Formal storage initialization failed.") from None

    def _save(self):
        self._write(self.path / "state.json", self._state)
        self._saved_state = deepcopy(self._state)

    def _restore_state(self):
        if self._saved_state is not None:
            self._state = deepcopy(self._saved_state)

    def _seal(self, pair, path):
        pair.setdefault("evidence_hashes", {})[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()

    def _pair(self, task, status):
        self.verify()
        key = self._key(task)
        frozen = next((item for item in json.loads(self._manifest_bytes)["tasks"] if self._key(item) == key), None)
        if frozen is None or any(task.get(field) != value for field, value in frozen.items()):
            raise StorageError("Formal attempt mapping rejected.")
        pair = self._state["pairs"].get(key)
        if pair is None or pair["status"] != status:
            raise StorageError("Formal attempt transition rejected.")
        return key, pair

    def start_attempt(self, task, evidence):
        try:
            key, pair = self._pair(task, "not_started")
            if evidence.get("source", pair["method"]) != pair["method"]:
                raise ValueError
            self._write(self.path / "attempts" / key / "started.json",
                        {"pair": key, "attempt": 1, "attempt_no": 1, "source": pair["method"], "evidence": evidence}, immutable=True)
            self._seal(pair, self.path / "attempts" / key / "started.json")
            pair["status"] = "running"
            self._save()
        except (OSError, ValueError, KeyError, TypeError):
            self._restore_state()
            raise StorageError("Formal attempt start failed.") from None

    def record_call(self, task):
        try:
            key, pair = self._pair(task, "running")
            if pair["calls"] != 0 or self._state["dispatch_count"] >= 56:
                raise ValueError
            self._write(self.path / "attempts" / key / "call.json",
                        {"pair": key, "attempt": 1, "attempt_no": 1, "source": pair["method"], "calls": 1}, immutable=True)
            self._seal(pair, self.path / "attempts" / key / "call.json")
            pair["calls"] = 1
            self._state["dispatch_count"] += 1
            self._save()
        except (OSError, ValueError, KeyError, TypeError):
            self._restore_state()
            raise StorageError("Formal call recording failed.") from None

    def _exports(self):
        expected = {}
        for key, pair in self._state["pairs"].items():
            if pair["status"] in {"succeeded", "failed", "framework_error"}:
                outcome = json.loads((self.path / "attempts" / key / "outcome.json").read_bytes())
                record = {**outcome["result"], "pair": key, "requirement_id": pair["requirement_id"],
                          "method": pair["method"], "attempt": 1, "attempt_no": 1}
                filename = "generation_records.jsonl" if pair["method"] == "baseline" else "generation_runs.jsonl"
                expected.setdefault(self.path / pair["method"] / filename, []).append(record)
                expected.setdefault(self.path / pair["method"] / "initial_cases.jsonl", []).append({
                    "pair": key, "requirement_id": pair["requirement_id"], "method": pair["method"],
                    "attempt": 1, "attempt_no": 1, "initial_cases": outcome["result"].get("initial_cases", [])})
        return {path: b"".join(self._bytes(row) for row in rows) for path, rows in expected.items()}

    def finish_attempt(self, task, result):
        try:
            key, pair = self._pair(task, "running")
            status = result["status"]
            if status not in {"succeeded", "failed", "framework_error"}:
                raise ValueError
            self._write(self.path / "attempts" / key / "outcome.json",
                        {"pair": key, "attempt": 1, "attempt_no": 1, "source": pair["method"], "result": result}, immutable=True)
            self._seal(pair, self.path / "attempts" / key / "outcome.json")
            pair["status"] = status
            for path, payload in self._exports().items():
                self._write(path, payload, raw=True)
            self._save()
        except (OSError, ValueError, KeyError, TypeError):
            self._restore_state()
            raise StorageError("Formal attempt completion failed.") from None

    def fail(self, task, code):
        # Never include the caller's exception or free-form code in evidence.
        try:
            self._write(self.path / "framework_error.json", {"status": "framework_error",
                        "code": "formal_framework_error"}, immutable=True)
            # Preserve corrupt disk evidence; only the last successful save is trusted.
            if json.loads((self.path / "state.json").read_bytes()) != self._saved_state:
                self._restore_state()
                return
            if task is not None:
                key = self._key(task)
                pair = self._state["pairs"][key]
                if pair["status"] == "running":
                    outcome = self.path / "attempts" / key / "outcome.json"
                    if outcome.exists():
                        return
                    self._write(outcome, {"pair": key, "attempt": 1, "attempt_no": 1, "source": pair["method"],
                                "result": {"status": "framework_error", "error_type": "formal_framework_error"}}, immutable=True)
                    self._seal(pair, outcome)
                    pair["status"] = "framework_error"
                    for path, payload in self._exports().items():
                        self._write(path, payload, raw=True)
                    self._save()
        except (OSError, ValueError, KeyError, TypeError):
            self._restore_state()

    def verify(self):
        try:
            raw = (self.path / "manifest.json").read_bytes()
            if raw != self._manifest_bytes or hashlib.sha256(raw).hexdigest() != (self.path / "manifest.sha256").read_text():
                raise ValueError
            state = json.loads((self.path / "state.json").read_bytes())
            if state != self._state:
                raise ValueError
            attempt_directories = {path.name for path in (self.path / "attempts").glob("*")}
            if not attempt_directories <= set(state["pairs"]):
                raise ValueError
            for key, pair in state["pairs"].items():
                directory = self.path / "attempts" / key
                if {path.name for path in directory.glob("*")} - {"started.json", "call.json", "outcome.json"}:
                    raise ValueError
                for filename in ("started.json", "call.json", "outcome.json"):
                    path = directory / filename
                    required = ((filename == "started.json" and pair["status"] != "not_started")
                                or (filename == "call.json" and pair["calls"] == 1)
                                or (filename == "outcome.json" and pair["status"] in {"succeeded", "failed", "framework_error"}))
                    if path.exists() != required:
                        raise ValueError
                    if required:
                        if hashlib.sha256(path.read_bytes()).hexdigest() != pair["evidence_hashes"][filename]:
                            raise ValueError
                        record = json.loads(path.read_bytes())
                        if (record["pair"] != key or record["source"] != pair["method"]
                                or record["attempt"] != 1 or record["attempt_no"] != 1):
                            raise ValueError
                        if filename == "outcome.json" and record["result"]["status"] != pair["status"]:
                            raise ValueError
            if state["dispatch_count"] != sum(pair["calls"] for pair in state["pairs"].values()):
                raise ValueError
            exports = self._exports()
            existing_exports = set(self.path.glob("baseline/*.jsonl")) | set(self.path.glob("proposed/*.jsonl"))
            if existing_exports != set(exports):
                raise ValueError
            for path, payload in exports.items():
                if path.read_bytes() != payload:
                    raise ValueError
        except (OSError, ValueError, KeyError, TypeError):
            raise StorageError("Formal storage integrity check failed.") from None

    def summary(self, *, verify=True):
        if verify:
            self.verify()
        pairs = deepcopy(list(self._state["pairs"].values()))
        count = self._state["dispatch_count"]
        eligible = self._state["formal_eligible"]
        return {"planned_pairs": 56, "actual_provider_calls": count if eligible else 0,
                "provider_fake_calls": 0 if eligible else count, "dispatch_count": count,
                "formal_experiment": True, "formal_eligible": eligible, "integrity_verified": verify,
                "pairs": pairs,
                **{status: sum(pair["status"] == status for pair in pairs)
                   for status in ("not_started", "running", "succeeded", "failed", "framework_error")}}
