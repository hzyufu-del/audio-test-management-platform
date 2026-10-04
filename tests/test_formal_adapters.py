from types import SimpleNamespace

import httpx
import pytest

from experiment.formal_adapters import FormalAdapters

SETTINGS = dict(execute=True, ai_enabled=True, api_key="demo-private-key", secret_key="demo-secret", model="demo-model", base_url="https://api.deepseek.com", timeout_seconds=60, max_output_tokens=8000)
TEXT = "Demo virtual sample login accepts matching credentials."


def test_baseline_calls_once_and_transcribes(tmp_path):
    calls = []
    marks = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(model="demo-model", choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="## 用例 1\n编号：a1\n标题：Demo login\n优先级：高\n"))])
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    adapters = FormalAdapters(tmp_path, SETTINGS, lambda: marks.append(True), client_factory=lambda **kwargs: client)
    result = adapters.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["status"] == "succeeded"
    assert result["sdk_calls"] == 1 and result["failure_origin"] is None
    assert result["normalization"]["normalized"][0]["priority"] == "高"
    assert len(calls) == len(marks) == 1
    adapters.close()


def test_unknown_sdk_exception_is_framework(tmp_path):
    def create(**kwargs):
        raise RuntimeError("secret arbitrary SDK exception")
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    adapters = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = adapters.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "framework" and result["sdk_calls"] == 1
    assert "secret arbitrary" not in str(result)


def test_unknown_method_has_zero_calls(tmp_path):
    adapters = FormalAdapters(tmp_path, SETTINGS, lambda: None)
    result = adapters.generate("wrong", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "framework" and result["sdk_calls"] == 0



def test_proposed_business_chain_and_sources(tmp_path):
    import json
    from test_experiment_adapters import PAYLOAD
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(model="demo-response-model", choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(PAYLOAD)))])
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    adapters = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = adapters.generate("proposed", title="Demo login", requirement_text=TEXT)
    assert result["status"] == "succeeded" and result["sdk_calls"] == 1
    assert result["failure_origin"] is None
    assert result["generation_run_id"] and result["session_id"]
    assert result["initial_cases"][0]["status"] == "pending"
    assert result["initial_cases"][0]["generation_run_id"] == result["generation_run_id"]
    assert calls[0]["response_format"] == {"type": "json_object"}
    adapters.close()


def test_proposed_unknown_sdk_failure_retains_framework_origin(tmp_path):
    def create(**kwargs):
        raise RuntimeError("private unknown failure")
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    adapters = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = adapters.generate("proposed", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "framework" and result["sdk_calls"] == 1
    assert "private unknown" not in str(result)
    adapters.close()


def test_persistent_marker_failure_prevents_sdk_call(tmp_path):
    calls = []
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs))))
    def marker():
        raise OSError("private writer failure")
    adapters = FormalAdapters(tmp_path, SETTINGS, marker, client_factory=lambda **kwargs: client)
    result = adapters.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "framework" and result["sdk_calls"] == 0
    assert not calls
    adapters.close()


def test_nonzero_client_retries_rejected_before_call(tmp_path):
    client = SimpleNamespace(max_retries=2)
    adapters = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = adapters.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "framework" and result["sdk_calls"] == 0
    adapters.close()


def test_api_error_is_method_failure(tmp_path):
    from openai import APIConnectionError
    def create(**kwargs):
        raise APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    adapters = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = adapters.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "method" and result["sdk_calls"] == 1
    adapters.close()


def test_unparseable_baseline_is_failed_retaining_safe_raw(tmp_path):
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ordinary unstructured result"))]))))
    adapters = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = adapters.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "method" and result["status"] == "failed"
    assert result["initial_text"] == "ordinary unstructured result"
    assert result["normalization"]["usable"] is False
    adapters.close()


def test_request_mismatch_and_second_create_are_framework(tmp_path, monkeypatch):
    from experiment import adapters as original
    calls = []
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: calls.append(kwargs))))
    wrapper = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    def bad_generate(self, requirement):
        proxy = self._client()
        request = dict(wrapper._expected)
        request["messages"] = [{"role": "user", "content": "reference sentinel"}]
        proxy.chat.completions.create(**request)
    monkeypatch.setattr(original.BaselineAdapter, "generate", bad_generate)
    result = wrapper.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "framework" and result["sdk_calls"] == 0
    assert not calls
    def double_generate(self, requirement):
        proxy = self._client()
        proxy.chat.completions.create(**wrapper._expected)
        proxy.chat.completions.create(**wrapper._expected)
    monkeypatch.setattr(original.BaselineAdapter, "generate", double_generate)
    result = wrapper.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "framework" and result["sdk_calls"] == 1
    assert len(calls) == 1
    wrapper.close()


def test_secret_output_is_method_failure_without_raw(tmp_path):
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="demo-private-key"))]))))
    wrapper = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = wrapper.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "method" and result["initial_text"] is None
    assert "demo-private-key" not in str(result)
    wrapper.close()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network transport is forbidden in formal adapter tests.")
    monkeypatch.setattr(httpx.Client, "send", blocked)


def test_baseline_initial_cases_are_exact_normalized_nine_fields(tmp_path):
    content = "## 用例 1\n编号：a1\n标题：Demo login\n优先级：p1\n"
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))]))))
    wrapper = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = wrapper.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["status"] == "succeeded"
    assert result["initial_cases"] == result["normalization"]["normalized"]
    assert result["initial_cases"][0]["priority"] == "p1"
    wrapper.close()


def test_authentication_api_error_is_method_failure(tmp_path):
    from openai import AuthenticationError
    def create(**kwargs):
        request = httpx.Request("POST", "https://example.invalid")
        raise AuthenticationError("private SDK response", response=httpx.Response(401, request=request), body=None)
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    wrapper = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = wrapper.generate("proposed", title="Demo login", requirement_text=TEXT)
    assert result["status"] == "failed" and result["failure_origin"] == "method"
    assert result["sdk_calls"] == 1
    assert "private SDK response" not in str(result)
    wrapper.close()


def test_normalization_exception_is_framework_after_one_call(tmp_path, monkeypatch):
    import experiment.formal_adapters as module
    def broken(text):
        raise RuntimeError("private parser exception")
    monkeypatch.setattr(module, "transcribe", broken)
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="## 用例 1\n编号：a1\n"))]))))
    wrapper = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = wrapper.generate("baseline", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "framework" and result["sdk_calls"] == 1
    assert "private parser" not in str(result)
    wrapper.close()


def test_proposed_real_database_misbound_source_is_framework(tmp_path, monkeypatch):
    import json
    from experiment import formal_adapters as module
    from test_experiment_adapters import PAYLOAD
    original = module.adapters.ProposedAdapter._export
    def misbind(self, record, run, context, version_id):
        # Change only the verifier's expected identity; actual DB provenance remains real.
        return original(self, record, run, context, version_id + 1)
    monkeypatch.setattr(module.adapters.ProposedAdapter, "_export", misbind)
    client = SimpleNamespace(max_retries=0, chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(PAYLOAD)))]))))
    wrapper = FormalAdapters(tmp_path, SETTINGS, lambda: None, client_factory=lambda **kwargs: client)
    result = wrapper.generate("proposed", title="Demo login", requirement_text=TEXT)
    assert result["failure_origin"] == "framework" and result["sdk_calls"] == 1
    assert result["initial_cases"] == []
    wrapper.close()
