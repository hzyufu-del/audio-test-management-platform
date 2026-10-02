# LLM Experiment Foundation Implementation Plan

> **For agentic workers:** Use subagent-driven-development and dispatching-parallel-agents for independent file ownership; root integrates and reviews. User requests execution in this session.

**Goal:** 建立可追溯生成调用、人工审核及真实调用实验数据基础。

**Architecture:** 两个证据实体旁接现有链路。独立提交 running 记录保护模型调用证据，业务提交原子完成成功状态或独立保存失败；审核原子提交。

**Tech Stack:** Flask, SQLAlchemy, Alembic, SQLite, Pydantic, OpenAI SDK, pytest-cov, Ruff.

## Global Constraints

- 不删除原 622 测试，不 skip，不降低 coverage >=90%。
- 不保存 API Key、Authorization、完整环境变量、raw response、system prompt。
- 仅 Mock/DeepSeek，不新增第三阶段功能，不 push。
- 修改历史 migration 禁止；原库迁移前备份。
- 工作分支 thesis/llm-experiment-foundation；第一阶段 baseline 5313745。

## Task 1: 实体与新迁移

Files: app/models.py; migrations/versions/d7e2f6a9b301_add_llm_experiment_evidence.py; tests/test_experiment_models.py; tests/test_experiment_migration.py.

Interfaces: GenerationRun / ReviewRecord 字段遵循设计文档；Session.generation_runs / Draft.generation_run_id / Draft.review_records。外键保护已有证据；旧数据不伪造记录。

- [x] 写约束、关系、可空元数据、FK RESTRICT、不可变及旧数据迁移测试；先运行确认新实体缺失失败。
- [x] 实现实体和新增 revision d7e2f6a9b301，down_revision c5d8a9e4f2b1；测试 fresh upgrade、旧数据升级、downgrade、check。
- [x] 执行 `.venv/Scripts/python.exe -m pytest tests/test_experiment_models.py tests/test_experiment_migration.py`，审查 diff。

## Task 2: Provider 元数据与实际模板 hash

Files: app/services/test_design/provider.py; deepseek_provider.py; mock_provider.py; prompts.py; tests/test_generation_provider_metadata.py.

Interfaces: last_call_metadata 为 GenerationMetadata frozen dataclass，字段 provider_model/prompt_tokens/completion_tokens/total_tokens/finish_reason/temperature/max_tokens/input_chars/output_chars；每次调用重置。prompts.build_test_design_messages(context) / prompt_hash() / requirement_hash(text)。generate 返回接口保持。

- [x] FakeClient 验证实际发出消息、usage 有/无、解析失败元数据、model/finish_reason、无隐式重试；测试模板实际变化导致 hash 变化；先运行 RED。
- [x] 实现安全白名单元数据，Mock 缺失 token 为 None；SDK max_retries=0。
- [x] 执行新测试与现有 Provider 测试，审查 diff。

## Task 3: Run 生命周期与审核服务

Files: app/services/test_design_service.py; app/services/test_design/evidence.py; app/services/test_design/reviews.py; tests/test_generation_runs.py; tests/test_review_records.py; tests/test_ai_test_design_service.py.

Interfaces: create_session 兼容；generate_for_session(session_id) 追加有来源 Run 草稿；update_draft(draft_id,data,*,reviewer_user_id=None,comment=None)、accept_draft/reject_draft 同参数。未指定身份取 current_user，不存在真实 User 则拒绝。

- [x] 先新增调用成功、失败、业务 commit 回滚、running commit 失败禁止调用、同 Session 多 Run、安全错误/快照、匿名审核拒绝、edit→accept/reject 与评分/changed count/原子回滚测试，实际 RED。
- [x] 实现独立证据事务、审计快照/指标；旧 service 审核测试补身份，业务断言保留。
- [x] 执行上述测试及全部 AI service 测试，审查事务与敏感值白名单。

## Task 4: 认证路由与最小 UI

Files: app/blueprints/ai_test_design/routes.py; app/templates/ai_test_design/{detail,index,edit_draft}.html; tests/test_experiment_routes.py; tests/test_ai_test_design_routes.py.

- [x] RED：匿名 edit GET/POST、accept/reject 转登录，登录后记录准确 user，伪造身份表单不生效，UI 展示 Run/Review 及缺失 usage。
- [x] 登录装饰器与 comment 表单；列表失败 Run 摘要；详情 evidence 历史。旧 route fixture 对审核登录，匿名行为新测试保留。
- [x] 执行路由测试与 HTML 检查，审查 diff。

## Task 5: 验证、一次真实 Smoke 与报告

Files: docs/llm-experiment-foundation-2026-10-01.md; README.md; scripts/llm_generation_smoke.py; ignored instance evidence.

- [x] 原 SQLite backup，核验表数量/旧记录摘要；执行 db upgrade/current/check 和 PRAGMA foreign_key_check。
- [x] Ruff + 全套 pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90；确认测试增量与旧函数保留。
- [x] 代码审查闭环。无有效环境凭据真实 Smoke pending；具备条件仅一次 Demo 调用，保存真实元数据。
- [x] 写完整报告：Git、实际实体关系、迁移、模型与人工证据、Smoke 真值、测试真实统计、剩余项及正式实验判断。完成即停止。

## Final verification and recovery

2026-10-02 recovery verified saved state. GenerationRun atomic terminal predicate uses SQLAlchemy status version locking; deterministic race test passes. Full regression after the fix completed in background: 854 passed, 361 warnings, 120.71s, 95.14% line coverage. New232 cases, old622 preserved. Ruff/current/check/FK/integrity and unchanged old rows reconfirmed. One authorized real DeepSeek smoke failed schema with finish_reason=length at2000 output tokens; Run retained. No second API call, push, new migration or third-stage work. Final report is docs/llm-experiment-foundation-2026-10-01.md.
