# DeepSeek Smoke 定点修复计划

**Goal:** 一条虚拟需求完成真实 Provider → 严格校验 → GenerationRun/Session/Draft 持久化闭环，不进入正式实验。

**Architecture:** 沿用已批准的第二阶段数据模型、事务和安全边界。修复实际提示词的结构说明和输出规模，Smoke 使用局部有限预算；重新读库校验唯一调用来源和所有草稿。

**Constraints:** 保留旧失败 Run 和所有现有修改；不新增 migration、实体或正式 TestCase；不修改 `.env`；SDK 禁重试；本轮真实调用一次；不提交或推送。

## 1. 明确输出合同并验证失败

- [x] 在 `tests/test_generation_provider_metadata.py` 验证完整 JSON 示例符合既有 Schema，以及 `length` 即使返回可解析 JSON 也不能当成成功。
- [x] 执行测试，确认现有代码失败；在 `app/services/test_design/prompts.py` 补齐枚举、字符串类型、示例和 3～6 条简短输出限制。
- [x] 将 Prompt version 更新为 `test-design-v2`，Service 和 Recorder 共用常量，历史记录/seed 不改写；Provider 拒绝截断响应但保留 metadata。

## 2. 修复 Smoke 验收

- [x] 在 `tests/test_llm_generation_smoke.py` 用 FakeClient 覆盖真实适配器成功、截断失败、并发无关 Run、缺失持久化证据和禁隐式执行。
- [x] RED 后修复 `scripts/llm_generation_smoke.py`：仅局部配置 8,000 输出 token / 60 秒；一次 Provider 请求；唯一匹配本需求的新 Run；重新读库检查 Run/Session/草稿/快照/hash 一致，输出安全诊断。
- [x] 定向测试与 Ruff 通过后进行独立代码复核。

## 3. 真实验收与收尾

- [x] 全量 pytest-cov ≥90%，migration current/check 和 Git diff check。
- [x] 对当前 SQLite 做新备份并记录运行前状态，保留上一轮证据；显式调用一次原虚拟登录需求。
- [x] 核验成功 Run、Session、待审核草稿、安全、旧数据和 `.env` 未变；保留本次安全报告。
- [x] 更新第二阶段报告，明确本轮验收结果，不进行正式实验或第三阶段。

最终证据：861 passed，360 warnings，128.50 s，95.14% 行覆盖；原有 622 项保留，累计新增 239 项。真实调用仅一次，Run 2 / Session 1 / 6 测试点 / 6 待审核草稿，succeeded/stop，严格快照和来源一致。旧失败 Run 1、旧业务行和 `.env` 未变；migration 仍为 d7e2f6a9b301。完整结果见 `docs/llm-experiment-foundation-2026-10-01.md` 第 11 节。
