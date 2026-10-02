# 第二阶段：LLM 实验证据设计

用户已提供本阶段完整设计、授权实施和验收要求；按现有代码落实，不增加第三阶段功能。

## 数据与事务

保留 requirement → Session → test_points → Draft → quality → 人工审核 → TestCase。新增 GenerationRun：成功 Session 对应 N 个 Run，Draft 可选关联来源 Run。历史数据不回填伪造调用。失败发生在 Session 创建前时 session_id 允许 NULL，因此 Run 额外保存 project_id、version_id、title、requirement_text 安全输入快照，以保证失败需求也可追溯；成功时原文仍保留在 Session。

Run 字段：id/session_id/project_id/version_id/title/requirement_text/provider/provider_model/prompt_version/prompt_hash/requirement_hash/status/started_at/finished_at/latency_ms/input_chars/output_chars/prompt_tokens/completion_tokens/total_tokens/finish_reason/temperature/max_tokens/error_type/error_message/structured_output_json/created_at。字符计数 input_chars 是实际静态 system 与序列化 user 消息内容长度之和；output_chars 是 Provider 返回的文本长度（Mock 是稳定序列化结果长度）。缺失 usage、finish_reason、temperature 保留 NULL；不推算 token。

调用前用独立 SQLAlchemy Session 持久化 running Run；无法保存则不调用模型。应用事务提交 Session/Draft 和 Run succeeded 状态；若回滚，独立 Session 将已存在 Run 标为 failed。解析或安全校验失败只保存安全固定错误分类，不保存 raw response；结构化快照仅在 Schema 和安全检查全部通过后保存。数据库完全不可写或进程终止时已提交 running 记录可见，不能保证终态自动恢复。本阶段不增加后台恢复队列。

为已有 Session 提供服务方法 generate_for_session(session_id)，追加新草稿并记录来源 Run，保留旧草稿与审核历史；失败重试不修改 Session 当前结果。Session 展示最新结果，历史以每个 Run 的快照为准。SDK 禁用隐式 retries，使一次 Run 对应一次 Provider 调用。

Run 从 running 到终态仅一次，终态禁止 ORM 修改/删除；ReviewRecord 创建后禁止 ORM 修改/删除。外键 RESTRICT 保护实验 Run/ReviewRecord 的来源和身份；旧 Session 无证据时原有 Draft cascade 保留。约束和迁移一致，历史 migration 不修改。

## Provider 与安全

保持 generate(context) 返回 TestDesignResult 的现有接口，增加 last_call_metadata 安全白名单元数据。DeepSeek 在解析前提取响应 model、usage、finish_reason 和输出字符数；解析失败也能记录 usage。实际发送静态 prompt 来自统一消息构建函数，prompt_hash 为稳定序列化静态消息模板 SHA-256；requirement_hash 为验证后实际发送需求 UTF-8 SHA-256，原文不被 hash 替代。版本继续 test-design-v1。

异常消息用固定安全文案与允许的错误类型，绝不持久化 SDK 异常字符串、请求头、API Key、系统 Prompt 或环境变量。安全检查补充 Authorization/Header 与当前配置中秘密值检查，覆盖生成快照、元数据及审核意见。无需 raw response。

## 审核与 UI

ReviewRecord：id/draft_id/reviewer_user_id/action/before_snapshot_json/after_snapshot_json/score_before/score_after/changed_fields_json/changed_field_count/comment/created_at。before/after 包含九个内容字段、status、accepted_test_case_id；changed 字段只计算九个内容字段，状态变化不会算人工编辑。分数沿用现有质量评分器，表示审核前后 Session 全部草稿集合的质量分，并明确其规则评分性质。

edit/accept/reject 均要求真实已登录用户；操作和审计原子提交；重复操作被现有 pending 状态约束阻止。服务支持显式 reviewer_user_id 用于受信任 CLI，HTTP 一律取 current_user，不接受表单伪造 ID。修改率以至少一次内容变化的草稿数/全部来源草稿数计算，平均修改量为所有 edit 内容字段变化数/发生变化 edit 次数；最终状态按 Draft，审核次数按 ReviewRecord。无操作 edit 记录计审核但不计人工修改。

UI 保持现有布局，详情加调用历史及每草稿审核历史、登录提醒、可选意见；失败无 Session 的 Run 在 AI 列表显示安全摘要。不展示堆栈或 system prompt。

累计草稿使用独立的持久化集合 Schema，保持逐字段验证，20 条数量上限仍仅针对每次 Provider 输出。重试后 Session 分数重新计算全部保留草稿。对于旧数据中已存在的敏感字段，审核快照保存 `[redacted sensitive content]` 并列出 `redacted_fields`；内容变化数量按内存中的原字段计算，既可拒绝旧敏感草稿，也不会把敏感值复制到新证据表。

## 验证与范围

TDD 覆盖成功/失败/回滚、Mock/DeepSeek FakeClient、元数据缺失/hash 变化/秘密过滤、身份与操作顺序、快照及分数、FK/不可变/迁移。保留原 622 测试，对受新增登录要求影响的测试补真实身份 fixture，不删除或放宽业务断言。最终 Ruff、迁移 current/check/外键、完整 pytest-cov >=90%。真实 DeepSeek 仅在全部门槛通过且有环境凭据后调用一次 Demo 需求；无有效凭据标记 pending。不 push，不进行大规模实验。
