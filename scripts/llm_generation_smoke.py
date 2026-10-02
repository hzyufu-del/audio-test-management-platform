"""Run one explicit Demo call; never retry or print credential/config dumps."""

import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEMO_REQUIREMENT = (
    "Demo 用户登录接口（完全虚构的演示需求）：用户名和密码为必填字段；"
    "密码长度为 8～20 位；连续输入错误密码 5 次后账号锁定 10 分钟；"
    "登录成功返回访问令牌。所有数据均为 demo，无真实账号或凭据。"
)
DEMO_TITLE = "Demo login API thesis smoke"
SMOKE_MAX_OUTPUT_TOKENS = 8000
SMOKE_TIMEOUT_SECONDS = 60


def inspect_closed_loop(run, session):
    """Check persisted rows against the strictly validated call snapshot."""
    from pydantic import ValidationError

    from app.services.test_design.prompts import PROMPT_VERSION, prompt_hash, requirement_hash
    from app.services.test_design.schemas import TestDesignResult
    from app.services.test_design_service import TestDesignService

    checks = dict(schema_validation=False, session_persisted=session is not None,
                  drafts_persisted=False, draft_sources_valid=False, closed_loop_validated=False)
    try:
        snapshot = TestDesignResult.model_validate_json(run.structured_output_json)
    except (ValidationError, ValueError, TypeError):
        return checks
    checks["schema_validation"] = True
    if session is None:
        return checks
    checks["drafts_persisted"] = bool(session.drafts)
    checks["draft_sources_valid"] = bool(session.drafts) and all(
        draft.session_id == session.id and draft.generation_run_id == run.id
        and draft.status == "pending" and draft.accepted_test_case_id is None
        for draft in session.drafts
    )
    try:
        saved = TestDesignService.session_result(session).model_dump(mode="json")
    except (ValidationError, ValueError, TypeError):
        return checks
    expected = snapshot.model_dump(mode="json")
    # Draft relationship ordering is not part of the persistence contract.
    def canonical(rows):
        return sorted(json.dumps(row, sort_keys=True) for row in rows)
    checks["closed_loop_validated"] = (
        run.status == "succeeded" and run.finish_reason == "stop"
        and run.provider == session.provider == "deepseek"
        and run.provider_model == session.provider_model
        and run.session_id == session.id and session.status == "generated"
        and (run.project_id, run.version_id) == (session.project_id, session.version_id)
        and run.title == session.title == DEMO_TITLE
        and run.requirement_text == session.requirement_text == DEMO_REQUIREMENT
        and run.prompt_version == session.prompt_version == PROMPT_VERSION
        and run.prompt_hash == prompt_hash()
        and run.requirement_hash == requirement_hash(DEMO_REQUIREMENT)
        and run.finished_at is not None and run.error_type is None
        and checks["draft_sources_valid"]
        and saved["test_points"] == expected["test_points"]
        and canonical(saved["case_drafts"]) == canonical(expected["case_drafts"])
        and saved["limitations"] == expected["limitations"]
    )
    return checks


def execute_smoke(app, *, project_id, version_id, execute=False):
    from app.extensions import db
    from app.models import GenerationRun, TestDesignSession
    from app.services.ai.exceptions import AIReviewError
    from app.services.test_design_service import TestDesignService, TestDesignValidationError
    from app.services.workflow_errors import WorkflowServiceError
    from app.services.test_design.evidence import safe_text
    from app.services.test_design.prompts import requirement_hash

    report = {"executed": False, "provider": "deepseek", "model": None,
              "result": "pending: execution not requested",
              "schema_validation": None, "generation_run_persisted": False,
              "token_usage": None, "latency_ms": None,
              "closed_loop_validated": False, "session_persisted": False,
              "drafts_persisted": False, "draft_sources_valid": False}
    if not app.config.get("DEEPSEEK_API_KEY"):
        report["result"] = "pending: missing valid API credential"
        return report
    if not execute:
        return report
    with app.app_context():
        matching = GenerationRun.query.filter_by(
            provider="deepseek", project_id=project_id, version_id=version_id,
            title=DEMO_TITLE, requirement_hash=requirement_hash(DEMO_REQUIREMENT),
        )
        existing_ids = {r.id for r in matching.all()}
        config = dict(app.config)
        config.update(AI_PROVIDER="deepseek", AI_ENABLED=True,
                      AI_MAX_OUTPUT_TOKENS=SMOKE_MAX_OUTPUT_TOKENS,
                      AI_REQUEST_TIMEOUT_SECONDS=SMOKE_TIMEOUT_SECONDS)
        report.update(requested_model=safe_text(config.get("DEEPSEEK_MODEL"), 120, config),
                      timeout_seconds=SMOKE_TIMEOUT_SECONDS, result="failed")
        session_id = None
        try:
            session = TestDesignService(config).create_session(
                project_id=project_id, version_id=version_id,
                title=DEMO_TITLE, requirement_text=DEMO_REQUIREMENT,
            )
        except (AIReviewError, WorkflowServiceError, TestDesignValidationError):
            # Stored evidence has an allowlisted error; raw exception not emitted.
            report["result"] = "failed"
        else:
            session_id = session.id
        # Verify durable data rather than the in-memory returned object.
        db.session.expire_all()
        new_runs = [r for r in matching.order_by(GenerationRun.id).all() if r.id not in existing_ids]
        if len(new_runs) == 1:
            run = new_runs[0]
            report.update(
                executed=True, model=run.provider_model, run_id=run.id,
                status=run.status, generation_run_persisted=True,
                latency_ms=run.latency_ms, finish_reason=run.finish_reason,
                max_tokens=run.max_tokens, input_chars=run.input_chars, output_chars=run.output_chars,
                prompt_version=run.prompt_version,
                token_usage={"prompt_tokens": run.prompt_tokens,
                             "completion_tokens": run.completion_tokens,
                             "total_tokens": run.total_tokens},
                prompt_hash=run.prompt_hash, requirement_hash=run.requirement_hash,
            )
            saved_session = db.session.get(TestDesignSession, session_id) if session_id else None
            report.update(inspect_closed_loop(run, saved_session))
            if report["closed_loop_validated"]:
                report.update(result="succeeded", session_id=saved_session.id,
                              test_point_count=len(json.loads(saved_session.test_points_json)),
                              draft_count=len(saved_session.drafts),
                              draft_ids=[draft.id for draft in saved_session.drafts])
            else:
                report["safe_error"] = "Persisted Smoke evidence did not pass closure checks."
            if run.error_type:
                report["error_type"] = run.error_type
                report["safe_error"] = run.error_message
                if run.error_type == "AIConfigurationError":
                    report["result"] = "pending: missing valid API credential"
        else:
            report["safe_error"] = "Smoke did not find exactly one matching generation record."
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--version-id", type=int, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    from app import create_app
    report = execute_smoke(create_app(), project_id=args.project_id,
                           version_id=args.version_id, execute=args.execute)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["result"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
