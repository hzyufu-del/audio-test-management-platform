import copy

import pytest

from app import create_app
from app.extensions import db
from app.models import Project, TestCase as ChecklistTestCase, Version
from app.services.ai.exceptions import AIProviderError
from app.services.ai.provider import AIProvider
from app.services.ai.schemas import (
    IssueCategory,
    IssueSeverity,
    ReviewConfidence,
    SemanticReviewResult,
    TestCaseQualityIssue as QualityIssue,
)


class StaticDeepSeekProvider(AIProvider):
    provider_name = "deepseek"
    is_demo = False

    def review_test_case(self, context):
        return SemanticReviewResult(
            summary="DeepSeek mock response for route testing.",
            issues=[],
            missing_preconditions=[],
            ambiguous_expectations=[],
            missing_test_scenarios=[],
            rewrite_suggestions=["Use one observable sample result."],
            confidence=ReviewConfidence.HIGH,
            limitations=["The provider was monkeypatched; no network was used."],
        )


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "testcase_ai_routes.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
            "AI_ENABLED": True,
            "AI_PROVIDER": "mock",
        }
    )
    with app.app_context():
        db.create_all()
        project = Project(
            name="Mock AI Route Project",
            code="MOCK-AI-ROUTE",
            status="active",
        )
        db.session.add(project)
        db.session.flush()
        version = Version(
            project_id=project.id,
            name="Demo AI Route Version",
            code="FW_DEMO_AI_ROUTE",
            status="testing",
        )
        db.session.add(version)
        db.session.flush()
        test_case = ChecklistTestCase(
            version_id=version.id,
            title="Sample Bluetooth Route Review",
            code="TC_AI_ROUTE_001",
            module="Bluetooth",
            priority="P1",
            case_type="checklist",
            precondition="",
            steps="1. Open Demo settings.\n2. Connect Sample accessory.",
            expected_result="显示正常",
            status="active",
        )
        db.session.add(test_case)
        db.session.commit()
        app.config["TESTCASE_AI_TEST_ID"] = test_case.id

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_ai_review_route_is_registered_as_post(client, app):
    response = client.post(
        f"/test-cases/{app.config['TESTCASE_AI_TEST_ID']}/ai-review"
    )

    assert response.status_code == 200


def test_missing_testcase_ai_review_returns_404(client):
    response = client.post("/test-cases/999999/ai-review")

    assert response.status_code == 404


def test_original_detail_page_shows_optional_ai_review_state(client, app):
    response = client.get(
        f"/test-cases/{app.config['TESTCASE_AI_TEST_ID']}"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AI 用例质量审查" in page
    assert "AI 检查用例" in page
    assert "等待检查" in page
    assert "不能替代需求确认、测试设计评审或人工判断" in page
    assert "审查结果不会自动修改或保存 TestCase" in page


def test_disabled_ai_review_shows_friendly_message_without_provider_call(
    client,
    app,
    monkeypatch,
):
    from app.services.ai.mock_provider import MockAIProvider

    app.config["AI_ENABLED"] = False

    def forbidden_provider_call(self, context):
        raise AssertionError("Provider must not be called while AI is disabled")

    monkeypatch.setattr(
        MockAIProvider,
        "review_test_case",
        forbidden_provider_call,
    )
    response = client.post(
        f"/test-cases/{app.config['TESTCASE_AI_TEST_ID']}/ai-review"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AI 审查当前未启用" in page


def test_mock_provider_review_renders_score_rule_and_semantic_sections(
    client,
    app,
):
    response = client.post(
        f"/test-cases/{app.config['TESTCASE_AI_TEST_ID']}/ai-review"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "启发式质量评分" in page
    assert "Demo AI Review" in page
    assert "规则检查问题" in page
    assert "预期结果主要由模糊词组成" in page
    assert "AI 语义问题" in page
    assert "Demo AI Review 已完成确定性的语义提示生成" in page
    assert "置信度" in page
    assert "局限性" in page
    assert "不是正式评审结论" in page


def test_deepseek_provider_can_be_monkeypatched_without_network(
    client,
    app,
    monkeypatch,
):
    import app.services.testcase_ai_service as service_module

    app.config.update(
        AI_PROVIDER="deepseek",
        DEEPSEEK_API_KEY="local-test-key",
        DEEPSEEK_MODEL="demo-current-model",
    )
    monkeypatch.setattr(
        service_module,
        "DeepSeekProvider",
        lambda **kwargs: StaticDeepSeekProvider(),
    )

    response = client.post(
        f"/test-cases/{app.config['TESTCASE_AI_TEST_ID']}/ai-review"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "DeepSeek AI Review" in page
    assert "DeepSeek mock response for route testing" in page


def test_provider_failure_returns_friendly_page_instead_of_500(
    client,
    app,
    monkeypatch,
):
    from app.services.ai.mock_provider import MockAIProvider

    def unavailable(self, context):
        raise AIProviderError("AI 服务暂时不可用，请稍后重试。")

    monkeypatch.setattr(MockAIProvider, "review_test_case", unavailable)
    response = client.post(
        f"/test-cases/{app.config['TESTCASE_AI_TEST_ID']}/ai-review"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "检查失败" in page
    assert "AI 服务暂时不可用，请稍后重试" in page


def test_ai_output_is_autoescaped_and_never_rendered_as_safe_html(
    client,
    app,
    monkeypatch,
):
    from app.services.ai.mock_provider import MockAIProvider

    def unsafe_result(self, context):
        return SemanticReviewResult(
            summary="<script>sampleUnsafe()</script>",
            issues=[
                QualityIssue(
                    category=IssueCategory.OTHER,
                    severity=IssueSeverity.INFO,
                    description="<b>unsafe description</b>",
                    evidence="<img src=x onerror=sampleUnsafe()>",
                    suggestion="Render as plain text only.",
                )
            ],
            missing_preconditions=[],
            ambiguous_expectations=[],
            missing_test_scenarios=[],
            rewrite_suggestions=[],
            confidence=ReviewConfidence.LOW,
            limitations=["Sample HTML-like data must remain escaped."],
        )

    monkeypatch.setattr(MockAIProvider, "review_test_case", unsafe_result)
    response = client.post(
        f"/test-cases/{app.config['TESTCASE_AI_TEST_ID']}/ai-review"
    )
    page = response.get_data(as_text=True)

    assert "<script>sampleUnsafe()</script>" not in page
    assert "&lt;script&gt;sampleUnsafe()&lt;/script&gt;" in page
    assert "<b>unsafe description</b>" not in page
    assert "&lt;b&gt;unsafe description&lt;/b&gt;" in page
    assert "|safe" not in page


def test_review_does_not_change_testcase_or_create_records(client, app):
    with app.app_context():
        test_case = db.session.get(
            ChecklistTestCase,
            app.config["TESTCASE_AI_TEST_ID"],
        )
        before = copy.deepcopy(
            {
                key: getattr(test_case, key)
                for key in (
                    "title",
                    "code",
                    "module",
                    "priority",
                    "case_type",
                    "precondition",
                    "steps",
                    "expected_result",
                    "status",
                )
            }
        )
        counts_before = (
            Project.query.count(),
            Version.query.count(),
            ChecklistTestCase.query.count(),
        )

    response = client.post(
        f"/test-cases/{app.config['TESTCASE_AI_TEST_ID']}/ai-review"
    )
    assert response.status_code == 200

    with app.app_context():
        test_case = db.session.get(
            ChecklistTestCase,
            app.config["TESTCASE_AI_TEST_ID"],
        )
        after = {key: getattr(test_case, key) for key in before}
        assert after == before
        assert counts_before == (
            Project.query.count(),
            Version.query.count(),
            ChecklistTestCase.query.count(),
        )


def test_review_result_disappears_after_refresh(client, app):
    testcase_id = app.config["TESTCASE_AI_TEST_ID"]
    reviewed = client.post(f"/test-cases/{testcase_id}/ai-review")
    refreshed = client.get(f"/test-cases/{testcase_id}")
    reviewed_page = reviewed.get_data(as_text=True)

    assert "window.history.replaceState" in reviewed_page
    assert f'"/test-cases/{testcase_id}"' in reviewed_page
    assert "启发式质量评分" in reviewed.get_data(as_text=True)
    assert "启发式质量评分" not in refreshed.get_data(as_text=True)
    assert "等待检查" in refreshed.get_data(as_text=True)
