# Step 3-D：Pilot-v2 技术试运行报告

日期：2026-10-02（Asia/Shanghai）。本轮为独立技术 Pilot，没有开始正式实验或人工评分。

**ready_for_formal_experiment=false**。

Baseline 的两个 attempt 均成功；Proposed 的端到端 attempt 为 **1/2 成功**。上传需求的 Proposed 已完成合法生成和业务持久化，但实验导出安全检查发生误判，外层 outcome 保留为 failed。该框架问题已在保留证据后离线修复、补充回归测试，没有重新调用模型或改写结果。

## 1. 快照与基本信息

执行前已检查 git status、diff --stat、当前分支及最近五次提交。原有 21 个变更文件均属于第三阶段实验框架、Pilot-v1、Step 3-C 诊断/v3 修复及相关测试文档，未发现未知用户修改。

- 初始安全快照：`2ea67a205eda477790bc7d9a3315c87f1ed77636`，`feat: stabilize llm experiment pilot pipeline`。
- 预检发现现有加载器仅接受 pilot-v1；增加了明确的 pilot-v2 版本及 manifest 标签支持，并保留 v1 兼容。另补齐 Docker 对共享版本模块 `test_design_contract.py` 的复制。两项均先离线复现、测试，再提交。
- 最终真实运行快照：`1e495543d9df9a75498ca2245917e88b3dee7769`，`fix: support isolated pilot-v2 and package prompt contract`。
- 分支：`thesis/llm-experiment-foundation`。真实调用前源码及正式数据集工作区干净。
- 未 push。真实运行后的导出修复和本报告保留为未提交修改，供人工审核。

```text
pilot_version=pilot-v2
pilot_v2_base_commit=1e495543d9df9a75498ca2245917e88b3dee7769
pilot_only=true
formal_experiment=false
prompt_version=test-design-v3
baseline_prompt_version=baseline-v1
requested_model=deepseek-v4-pro
provider=deepseek
endpoint=https://api.deepseek.com
max_tokens=8000
timeout=60 seconds
temperature=not sent
thinking=disabled
max_retries=0
attempts_per_requirement_per_method=1
```

运行目录：`experiment/pilot_runs/pilot-v2-20261002T071344Z/`。

预登记及审计目录：`experiment/pilot_runs/pilot-v2-preflight-20261002T071344Z/`。

manifest 创建时间为 `2026-10-02T07:25:53.267689+00:00`，对应北京时间 15:25:53。目录后缀为准备阶段时间，不作为请求开始时间。

## 2. 全新输入与 Dry Run

新输入位于预检目录的 `input/requirements.jsonl`，标记 `dataset_version=pilot-v2`：

| 标识 | 结构 | 内容范围 |
|---|---|---|
| PILOT_UPLOAD_001（A） | 文件上传 | 虚构 Demo 星屿练习素材；.txt/.png 白名单、1–4096 字节、空文件、超限、成功标识 |
| PILOT_ACCESS_001（B） | 权限与状态 | 虚构 Demo 云帆练习队列；普通用户/管理员、启用/禁用、整组发布、1–4 条边界 |

两条需求由 Codex 辅助新写，未抽取正式 28 条需求，未复用 Pilot-v1 两条需求，也未使用真实项目或公司数据。仅为满足既有加载器格式，另新写 12 个本地参考点；这些点不进入 Provider 参数、不用于本轮评分。未读取正式 reference_scenarios 内容来编写输入，只计算其文件哈希。来源说明保存在 `input/INPUT_PROVENANCE.json`。

CLI Dry Run 保存在 `dry-run.json`，与 `frozen-preflight.json` 的计划一致。独立 MockTransport 探针验证了控制器接线、四次顺序和参数检查，真实请求为 0；该探针在临时目录运行，没有写入真实运行目录。

```text
requirements=2
methods=baseline+proposed
planned_requests=4
max_real_provider_requests=4
order=A Baseline → A Proposed → B Proposed → B Baseline
```

两组使用相同模型、endpoint、需求 title/text、token 上限、超时、thinking、temperature 和重试设置。唯一方法差异保持既有实验设计：Baseline 简单文本生成；Proposed v3 测试点及 JSON、既有 Schema、安全检查、规则评分和持久化。Prompt、Schema、Baseline、评价规则及正式数据集均未在调用过程中修改。

请求前冻结了输入/源码哈希、Prompt 哈希、消息哈希、匿名编号映射和格式转换规则。控制器最多接受 4 次 SDK create，每个序号最多发出一次 POST；按消息哈希核实输入，无参考场景加入。SDK 调试日志被关闭，未落盘消息全文或响应头。

## 3. 请求统计与四次 attempt

```text
planned=4
actual_requests=4
sdk_create_calls=4
HTTP POST dispatches=4
HTTP responses=4
baseline_success=2
baseline_failed=0
proposed_success=1
proposed_failed=1
unexpected_retries=0
blocked_duplicate_posts=0
pre_call_failed=0
unresolved=0
```

四份传输响应记录均为 HTTP 200，四份 outcome 均有实际响应 usage 和 returned_model；returned_model 均为 `deepseek-v4-pro`，证据来源为 `provider_response_metadata`。POST 计数本身是发送前审计计数，此处另有四份响应记录支持四次请求已返回。

| 顺序 / Requirement | Method | 外层 Status | Finish reason | Latency ms | Tokens（输入/输出/合计） | Diagnostic |
|---|---|---|---|---:|---|---|
| 1 / A | Baseline | succeeded | stop | 6404 | 328 / 871 / 1199 | 无失败 |
| 2 / A | Proposed | failed | stop | 15504 | 1403 / 2220 / 3623 | ExportSafetyError；导出误判 confirmed |
| 3 / B | Proposed | succeeded | stop | 9475 | 1415 / 1238 / 2653 | 无失败 |
| 4 / B | Baseline | succeeded | stop | 8784 | 340 / 1310 / 1650 | 无失败 |

Proposed latency 来自 `test_design_service`，Baseline 为 `baseline_adapter_including_validation`；口径不同，不将差值解释为模型速度差异。

所有 attempt 恰好执行一次。没有自动重试、手工补跑、切模型、调参、挑选结果或修复后的第二次真实请求。

## 4. Proposed 逐条验证

以下 ID 仅属于本轮隔离的 `proposed.sqlite`，不能与原业务库或 Pilot-v1 的同号记录混用。

| 检查 | A / attempt 2 | B / attempt 3 |
|---|---|---|
| GenerationRun | Run 1，succeeded | Run 2，succeeded |
| finish_reason | stop | stop |
| structured_output_json | 存在，合法结构化快照 | 存在，合法结构化快照 |
| JSON / 既有 Schema | 持久化快照重新验证通过 | 持久化快照重新验证通过 |
| 业务值安全检查 | 通过 | 通过 |
| TestDesignSession | Session 1 | Session 2 |
| TestCaseDraft | ID 1–12，共 12 条 | ID 13–17，共 5 条 |
| Draft 来源 | generation_run_id=1、session_id=1 | generation_run_id=2、session_id=2 |
| Draft 状态 | 全部 pending，无 accepted_test_case_id | 全部 pending，无 accepted_test_case_id |
| Prompt version | test-design-v3 | test-design-v3 |
| 外层 outcome | failed / ExportSafetyError | succeeded |
| 匿名预览 | 保持空批次；不补回被拒绝导出的内容 | 展示原始 5 条草稿的九字段 |

两条 Run/Session 的 title、requirement_text、项目/版本关联与预登记输入一致；Draft 内容与初始结构快照一致。Provider 返回元数据、成功 Run 和合法持久化结构共同支持 JSON 解析、Schema、安全检查及持久化路径已完成。未保存原始 Provider 响应来进行事后重解析。

- v3 Prompt SHA-256：`1ce470e27c23fea69d0554dedb3d4a88f16053af3fb44f166181b9f01bd3cf9f`。
- A requirement SHA-256：`310aa5a552d545bf01eabcf13f2c739ef9074d4df3d161fdb3113f26f48ad23a`。
- B requirement SHA-256：`c9434592a8ee35ac4e1a36df0ed23e75363c21f75a716f13b9db360806e1aa5a`。

隔离库共有 2 Run、2 Session、17 Draft，正式 TestCase=0、ReviewRecord=0；foreign_key_check 无异常，integrity_check=ok。A 的 12 条草稿在既有 Schema 上限内，但超过 Prompt 的 3–6 条生成指导；本轮保留数量事实，没有删减、重生成或据此调整 Schema。

### A 的状态差异与诊断

**confirmed：失败位于实验外层导出安全检查，不是本次 Provider JSON/Schema 验证失败。**

原 `_is_safe` 同时检查值树和整个 `json.dumps` 字符串。整条记录被拼成一行后，Run 时间戳与另一字段中的普通日志级别词发生跨字段匹配，触发 `LOG_LINE_PATTERN`。原值树安全检查通过，序列化整体检查失败；敏感内容模式命中为 0。定位字段为 `structured_output.case_drafts.0.expected_result`。离线合成 fixture 复现了相同误判，无须保留或复制模型原文。

这次外层 failed 与 durable Run succeeded 不符合“失败 attempt 必有 failed Run 且无 Session/Draft”的简单对应关系。Session/Draft 是已经成功校验后保存的记录，不能删除或伪造为不存在。原 outcome 的 `initial_cases=[]`、`structured_output=null` 与库内合法快照同时保留，不将其改写成 2/2 成功。

本轮两条 Proposed 没有 Provider 验证失败摘要文件；成功 Provider 的摘要为空。导出阶段不在既有 opt-in diagnostics 覆盖范围内，因此没有请求时的导出诊断摘要，这是本轮暴露的诊断边界。后续离线确认依据保存在预检目录 `export-failure-confirmed.json`，仅记录固定分类、阶段、字段路径和布尔事实；它不是回填的请求时摘要。`export-failure-analysis.json` 为初步分析，最终确认以 confirmed 文件为准。

没有保存 raw invalid response、完整 Prompt、Authorization、API Key、headers、环境内容、SDK 异常字符串或推理链。库内保留的是通过既有 Schema 和业务安全检查的结构快照。

## 5. Baseline 初始输出与九字段转换

Baseline 继续使用 `baseline-v1`，模板 hash 为 `ec5f5690c0e6ada964cafe3a8903ab070269733c3b87363eeef2a7e450859dd3`。两个 outcome 均保留需求 ID、请求/返回模型及证据来源、Prompt/requirement hash、usage、latency、finish_reason、status 和安全初始正文。

| Baseline | 初始用例数 | 缺字段 | 歧义字段 | 未映射值保留次数 | 转换 |
|---|---:|---:|---:|---:|---|
| A / attempt 1 | 6 | 0 | 0 | 18 | 按显式标签和冻结映射转换，前言单独保留 |
| B / attempt 4 | 8 | 0 | 0 | 17 | 按显式标签和冻结映射转换，标题单独保留 |

初始正文另存为 `normalization/001_initial_text.txt` 与 `004_initial_text.txt`，其 UTF-8 内容与 outcome 初始文本一致。每个字段保留来源行、原始文本和转换操作，汇总见 `normalization/conversion-log.json`。没有人工补写缺失业务内容，没有把未映射的高/中等值猜测成 P0–P3。B 返回 8 条，超过 Prompt 的数量指导，仍按原 Baseline 非空、安全、完整正文采集口径保留。

## 6. 匿名预览

新材料位于运行目录的 `blind_preview/BLIND_PREVIEW.md` 和四份 batch JSON。匿名编号映射在请求前随机生成，映射文件只保留于私有预检目录。

- 四批显示 8、5、0、6 条，共 19 条；失败批次保持空，不从数据库补回被拒绝导出的内容。
- 两组采用完全相同的九字段。显示内容无 method、Prompt version、GenerationRun、system quality score、tokens、latency、provider 或内部来源路径。
- 可展示用例缺字段 0、歧义字段 0。总未映射字面值次数为 50，其中 Baseline 35、Proposed 15；这是转换记录，包含原样保留的合法枚举，不等于 50 个模型错误。
- 不需要人工补录这 19 条的九字段内容；两段前言/标题保留在私有转换证据中，没有作为用例字段猜测填入。
- **九字段版式可用，严格匿名性尚不足。** 高/中与 P1/P2、用例类型术语、数量和空批次仍可能透露来源。未通过语义重写隐藏这些差异。

本轮只检查展示与转录条件，没有正式评分。内部 evaluation CSV 仍含 method，不能作为匿名材料直接发给评价者；评分和覆盖判断保持为空。

## 7. 数据与历史保护

运行前后正式文件 SHA-256 均与 DATASET_README v1.0 一致：

| 文件 | SHA-256 |
|---|---|
| requirements.jsonl | 7eaf3c824d35318f910c2134adbd0f5e2314ff6d56a7a04a00c96f4aea67c6d7 |
| reference_scenarios.jsonl | 4b7663d5a73df3676c0ff97043911a8cfb0118399dfe2c3ee965d31c2dc8b178 |

```text
formal_dataset_modified=false
formal_dataset_unchanged=true
formal_experiment_started=false
formal_experiment_not_started=true
reference_scenarios_leaked_to_provider=false
credentials_absent=true
```

原 Pilot-v1 的报告、失败分析和运行目录均保留。新保护清单含这些文件、原 instance、正式数据及本地配置，共 182 个文件。真实调用结束、离线修复前另冻结本轮 25 个主证据文件；后续转换只创建新文件，没有修改主证据。保护依据见 `protection-before.json`、`pilot-v2-primary-before-offline-fix.json` 和 `verification.json`。

Pilot-v1 永久保持 `pilot_version=pilot-v1`、Baseline 2/2、Proposed 0/2、`formal_experiment=false`。

## 8. 离线修复与验证范围

发现导出问题后，先保存主证据哈希，再仅修改 `experiment/framework.py` 的导出安全检查及相应测试。JSON 可序列化/有限数值检查保留；安全检查分别处理原始值、独立键和非字符串标量，保留嵌套凭据键、Authorization/request_headers 标记、数字形式凭据以及单个字段内真实日志的拒绝能力，避免跨字段拼接误判。

合成回归先出现预期失败（1 failed、10 passed），随后修复。独立审查又发现非字符串标量可能绕过凭据匹配，新增 10 项合成测试先全部失败，补齐后聚焦安全测试 24 项通过。没有使用真实调用重放来验证修复，没有调整 Prompt、Schema、模型或参数；旧 Pilot-v2 outcome、数据库和统计保持不变。

| 验证阶段 | 本轮实际结果 |
|---|---|
| 初始快照前聚焦回归 | 116 passed |
| 最终运行快照前 AI Design/实验/Run 等相关回归 | 485 passed；网络 guard 拦截尝试 0 |
| Docker 复制依赖模拟与交付测试 | 19 passed；没有执行 Docker build |
| 控制器离线 MockTransport 探针 | 4 次 fixture 请求；真实 Provider 请求 0 |
| 真实调用后导出修复最终相关回归 | 151 passed，0 failed，6.72 秒 |
| 真实调用后 Ruff / git diff --check | 通过 |
| 隔离数据库只读完整性 | integrity_check=ok；foreign_key_check 无异常 |

各行是不同阶段/范围，不能相加视为互不重复的测试数。本轮未重跑完整覆盖率套件；用户提供的 977 passed、95.14% 属于 Step 3-C 历史验证，未冒充本轮新结果。模型、Schema、migration 和正式数据未修改。

修复后源码与运行 manifest 的源码摘要存在预期差异，仅限 `experiment/framework.py`；真实生成仍归属已冻结的 `1e495543d9df9a75498ca2245917e88b3dee7769`，不把未提交修复描述成生成时的代码。最终测试及再次核验记录见预检目录 `root-offline-fix-final-tests.json`、`verification-final.json`；较早的阶段性测试与核验文件也保留。

## 9. 与 Pilot-v1 的事实对比

```text
Pilot-v1 Proposed end-to-end: 0/2
Pilot-v2 Proposed end-to-end: 1/2
Pilot-v2 durable generation/schema/persistence: 2/2
```

两轮使用不同虚构需求及不同 Prompt 版本，样本量各两条。这些计数仅描述技术执行结果，不支持模型质量显著提高、覆盖更好或人工成本更低的结论。

## 10. 最终结论

```text
ready_for_formal_experiment=false
```

原因：本轮 Proposed 的原始端到端记录未达到 2/2；导出误判虽已离线修复，但未用新真实请求验证，且不能追改本轮结果。匿名版式能够检查，来源线索和失败空批次仍限制有效盲评准备。四次调用上限、统一参数、业务数据关联和历史/正式数据保护已核实，但尚不足以满足全部正式实验技术门槛。

Pilot-v2 到此结束，等待人工审核。没有执行正式 56 次实验、正式人工评分、后续 Prompt 调优、Pilot-v3、论文实验结论或远程 push。
