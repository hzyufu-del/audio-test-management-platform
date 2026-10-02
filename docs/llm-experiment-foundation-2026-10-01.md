# 第二阶段 LLM 实验数据基础：实现与验收报告

毕业设计题目：《基于大语言模型的智能测试用例生成与管理系统设计与实现》。初次实施、回归及失败 Smoke：2026-10-01；网络恢复复核与单条真实成功 Smoke 补验：2026-10-02，Asia/Shanghai。

**第二阶段数据基础和单条真实成功生成闭环均已验收。2026-10-02 按用户授权修复 Smoke 并仅调用一次真实 DeepSeek：Run 2 为 succeeded/stop，严格 Schema 和持久化来源校验通过，生成 Session 1、6 个测试点和 6 条待审核草稿；旧失败 Run 1 保留。最终 861 passed，行覆盖率 95.14%。本轮未进入正式实验。** 第 8～9 节保留首次失败调用与初次回归的历史证据；本次修复、最新结果和边界见第 11 节。

## 1. Git

```text
baseline commit: 53137455a7f1e19c9297d65d8d46ffc73753eeba
baseline message: chore: establish thesis development baseline
current branch: thesis/llm-experiment-foundation
current HEAD: 53137455a7f1e19c9297d65d8d46ffc73753eeba
```

第一阶段检查确认仅 `.env.example`、`README.md`、基线计划和报告这四个文件存在未提交变更，然后按指定消息提交。从该 commit 创建并切换新分支，确认工作区干净后开始第二阶段。没有覆盖其他用户变更，没有 push。第二阶段代码、迁移、测试和文档保留为本分支未提交变更，便于审阅。

使用仓库 `.venv\Scripts\python.exe`，Windows/Python 3.14.3、pytest 8.4.2。本轮未执行 Linux/Python 3.12 CI 或 Docker 构建。

### 中断恢复核对

恢复时实际执行 git status、diff --stat、diff、branch/HEAD 及 db current，检查已保存的模型、唯一新 migration、service/helper、route、template、七个新增测试文件和执行日志。已有代码全部保留，没有重复创建迁移或实体。已跟踪文件差异为 17 files changed、712 insertions、86 deletions；新增文件另见 Git untracked 清单，不能将该 stat 当作全部变更量。

中断前已完成实体/迁移、Provider 元数据/hash、生成与审核服务、认证/UI、真实一次 Smoke，以及最后的并发修复。完整回归进程在中断后继续完成并保存 854 passed 日志；代码、测试和 migration 的修改时间均早于该完整回归完成，恢复后没有改动这些源文件。未完成的是报告统计、并发修复说明和收尾状态。恢复后重新执行并发复现测试（1 passed）、Ruff、migration current/check、旧数据/外键/完整性检查及新增测试收集，并核对新的 coverage.xml；没有重复执行真实 API 调用。

## 2. 新数据结构

### GenerationRun

实际为 27 个字段：

| 字段 | 类型 / 可空性 | 用途 |
| --- | --- | --- |
| id | Integer PK | 独立调用编号 |
| session_id | Integer FK，可空 | Session 1:N Run；首次失败没有 Session |
| project_id / version_id | Integer FK，必填 | 失败调用也能定位需求上下文 |
| title / requirement_text | String(200) / Text，必填 | 安全校验后的实际输入快照；Session 继续保留需求原文 |
| provider | String(30)，必填 | mock / deepseek，有 CHECK 约束 |
| provider_model | String(120)，可空 | 优先实际响应 model，否则安全配置值；Mock 为 NULL |
| prompt_version | String(40)，必填 | 当前 test-design-v2；历史 test-design-v1 不改写 |
| prompt_hash / requirement_hash | String(64)，必填 | SHA-256 |
| status | String(30)，必填 | running / succeeded / failed，有 CHECK 约束 |
| started_at / created_at | UTC DateTime，必填 | 调用开始、记录创建时间 |
| finished_at | UTC DateTime，可空 | 终态时间；running 没有终态时间 |
| latency_ms | Integer，可空 | 单调时钟测量，不依赖系统时钟差 |
| input_chars / output_chars | Integer，可空 | 实际消息内容总字符数 / 响应内容字符数 |
| prompt_tokens / completion_tokens / total_tokens | Integer，可空 | Provider 实际返回值，不估算、不编造 |
| finish_reason | String(80)，可空 | Provider 实际返回值，经安全白名单检查 |
| temperature / max_tokens | Float / Integer，可空 | 实际设置；未发送 temperature，故为 NULL |
| error_type / error_message | String(80) / Text，可空 | 安全分类与固定安全文案，不保存异常原文 |
| structured_output_json | Text，可空 | 仅经过解析、严格 Schema 和安全校验的结果 |

关系：Project/Version → Run；Session → 多个 Run；Run → 多个来源 Draft。`TestCaseDraft.generation_run_id` 是新增的可空外键，历史草稿保留 NULL，不回填虚假生成记录。成功 Run 关联 Session；首次失败 Run 保存安全输入上下文，`session_id=NULL`。

外键使用 RESTRICT 保护 Run 来源。Run 从 running 到终态一次，终态禁止 ORM 更新和删除。使用 `status` 作为 SQLAlchemy 乐观锁版本条件，UPDATE 同时比较先前读取的状态；两个会话交错终态提交时，后写者收到 StaleDataError，不能覆盖先前终态。确定性并发复现测试已验证此行为，无须额外数据库字段或 migration。不可变保护针对 ORM；直接数据库操作或 SQLAlchemy bulk SQL 可绕过 mapper 事件，不应使用这些途径修改实验证据。

### ReviewRecord

实际为 12 个字段：

```text
id                        Integer PK
draft_id                  Integer FK, NOT NULL, RESTRICT
reviewer_user_id           Integer FK User, NOT NULL, RESTRICT
action                    String(30), edit / accept / reject, NOT NULL
before_snapshot_json      Text, NOT NULL
after_snapshot_json       Text, NOT NULL
score_before              Integer, 0..100, NOT NULL
score_after               Integer, 0..100, NOT NULL
changed_fields_json       Text, NOT NULL
changed_field_count        Integer, 0..9, NOT NULL
comment                   Text, NULL allowed
created_at                UTC DateTime, NOT NULL
```

Draft 1:N ReviewRecord，User 1:N ReviewRecord；action、分数范围、变化字段数有数据库 CHECK。记录创建后禁止 ORM 更新和删除。外键 RESTRICT 保留草稿与审核人；没有证据关联的历史 Session/Draft 继续遵循旧 cascade 行为。

## 3. 调用与事务

1. 检查需求安全、Demo 范围和 Project/Version 关系。
2. 独立 SQLAlchemy Session 提交 running Run。提交失败则不调用 Provider。
3. Provider 调用一次，SDK `max_retries=0`；无后台队列或隐藏重试。
4. 提取安全元数据；解析、严格 Schema、安全检查，再保存结构化结果。
5. 应用事务原子提交 Session、Draft 来源链接和 Run succeeded。
6. Provider/Schema/安全失败记录 failed；业务写入回滚后，独立事务保存 failed Run。经验证的安全快照在业务写入失败时仍可保留；未经验证的输出从不保存。

原有“生成失败不产生 Session/Draft”语义保持。初始失败由 Run 的需求快照追溯，避免为失败创建伪造的 generated Session。对于已有 Session，`generate_for_session(session_id)` 追加独立 Run/草稿，不删除原草稿、人工修改或审核记录；失败重试不改变当前 Session 结果。

单次 Provider Schema 仍限制最多 20 条草稿。持久化 Session 使用逐字段严格校验的集合 Schema，允许累计多个批次；重试后的 Session 分数按全部保留草稿重算，避免列表与详情不一致。每个 Run 保留自己的独立输出快照，实验分析应以 Run 区分批次。

若数据库完全不可写、进程崩溃或被终止，已提交的 running 证据可能无法自动转为终态。本阶段没有后台恢复；统计时应单独报告 unresolved running 调用。

## 4. Migration 与原数据

```text
old head: c5d8a9e4f2b1
new head: d7e2f6a9b301
db current: d7e2f6a9b301 (head)
db check: No new upgrade operations detected.
PRAGMA foreign_keys: 1
PRAGMA foreign_key_check: []
PRAGMA integrity_check: ok
```

新迁移：`migrations/versions/d7e2f6a9b301_add_llm_experiment_evidence.py`。只新增两张表、Draft 可空字段及关联索引/外键，没有修改历史 migration。

原库：`instance/audio_test_platform.sqlite`。升级前使用 SQLite backup API 备份到：

```text
instance/backups/audio_test_platform-pre-experiment-20261001-175515.sqlite
```

备份完整性为 ok，旧表内容摘要与源库一致。2026-10-01 升级及首次失败 Smoke 后核验旧字段、行数量和数据摘要，旧业务记录均未改变；`.env` 文件摘要未改变。当时旧表数量为 Project 2、Version 4、TestCase 4、TestExecution 15、Defect 4、TestRun 1、LogFile 1、User 1，Session/Draft 均 0，原库新增 **1 个真实失败 GenerationRun、0 个 ReviewRecord**。2026-10-02 成功补验后的最新数量见第 11 节；测试产生的 Fake/Mock 数据均在临时测试数据库，不作为真实实验结果。

## 5. 模型追踪与安全

| 证据 | 实现及验证 |
| --- | --- |
| provider / model | Mock 明确为 mock；DeepSeek 保存实际响应 model，缺失安全回退 |
| prompt version / hash | 当前 test-design-v2，历史记录保留 v1；对真正参与消息构建的静态 system 与 user 序列化模板稳定 JSON SHA-256 |
| requirement hash | 对验证后实际发送需求 UTF-8 SHA-256；Session 与 Run 输入快照保存原文 |
| latency / timestamps | UTC 时间 + perf_counter 耗时；包括 Provider 和校验/生成准备，终态写库前停止计时 |
| tokens / finish reason | SDK 有值则记录；无值、格式异常或敏感值则 NULL |
| success / failure | Mock、DeepSeek FakeClient、真实失败、后续 DB rollback 均有独立测试/证据 |
| structured output | 合格结果快照不可因人工编辑覆盖；未通过 Schema/安全检查时为 NULL |
| safe error | 固定文案与已知分类；不使用 SDK exception string，不保存 raw request/response |

DeepSeek 官方 [Chat Completions 响应说明](https://api-docs.deepseek.com/api/create-chat-completion) 提供 model、usage 和 finish_reason 字段；本实现仍以实际 SDK 对象为准，不假定每次都有 usage。真实 Smoke 的 usage 和 finish_reason 来自本轮响应。

安全检查覆盖 credential assignments、Authorization/Bearer/header 片段、API Key/Secret Key 配置值、日志与路径、Prompt 泄漏，以及审核意见。旧草稿如已含敏感内容，审核快照按字段保存 `[redacted sensitive content]` 并列出 `redacted_fields`；变化数量根据内存中的原字段计算。可拒绝旧敏感草稿，同时不会把凭据复制进新审计表。

真实 Run 的所有新入库字段另外与当前 API Key/Secret Key 值逐项比较，结果为 **credential_values_absent_from_evidence=true**。没有保存 API Key、Authorization、环境变量转储、完整 Prompt 或未经检查的原始响应。

## 6. 人工审核与指标

edit GET/POST、accept、reject 使用 Flask-Login 要求登录；HTTP 路由只关联 `current_user.id`，不接受客户端伪造 reviewer。服务也验证 User 存在；内部可信 CLI 可显式传 reviewer_user_id，匿名调用不会伪造身份。本阶段没有扩展完整 RBAC 或项目成员体系。

可选审核意见去除首尾空白后最多 1,000 字符，服务端验证长度和敏感内容，空意见存为 NULL。

每次成功审核和其数据修改原子提交；数据库失败不留半条审核记录。pending 约束保留，重复 accept、reject 后 accept/edit、重复 code 冲突均受保护。

before/after 包含九个内容字段、status、accepted_test_case_id。普通数据修改前后完整保留；敏感旧内容按上节显式脱敏。分数是**当前 Session 全部草稿的确定性规则分数**，不是主观人工质量评分，也不是每条用例独立评分。

可计算：

- 人工修改率：至少一次内容变化 edit 的草稿数 / 传入集合的全部草稿数。
- 平均修改字段数：所有发生内容变化 edit 的字段变化数之和 / 这些 edit 次数。
- 接受/拒绝率：最终 accepted/rejected 草稿数 / 传入集合的全部草稿数；pending 仍在分母。
- 审核次数：ReviewRecord 数量；无内容变化 edit 计审核，不计人工修改。

应按 GenerationRun/Provider 分组统计，区分历史无来源 Seed 草稿、Mock 与真实 LLM。没有虚构人工审核实测数据，没有实现字符相似度或编辑耗时算法。

页面当前传给指标函数的是全部 `session.drafts`，包括 `generation_run_id=NULL` 的历史草稿，并未自动过滤来源；实验分析可向同一函数传入特定 Run 的 drafts 集合，再计算对应批次指标。

## 7. UI

保持现有 AI Test Design 布局。Session 详情显示生成历史、Provider/Model、Prompt Version、状态、UTC 时间、latency、可空 usage/finish_reason；各草稿显示 Reviewer、Action、Review Time、变化字段、评分与意见。匿名用户看到登录提示。列表显示没有 Session 的 running/failed 调用安全摘要，历史无 Run 的会话显示真实空状态。

NULL 模型/元数据显示 `Not returned`，不估算 token。孤立调用卡片随 project/version/provider 筛选，Session 状态筛选保持原有意义。

没有向普通页面输出 API Key、完整 system Prompt 或内部堆栈。页面 HTTP/认证/转义/空元数据/失败调用展示已由路由测试验证。

使用现有 Playwright CLI 在临时 SQLite 副本渲染详情、列表和编辑页，桌面 1440×1000、手机视口 390×844，共六张截图经检查。每个页面 document scrollWidth 等于视口宽度，没有整页横向溢出；原列表表格仍在容器内横向滚动。这是浏览器视口模拟，不是实体手机测试；没有新增 Playwright/Selenium 依赖或浏览器测试框架，预览进程和浏览器会话已关闭。截图保留在 `.codex/task4-ui/`。

## 8. 首次真实 DeepSeek Smoke（2026-10-01，历史失败记录）

只在结构、相关测试、完整回归、原库迁移和凭据配置检查通过后执行：

```powershell
.\.venv\Scripts\python.exe scripts\llm_generation_smoke.py --project-id 1 --version-id 1 --execute
```

需求为完全虚构的 Demo 登录接口：用户名密码必填、密码长度 8～20 位、连续错误 5 次锁定 10 分钟、成功返回访问令牌。没有真实账号、公司需求、日志、隐私或商业数据。

```text
executed: true — exactly one Provider/API attempt; no retry
provider: deepseek
requested model: deepseek-v4-pro
response model: deepseek-v4-pro
API response received: yes
overall result: failed
schema validation: false
generation run persisted: true, id=1, status=failed
session generated: no
test points / Drafts persisted: no
structured_output_json: NULL
prompt_tokens: 318
completion_tokens: 2000
total_tokens: 2318
finish_reason: length
latency: 15088 ms
input_chars: 1208
output_chars: 8295
temperature: NULL — not supplied in request
max_tokens: 2000
request timeout: 20 seconds
error_type: AIResponseError
safe error: AI test design output failed validation.
```

实际 `prompt_hash`：`f560f057536cb0a2992897460dca02804d08cb1822fc916c8a2a5c399f5d5364`。

实际 `requirement_hash`：`6115979f68afd791cf2159408357340c6fe0f7fa9cf3202fb75b5d410dc343ac`。

模型输出达到当前 token 上限，返回 length 且未通过校验；这支持“输出截断导致本次失败”的判断。由于不保留原始 Provider 内容，本报告不展示或补写原始输出。没有扩大输出预算后重复调用，没有把失败伪装成成功或缺凭据 pending。

Smoke 脚本默认不执行，需要显式 `--execute`；无凭据会报告 `pending: missing valid API credential`。本轮凭据实际获得响应，未触发该 pending 路径。

## 9. 初次完整测试与新增数量（2026-10-01，历史验证）

真实命令：

```powershell
.\.venv\Scripts\python.exe -m ruff check . --no-cache
.\.venv\Scripts\python.exe -m flask --app run.py db current
.\.venv\Scripts\python.exe -m flask --app run.py db check
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90
```

```text
collected: 854
passed: 854
failed: 0
skipped: 0
xfailed / xpassed: 0 / 0
warnings: 361
duration: 120.71 s (0:02:00)
coverage: 95.14% line coverage
statements: 3703
covered: 3523
missed: 180
pytest exit code: 0
Ruff: All checks passed!, exit 0
```

Warnings 按 pytest 最终 summary 如实记录，包含原有 datetime.utc* 弃用和 SQLite 连接 ResourceWarning；没有过滤或隐藏。覆盖率是行覆盖率，不是 branch coverage。

新增 **232** 个 parametrized collected cases：

| 新测试文件 | collected | 核心覆盖 |
| --- | ---: | --- |
| test_experiment_models.py | 65 | 字段/可空、必须值、CHECK、外键、关系、cascade/restrict、不可变 |
| test_experiment_migration.py | 4 | fresh/旧数据升级、downgrade/reupgrade、check、外键与约束 |
| test_generation_provider_metadata.py | 76 | FakeClient usage 有/无、model/finish_reason、错误响应元数据、消息/hash、禁重试、Mock、异常元数据 |
| test_generation_runs.py | 16 | 成功/失败、secret、Schema、DB rollback、调用前证据门槛、多 Run、累计草稿、评分一致、DeepSeek→Run、异常 temperature、并发终态覆盖 |
| test_review_records.py | 52 | edit/accept/reject、真实身份、评论安全、before/after、分数、顺序、指标、回滚、旧敏感内容脱敏 |
| test_experiment_routes.py | 17 | 匿名与登录、伪造 reviewer、意见/历史/空 usage、孤立失败 Run、转义 |
| test_llm_generation_smoke.py | 2 | 无凭据 pending、未显式执行不调用 API |

原有 622 项 collected case 保留；对 baseline 测试源码做 AST 比较，全部 **413 个原 test_* 函数**仍存在，missing=[]。仅为新增 Draft 列更新精确字段集合断言，为审核新增登录要求补真实 User/登录 fixture；没有删除测试、skip、降低 threshold 或放宽关键业务断言。

## 10. 后续验收与保留边界

首次验收留下的“真实成功生成”缺项已在 2026-10-02 按用户明确授权补验。上次 2,000 token/length 的失败证据保留，本次仅调用一条相同虚拟需求，成功完成严格校验及生成落库闭环。没有修改 `.env`，没有开始 30～50 条实验或第三阶段功能；本次结果见第 11 节。

另外，进程崩溃/数据库不可写可能保留 unresolved running；ORM 不可变机制不覆盖直接 SQL 篡改；规则分数与字段变化指标不等于主观质量或时间成本。这些边界在实验统计时需要明确。

独立代码审查未发现尚未解决的 Important/Critical 问题。审查同时注明可信内部调用的边界：running Run 的直接 ORM 删除仍允许；Draft 来源外键确保存在，但不限制内部调用者把来源改为另一 Session 的 Run。当前服务和 HTTP 没有提供这些修改/删除入口，正式实验应通过受控服务操作。

审查生成的一份临时模拟数据库 `C:\Users\lipuy\AppData\Local\Temp\llm-readonly-review-9gmt3o3p\review.sqlite` 清理被自动审批拒绝，返回 `blocked by policy`；文件保留，只含模拟数据，不影响原库或真实调用证据。没有使用替代方式绕过拒绝。

**当前项目具备 LLM 毕业论文实验的数据记录与追溯基础，单条真实成功生成验收也已通过。** 自动化与 FakeClient 证明 Schema、调用记录、草稿、审核及回滚链路；两条真实调用分别证明失败和成功证据能落库。这是工程闭环验收，尚不构成生成质量、稳定性或模型效果的正式实验结论。本轮到此停止。

本轮原始验证证据保存在被 Git 忽略的 `instance/experiment-evidence/`，包括 before/after.json、upgrade/current/check.txt、ruff.txt、pytest.txt、new-test-collection.txt、final-audit.json、safety-audit.json 和 deepseek-smoke.json。数据库备份、`.env`、真实实验 SQLite 和本地证据不提交到仓库。

## 11. 单条真实 Smoke 修复与成功补验（2026-10-02）

### 修复范围与依据

用户授权：“修复真实 DeepSeek Smoke，使一次虚拟需求能够完成成功生成闭环，不进入正式实验。” 保留现有第二阶段修改，未新增 model/migration，未改写旧证据，未提交或推送。

旧响应的 completion_tokens=2000、max_tokens=2000、finish_reason=length 证明触达输出上限。具体 JSON 破损位置没有原始输出可供判断，不补写推测。DeepSeek 官方 [JSON Output](https://api-docs.deepseek.com/guides/json_mode/) 和 [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) 说明 JSON 模式需要目标结构说明、示例及合理输出预算，length 仍可能截断内容。

本次定点修改：

- `app/services/test_design/prompts.py`：Prompt 升级为 `test-design-v2`，提供完整合法 JSON 示例、category/scenario 枚举、code 格式，以及 steps 等字段的字符串类型；指导生成 3～6 个简短测试点/草稿和 1～2 条限制说明。现有严格 Pydantic Schema 与单次 20 项上限均未放宽。
- `test_design_service.py` 和 `test_design/evidence.py` 共用 Prompt version 常量，Run 与 Session 保持一致；seed/历史记录保留 v1。
- `deepseek_provider.py`：先保留返回 metadata，再拒绝 length 响应，即使其 JSON 恰好可解析也不当作成功。SDK `max_retries=0` 保持不变。
- `scripts/llm_generation_smoke.py`：只对本次复制的配置设置 8,000 输出 token 上限、60 秒超时；常规应用配置和 `.env` 不改。针对项目、版本、标题、Provider 和需求 hash 匹配唯一新增 Run，避免选中其他并发生成记录。过期缓存后重新读库，要求 succeeded/stop、严格快照、Session/Run/hash/version/内容一致，以及所有待审核 Draft 的来源和内容一致。

### 本次真实调用

需求与首次调用相同，仍为完全虚构的 Demo 登录接口；requirement hash 未变。本轮只有一次真实 Provider 请求，无 SDK 重试、无补调，无 Mock/Fake 替代。

| 项目 | 本次实测值 |
| --- | --- |
| 请求 / 返回模型 | deepseek-v4-pro / deepseek-v4-pro |
| result / status / finish_reason | succeeded / succeeded / stop |
| strict Schema / closed_loop_validated | true / true |
| Run / Session | 2 / 1 |
| 测试点 / 草稿 | 6 / 6 |
| 草稿 ID / 状态 / 来源 | 1～6，全部 pending，generation_run_id=2 |
| 耗时 | 9,110 ms |
| prompt / completion / total tokens | 933 / 1,253 / 2,186 |
| 实际输入 / 输出字符数 | 3,997 / 5,332 |
| 输出上限 / 超时 | 8,000 token / 60 秒，仅 Smoke 局部配置 |
| temperature | NULL（未显式传入，不编造值） |
| Prompt version | test-design-v2 |
| Prompt hash | 47204e231b71bac5f94010b88e406f35bdf66e2f21d7cd1e06d28b9e6dfb3cf1 |
| Requirement hash | 6115979f68afd791cf2159408357340c6fe0f7fa9cf3202fb75b5d410dc343ac |

6 条草稿分别覆盖成功登录、用户名/密码缺失、密码 7/8 位下界、20/21 位上界、5 次错误后的锁定、10 分钟锁定时长。场景标签包括 normal/negative/boundary/recovery。本地规则评分为 100，仅代表当前结构评分；没有人工审核或正式模型质量评估，不能把它当作论文实验质量结论。草稿均未被接受为正式 TestCase。

### 最新自动化与数据库核验

```text
collected/passed: 861 / 861
failed/skipped/xfail/xpass: 0 / 0 / 0 / 0
warnings: 360
duration: 128.50 s
line coverage: 95.14% (3527/3707, missed 180)
pytest exit: 0
Ruff: All checks passed!
migration current: d7e2f6a9b301 (head)
migration check: No new upgrade operations detected.
foreign_keys: 1
foreign_key_check: []
integrity_check: ok
old_rows_unchanged / env_unchanged / safety_check: true / true / true
```

本次新增 7 项测试：Provider 合法示例与 length 拒绝 2 项；Smoke 成功持久化、截断、其他并发调用、返回对象无落库、错误草稿来源 5 项。6 项在旧实现上明确 RED，再修复转 GREEN。第二阶段累计新增 239 项，原有 622 项保留，AST 核验原 413 个 test_* 函数无缺失。只更新受 Prompt version 影响的版本断言，并增强文档同时保留 v1 历史/v2 当前说明；没有删除或跳过测试。

首轮全量回归发现页面版本断言仍为 v1；第二轮读到文档更新的中间状态。两项均修正并定向验证，随后冻结代码和文档重新执行全量回归，得到上面的 861 passed。失败尝试原始日志也保留。Warnings 未过滤，仍含原有 datetime 弃用/SQLite ResourceWarning。

调用前新备份：`instance/backups/audio_test_platform-pre-smoke-repair-20261002-004929.sqlite`，SQLite backup API 完成，完整性和源库内容摘要一致。调用后对全部旧行和 `.env` 内容摘要核验，旧 Run 1 及所有旧业务记录均未改变。原库现有 GenerationRun 2（失败 1、成功 1）、Session 1、Draft 6、ReviewRecord 0；TestCase 仍为 4，其他旧表数量不变。安全扫描通过；原始响应、请求头和凭据未持久化或输出。

本次安全证据位于 `instance/experiment-evidence/smoke-repair-20261002/`：`deepseek-smoke.json`、`generated-drafts-summary.json`、`before.json`、`after.json`、`final-audit.json`、`pytest.txt`、两份失败尝试日志、`ruff.txt`、`current.txt`、`check.txt` 和 `new-test-collection.txt`。这些本地数据和备份均被 Git 忽略。

**本次单条真实成功生成闭环任务已完成。** 常规页面仍使用已有配置，本次只验证 Smoke 的局部配置与这一条虚拟需求；未开展正式实验、批量生成或第三阶段开发。
