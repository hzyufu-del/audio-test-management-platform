"""Rendering and real JavaScript event checks for generation UI recovery."""

from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

from flask import render_template
from flask_login import login_user
import pytest

from app import create_app


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def by_id(self, element_id):
        return next(attrs for _, attrs in self.elements if attrs.get("id") == element_id)


@pytest.fixture()
def ui_app():
    app = create_app({
        "TESTING": True, "AI_PROVIDER": "mock", "AI_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "demo-ui-test-secret",
    })
    # Supports standalone template validation before the backend is integrated.
    if "ai_test_design.run_detail" not in app.view_functions:
        app.add_url_rule("/ai-test-design/runs/<int:run_id>",
                         endpoint="ai_test_design.run_detail", view_func=lambda run_id: "")
    return app


def render_new(app, **overrides):
    context = {
        "errors": [], "projects": [], "versions": [],
        "form_data": {"title": "Demo", "project_id": "", "version_id": "",
                      "requirement_text": "Sample requirement with enough details."},
        "request_key": "demo-request-key", "runtime_provider": "mock",
        "runtime_ai_enabled": False, "runtime_config_error": "",
    }
    context.update(overrides)
    with app.test_request_context():
        return render_template("ai_test_design/new.html", **context)


def test_generation_form_posts_request_key_and_identifies_mock(ui_app):
    html = render_new(ui_app)
    elements = Elements(html)
    assert any(tag == "input" and attrs.get("name") == "request_key"
               and attrs.get("value") == "demo-request-key"
               for tag, attrs in elements.elements)
    assert "disabled" not in elements.by_id("generate-button")
    assert elements.by_id("generation-status")["aria-live"] == "polite"
    assert "Mock 模拟生成" in html and "不会调用真实大模型" in html


@pytest.mark.parametrize("settings", [
    {"runtime_provider": "invalid", "runtime_config_error": "Invalid configuration"},
    {"runtime_provider": "deepseek", "runtime_ai_enabled": False},
])
def test_unavailable_provider_disables_submit_without_claiming_mock_success(ui_app, settings):
    html = render_new(ui_app, **settings)
    assert "disabled" in Elements(html).by_id("generate-button")
    assert "Mock 模拟生成" not in html
    assert "不会自动切换到 Mock" in html


def test_real_provider_label_is_configuration_not_success(ui_app):
    html = render_new(ui_app, runtime_provider="deepseek", runtime_ai_enabled=True)
    assert "DeepSeek 真实 Provider" in html
    assert "配置已启用不代表请求已经成功" in html
    assert "disabled" not in Elements(html).by_id("generate-button")


def test_failed_form_retains_input_and_links_record_with_escaped_error(ui_app):
    html = render_new(ui_app, errors=["<script>demo</script>"], failed_run_id=13)
    assert "&lt;script&gt;demo&lt;/script&gt;" in html
    assert '<script>demo</script>' not in html
    assert '/ai-test-design/runs/13' in html
    assert 'value="Demo"' in html


@pytest.mark.parametrize("status", ["running", "failed", "succeeded"])
def test_run_page_is_query_only_and_exposes_result_appropriately(ui_app, status):
    run = SimpleNamespace(
        id=5, title="Demo run", provider="mock", provider_model=None,
        project=SimpleNamespace(name="Demo project"), version=SimpleNamespace(name="Demo version"),
        prompt_version="test-design-v3", status=status, started_at=datetime.now(timezone.utc),
        finished_at=None, latency_ms=None, total_tokens=None, finish_reason=None,
        session_id=7 if status == "succeeded" else None,
        error_message="Safe failure" if status == "failed" else None,
    )
    summary = {"stage": "schema", "error_categories": ["missing_field"],
               "field_paths": ["case_drafts[0].steps"], "error_count": 1}
    with ui_app.test_request_context():
        html = render_template("ai_test_design/run.html", run=run, validation_summary=summary)
    assert "case_drafts[0].steps" in html and "missing_field" in html
    assert "刷新状态（仅查询）" in html
    # The only POST form is the optional base-template logout form, never generation.
    assert not any(tag == "form" and attrs.get("action", "").startswith("/ai-test-design")
                   for tag, attrs in Elements(html).elements)
    if status == "running":
        assert "运行中或结果待确认" in html
        assert "重新填写并手动提交" not in html
        assert "查看并审核草稿" not in html
    elif status == "failed":
        assert "重新填写并手动提交" in html
        assert "查看并审核草稿" not in html
    else:
        assert 'href="/ai-test-design/7"' in html
        assert "查看并审核草稿" in html


def test_submit_lock_and_back_navigation_execute_real_javascript():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for JavaScript event validation")
    script_path = Path(__file__).resolve().parents[1] / "app/static/js/test-design-generation.js"
    harness = r'''
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const code = fs.readFileSync(process.argv[1], "utf8");
function setup(blocked = false) {
  const handlers = {}, globalHandlers = {};
  const form = {valid:true, attributes:{}, addEventListener:(name, fn) => handlers[name] = fn,
    checkValidity(){return this.valid;}, setAttribute(name,value){this.attributes[name]=value;},
    removeAttribute(name){delete this.attributes[name];}};
  const button = {disabled:blocked, textContent:"Generate drafts"};
  const status = {hidden:true, textContent:""};
  const elements = {"generation-form":form, "generate-button":button, "generation-status":status};
  vm.runInNewContext(code, {document:{getElementById:id=>elements[id]},
    window:{addEventListener:(name,fn)=>globalHandlers[name]=fn}});
  function submit(prevented = false) {
    const event = {defaultPrevented:prevented, preventDefault(){this.defaultPrevented=true;}};
    handlers.submit(event);
    return event;
  }
  return {form,button,status,globalHandlers,submit};
}
const test = setup();
test.form.valid = false;
test.submit();
assert.equal(test.button.disabled,false,"invalid form must remain editable");
test.form.valid = true;
test.submit(true);
assert.equal(test.button.disabled,false,"other handlers may cancel submission");
assert.equal(test.submit().defaultPrevented,false,"first valid POST proceeds");
assert.equal(test.button.disabled,true);
assert.equal(test.form.attributes["aria-busy"],"true");
assert.equal(test.submit().defaultPrevented,true,"double click must not post twice");
test.globalHandlers.offline();
assert.equal(test.button.disabled,true,"unknown network result cannot trigger a retry");
assert.match(test.status.textContent,/服务端可能仍在处理/);
test.globalHandlers.pageshow();
assert.equal(test.button.disabled,false,"back navigation restores the form");
assert.equal(test.status.hidden,true);
assert.equal(test.form.attributes["aria-busy"],undefined);
assert.equal(test.submit().defaultPrevented,false,"server checks replay of preserved key");
const blocked = setup(true);
blocked.globalHandlers.pageshow();
assert.equal(blocked.button.disabled,true,"configuration failure must stay blocked");
assert.equal(blocked.submit().defaultPrevented,true);
console.log("submit lock, offline uncertainty, pageshow and configuration guards passed");
'''
    completed = subprocess.run([node, "-e", harness, str(script_path)],
                               capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("template,stale_submission", [
    ("edit_draft.html", False), ("detail.html", False), ("edit_draft.html", True),
])
def test_review_forms_include_loaded_draft_and_session_revisions(ui_app, template, stale_submission):
    session = SimpleNamespace(
        id=17, title="Demo session", review_revision=6, status="generated",
        project=SimpleNamespace(name="Demo project"), version=SimpleNamespace(name="Demo version"),
        provider="mock", provider_model=None, prompt_version="test-design-v3",
        requirement_text="Demo requirement with observable outcomes.",
    )
    draft = SimpleNamespace(
        id=23, session_id=17, session=session, revision=4, status="pending",
        suggested_code="DEMO-01", title="Demo draft", module="Demo", priority="P1",
        case_type="functional", scenario_type="positive", precondition="Demo ready",
        steps="Perform sample action", expected_result="Observe sample result",
        accepted_test_case=None,
    )
    session.drafts = [draft]
    form_data = {field: getattr(draft, field) for field in (
        "suggested_code", "title", "module", "priority", "case_type", "scenario_type",
        "precondition", "steps", "expected_result",
    )}
    context = {
        "draft": draft, "session": session, "form_data": form_data, "errors": [],
        "priorities": ["P1"], "case_types": ["functional"], "scenario_types": ["positive"],
        "assessment": SimpleNamespace(quality_score=100, dimension_scores={}, missing_scenarios=[],
                                      deduction_reasons=[], risk_warnings=[]),
        "generation_runs": [], "review_history": {23: []}, "test_points": [], "limitations": [],
        "metrics": SimpleNamespace(edited_drafts=0, total_drafts=1, edit_rate=0,
                                   average_changed_fields=0, accepted_count=0, acceptance_rate=0,
                                   rejected_count=0, rejection_rate=0, review_count=0),
    }
    if stale_submission:
        context.update(draft_revision="3", session_revision="5", errors=["Draft changed"])
    with ui_app.test_request_context():
        login_user(SimpleNamespace(is_active=True, is_authenticated=True,
                                   get_id=lambda: "1", username="Demo reviewer"))
        html = render_template("ai_test_design/" + template, **context)
    hidden = {attrs["name"]: attrs.get("value") for tag, attrs in Elements(html).elements
              if tag == "input" and attrs.get("type") == "hidden"}
    assert hidden["draft_revision"] == ("3" if stale_submission else "4")
    assert hidden["session_revision"] == ("5" if stale_submission else "6")
    if stale_submission:
        assert 'href="/ai-test-design/drafts/23/edit"' in html
        assert "重新加载当前草稿" in html
    if template == "detail.html":
        assert 'action="/ai-test-design/drafts/23/accept"' in html
        assert 'formaction="/ai-test-design/drafts/23/reject"' in html
    else:
        assert 'name="steps"' in html and "Perform sample action" in html
    assert 'name="comment"' in html
