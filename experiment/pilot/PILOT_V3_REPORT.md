# Step 3-E：Pilot-v3 最终技术 Gate 报告

日期：2026-10-03（Asia/Shanghai）。本轮通过最终技术验收；正式实验与人工评分尚未开始。以下计数仅描述技术链路，不作为论文正式效果统计。

## 1. 运行基线与冻结范围

```text
pilot_version=pilot-v3
pilot_only=true
formal_experiment=false
purpose=final_technical_readiness_gate
pilot_v3_base_commit=d024e799ba6dac50524da83a0a0cca31f35ebec7
base_commit=d024e799ba6dac50524da83a0a0cca31f35ebec7
prompt_version=test-design-v3
baseline_prompt_version=baseline-v1
provider=deepseek
requested_model=deepseek-v4-pro
endpoint=https://api.deepseek.com
timeout=60 seconds
max_tokens=8000
retry=0
temperature=not sent
thinking=disabled
stream=false
attempts_per_requirement_per_method=1
```

本地提交：`d024e79 fix: stabilize experiment export validation`。分支为 `thesis/llm-experiment-foundation`，没有 push。真实调用前源码工作区干净。

初始 `git status` 只有 `experiment/framework.py`、`tests/test_experiment_framework.py` 与未提交的 `PILOT_V2_REPORT.md`，均属于 v2 导出修复、回归或报告，未发现未知用户修改。Step 3-C 的 v3 Prompt 已在此前基线中。本次提交保存这些离线工作，另补充 v3 版本/manifest 支持、错误来源反例测试和本阶段执行计划。

加载器原先只接受 v1/v2，因此在真实请求前最小增加 `pilot-v3`，并固定 manifest 的 `purpose`、`base_commit`；没有放开未知版本或正式执行。旧测试保留原有 v2 覆盖并扩展 v3。Proposed Prompt 内容、Schema、质量评分、安全规则、Baseline Prompt、正式评价标准及正式数据均未修改。

| 冻结模板 | SHA-256 |
|---|---|
| Proposed v3 | `1ce470e27c23fea69d0554dedb3d4a88f16053af3fb44f166181b9f01bd3cf9f` |
| Baseline v1 | `ec5f5690c0e6ada964cafe3a8903ab070269733c3b87363eeef2a7e450859dd3` |

运行目录：`experiment/pilot_runs/pilot-v3-20261002T170135Z/`。

预检目录：`experiment/pilot_runs/pilot-v3-preflight-20261002T170135Z/`。目录后缀是准备阶段的 UTC 时间；本次独占执行启动记录时间为 **2026-10-03 13:59:48 +08:00**，不以目录后缀代替实际执行时间。

## 2. 完整回归与前置验收

完整 pytest 使用下列全部参数，由禁外网、允许本地 fixture HTTP 的包装器调用 `pytest.main` 执行：

```text
--cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90
```

实际入口为 `.venv/Scripts/python.exe -B experiment/pilot_runs/pilot-v3-preflight-20261002T170135Z/offline_regression.py full`。未降低 90% 阈值，未删除旧测试。

| 检查 | 本次新鲜结果 |
|---|---|
| 完整回归 | **1018 passed、0 failed、0 skipped**；359 warnings；138.52 秒 |
| app 覆盖率 | **95.14%**；生成 `coverage.xml` |
| 全套 `ruff check . --no-cache` | 通过 |
| `flask --app run.py db current` | `d7e2f6a9b301 (head)` |
| `flask --app run.py db check` | `No new upgrade operations detected.` |
| 原业务库连接 | `foreign_keys=1`、`foreign_key_check=[]`、`integrity_check=ok` |
| 完整回归外网尝试 | 0；真实 Provider 请求 0 |

首次验证包装器误禁用了本地 HTTP，导致 4 个 delivery smoke 测试失败（1014 passed，覆盖率仍为 95.14%）。失败证据保留为 `pytest-full-preflight.txt`、`full-regression.json`。依据堆栈确认是验证环境问题后，只在测试进程允许 loopback、禁用代理并继续阻断外网；本地 smoke 6 项通过，随后重新执行上述完整回归并通过。没有借此修改业务代码或跳过测试。最终结果见 `pytest-full-verified.txt`、`full-regression-final.json`。

独立运行工具在真实请求前还经过审查与模拟：修正模拟目录/文件接线，核对 manifest 的完整 tasks/requirements，按展示白名单与准确渲染验证匿名材料，并显式关闭只读 SQLite 句柄。早期预检冻结与模拟清理失败记录均保留；这些调整发生在真实调用之前。最终 MockTransport 探针完成 4 次离线 fixture 请求，真实请求 0，持久化、导出、转录、匿名预览和最终校验均通过；给导出内容故意设置错误 Run ID 的反例仍被拒绝。

## 3. 全新输入与 Dry Run

| Requirement | 类别 | 虚构 Demo 规则范围 |
|---|---|---|
| PILOT_QUERY_001（A） | 查询 / 分页 | 微光卡片目录；关键词连续子串/忽略英文大小写、0–12 字符、页码 1–999、每页 1–20、空结果、超过末页、非法参数和上下界 |
| PILOT_FLOW_001（B） | 状态流转 | 栖光练习包；草稿/待执行/已完成/已取消、合法动作、终态禁止操作、仅草稿可改数量、修改 0–6、提交 1–6 |

两条新需求正文分别为 512、501 字符；与正式 28 条及 v1/v2 共 32 条既有输入比较，ID 与正文均不重复。未使用真实公司、实习或业务数据。加载器要求的 12 个本地参考点也独立新写，仅作本地格式材料；为编写这些新输入，没有读取或复制正式 reference 内容，也没有将任何参考点用于评分或发送给模型。

CLI dry run 确认：

```text
requirements=2
methods=2
attempts_per_pair=1
planned_real_requests=4
order=A Baseline → A Proposed → B Proposed → B Baseline
output_directory_created=false
real_provider_requests=0
```

dry run 不加载 `.env`、不创建 Provider/实验 SQLite；执行配置在之后单独冻结。输入、消息、方法模板、源码、控制器、转换规则和随机匿名映射均在请求前冻结。双方接收相同 title/requirement_text，模型、endpoint、预算、超时、thinking、temperature 与 retry 控制相同。消息哈希在 SDK 与 HTTP 请求层核对，参考点不进入消息。

## 4. 请求统计与 Attempt 表

```text
planned=4
actual=4
sdk_create_calls=4
HTTP_POST_dispatches=4
HTTP_200_responses=4
baseline_success=2/2
proposed_generation_success=2/2
proposed_end_to_end_success=2/2
export_validation=2/2
source_association=2/2
retry_count=0
blocked_duplicate_posts=0
pre_call_failed=0
unresolved=0
```

| Requirement | Method | API | Generation | Export | E2E | Finish reason | Tokens（输入/输出/合计） | Latency ms |
|---|---|---|---|---|---|---|---:|---:|
| A / PILOT_QUERY_001 | Baseline | 200 | 成功 | 成功 | 成功 | stop | 422 / 883 / 1305 | 6241 |
| A / PILOT_QUERY_001 | Proposed | 200 | 成功 | 成功 | 成功 | stop | 1497 / 1583 / 3080 | 9742 |
| B / PILOT_FLOW_001 | Proposed | 200 | 成功 | 成功 | 成功 | stop | 1487 / 1728 / 3215 | 10772 |
| B / PILOT_FLOW_001 | Baseline | 200 | 成功 | 成功 | 成功 | stop | 412 / 946 / 1358 | 6545 |

四次返回模型均为 `deepseek-v4-pro`，依据实际 Provider 响应元数据；总 tokens 为 8958。Baseline latency 来自 `baseline_adapter_including_validation`，Proposed 来自 `test_design_service`，口径不同，不据此声称模型速度优劣。

每个 pair 只调用一次。没有 retry、补跑、结果挑选、模型切换、预算调整或调用中的代码修补。控制器的独占启动标记、新目录和每序列一次 POST 检查共同防止重放。

## 5. Proposed 端到端验证

以下 ID 仅属于 Pilot-v3 独立的 `proposed.sqlite`。

| 项目 | A / attempt 2 | B / attempt 3 |
|---|---|---|
| GenerationRun | Run 1，succeeded | Run 2，succeeded |
| structured output | 原 Schema 重新验证通过 | 原 Schema 重新验证通过 |
| Session | Session 1，generated | Session 2，generated |
| Draft | ID 1–9，共 9 条 | ID 10–17，共 8 条 |
| Draft 初始状态 | 全部 pending、未接受 | 全部 pending、未接受 |
| 来源关联 | Run/Session/项目/版本/需求一致 | Run/Session/项目/版本/需求一致 |
| 初始快照与导出 | 九字段、Draft ID、Run ID、Session ID 逐项一致 | 九字段、Draft ID、Run ID、Session ID 逐项一致 |
| manifest | 与请求前冻结的 tasks/requirements、源码基线一致 | 同左 |
| 匿名预览 | 9 条逐字投影成功 | 8 条逐字投影成功 |
| generation_success | true | true |
| end_to_end_success | true | true |

校验器通过只读连接重新读取唯一 Run，核对状态、需求/Prompt hash、Schema、Provider、Session 内容、Draft 来源与初始状态、导出内容、manifest 及展示结果，而非只信任 outcome 的 succeeded。隔离库为 2 Run、2 Session、17 Draft、0 正式 TestCase、0 ReviewRecord；外键检查为空，完整性为 ok。

两次 Proposed 分别生成 9、8 条草稿，超过 Prompt 的 3–6 条数量指导，但在既有 Schema 上限内。保留该事实，没有删减、重生成、调整 Schema 或将技术成功解释为质量优越。

## 6. Pilot-v2 Bug 回归验证

1. **原误判原因：** `_is_safe` 把整条 `json.dumps` 后的记录作为单行再次扫描。Run 的 ISO 时间戳与另一字段的正常 `INFO` 标签跨字段命中 `LOG_LINE_PATTERN`，因此业务生成/持久化成功，外层导出却失败。
2. **新逻辑：** 保留 JSON 可序列化与有限数值检查，分别检查值树、独立键、非字符串标量，不再把无关字段拼接成日志。没有删除来源一致性检查。
3. **工具 bug 的依据：** 对 v2 原库合法快照作只读、内存内重建，原值树安全、旧整行扫描拒绝、现检查通过。v2 原 outcome 仍为 failed；没有把历史结果回写为 2/2，也没有补跑 Provider。
4. **旧误判回归：** `test_export_safety_keeps_timestamps_separate_from_demo_level_labels` 覆盖时间戳与合法 INFO 分处字段的情形；凭据键/值、Authorization、headers、单字段真实日志、NaN/Infinity、不可序列化对象与非字符串凭据仍有拒绝测试。
5. **真实来源错误反例：** `test_proposed_rejects_draft_bound_to_another_attempt` 的两项参数化测试将新 Draft 改绑到另一真实存在的 Run 或 Session。SQL 确认错配实际持久化且外键合法；Run 仍 succeeded，但导出必须返回 `EvidenceValidationError`，不返回草稿。另有最终校验器的错误导出 Run ID 离线反例。
6. **v3 实际结果：** 两次正常 Run → Session → Draft → Export 均通过，未出现 ExportSafetyError。此结论与合成/历史反例证据共同支持修复 false positive，不能理解为关闭了数据一致性检查。

## 7. Baseline 与 Blind Preview

两次 Baseline 均保存通过既有安全检查的真实初始正文，UTF-8 正文副本与 outcome 内容一致。按请求前冻结的显式字段标签转录为九字段；无大小写统一、枚举值替换、步骤编号删除、语义重写或缺字段补写。

| Baseline | 初始用例数 | 缺字段 | 歧义字段 | 未解析内容 |
|---|---:|---:|---:|---|
| A / attempt 1 | 9 | 0 | 0 | 仅首行“测试用例列表”标题，原样私存 |
| B / attempt 4 | 6 | 0 | 0 | 仅首行生成说明，原样私存 |

`normalization/conversion-log.json` 与逐 attempt 转录记录保留原文字段、来源行、转换操作及未解析范围。Proposed 使用 initial cases 的九字段原值投影。全部 32 条用例无人工业务内容增加；96 个枚举字面值保留记录只是原样转录计数，不是 96 个模型错误。

匿名预览位于运行目录的 `blind_preview/BLIND_PREVIEW.md` 和四份 batch JSON。随机编号映射在请求前冻结，保留于私有 preflight。展示只包含统一说明、匿名批次、需求与九字段用例；不展示 method、Prompt version、Run ID、quality score、Provider、token、latency 或内部来源路径。JSON 白名单与 Markdown 准确渲染核对均通过。

已具备用于后续盲评的统一展示及方法元数据隐藏条件。文本风格、优先级字面值、术语和用例数量仍可能透露方法，属于方法限制，没有人为改写消除差异。内部报告、匿名映射、normalization 和含 method 的 evaluation 模板不属于对评价者发放的匿名材料。人工评分字段仍全部为空。

## 8. 数据与历史保护

| 文件 | Before SHA-256 | After SHA-256 |
|---|---|---|
| requirements.jsonl | `7eaf3c824d35318f910c2134adbd0f5e2314ff6d56a7a04a00c96f4aea67c6d7` | `7eaf3c824d35318f910c2134adbd0f5e2314ff6d56a7a04a00c96f4aea67c6d7` |
| reference_scenarios.jsonl | `4b7663d5a73df3676c0ff97043911a8cfb0118399dfe2c3ee965d31c2dc8b178` | `4b7663d5a73df3676c0ff97043911a8cfb0118399dfe2c3ee965d31c2dc8b178` |

前后摘要均与 DATASET_README v1.0 一致。保护清单中的 382 个历史 Pilot、正式数据、原 instance、本地配置及冻结业务方法文件全部匹配；70 个执行源码文件和 17 个冻结预检材料匹配。真实运行的 25 个原始证据文件先于派生展示建立摘要，转录后保持不变。

```text
formal_dataset_modified=false
formal_dataset_unchanged=true
reference_scenarios_used_as_model_input=false
formal_experiment_started=false
human_scoring_started=false
credentials_absent=true
```

实际凭据只在本机内存中参与配置和安全扫描；运行/预检导出无实际凭据值或完整 Prompt，请求证据未保存 Authorization、原始 Provider 响应、headers、SDK 原始异常或推理内容。离线 pytest 的失败堆栈作为测试诊断保留。Baseline 安全初始正文与 Proposed 通过 Schema 的结构快照按既有方法保留。API Key、`.env`、SQLite、私有运行证据及 Git 忽略输出均未提交。

## 9. 运行后验证与三轮历史

真实运行期间与之后没有修改业务源码或冻结的执行/校验/转录脚本。

运行后 `ruff check . --no-cache` 通过；实验框架、适配器、生成 smoke、Prompt v3 合约和 validation diagnostics 五个测试文件 **163 passed、0 failed、0 skipped**，8.16 秒，外网连接尝试 0。完整回归与这些定向计数不能相加。验收过程中未进行正式人工评分。

| Pilot | Baseline 可用 | Proposed generation | Proposed 执行时 E2E | 事实 |
|---|---|---|---|---|
| v1 | 2/2 | 0/2 | 0/2 | 两次输出验证失败，无 Session/Draft |
| v2 | 2/2 | 2/2 | **1/2** | 一次 export false positive；之后离线修复，历史结果不改写 |
| v3 | 2/2 | 2/2 | **2/2** | 新请求的持久化、导出、关联、校验和匿名展示均通过 |

三轮均为小规模技术 Pilot，输入与部分历史 Prompt 版本不同，不并入正式统计，不得用于“模型优于人工”等论文效果结论。

## 10. 最终 Gate

```text
ready_for_formal_experiment=true
```

理由：计划及实际请求均为 4，重试为 0；Baseline 2/2 可用，Proposed 生成与端到端均 2/2；导出校验、来源关联、匿名预览、统一参数、凭据保护、正式数据及历史证据保护均通过，运行后回归通过。v2 的跨字段误判修复没有放过真实来源错误。

本阶段在 Pilot-v3 技术验收完成处停止。没有执行正式 56 次调用、正式评分、Prompt v4、Pilot-v4、远程 push 或论文效果结论，等待人工授权正式实验。

主要本地证据：预检目录的 `frozen-preflight.json`、`full-regression-final.json`、`offline-controller-probe.json`、`request-accounting.json`、`v2-regression-readonly.json`、`verification.json`、`related-regression-final.json`；运行目录的 `manifest.json`、四份 `outcome.json`、`proposed.sqlite`、转换记录和匿名预览。早期预检失败及冻结修订均保留，不与真实请求次数混算。
