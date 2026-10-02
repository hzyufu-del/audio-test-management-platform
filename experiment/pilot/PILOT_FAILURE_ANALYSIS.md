# Step 3-C：Proposed Pilot-v1 失败分析与离线修复

日期：2026-10-02。范围：历史证据只读分析、通用诊断修复、Prompt 约束澄清和离线验证。

本阶段真实 Provider 请求为 **0**。未重跑 Pilot、未执行正式 28 条实验、未进行人工评分。

## 1. Pilot-v1 事实与证据保护

Pilot-v1 计划 4 次，实际 4 次请求；Baseline 2/2 成功，Proposed 0/2 成功。没有自动重试或人工补跑。两条 Proposed 失败 Run 均保留，未产生 Session / Draft。这些状态不表示用例语义质量或方法优劣。

- 原报告：`experiment/pilot/PILOT_REPORT.md`。
- 原运行：`experiment/pilot_runs/pilot-step3b-20261002T051712Z/`。
- 原代码快照：`fc58042f3457efe97e1b5ae2521b743995d6a2bc`。
- 本阶段独立审计：`experiment/pilot_runs/step3c-audit-20261002T053436Z/`，被 Git 忽略。

`PILOT_V1_ARCHIVE.json` 是外部永久登记，标记 `pilot_version=pilot-v1`、`status=completed_with_proposed_validation_failure`、`formal_experiment=false`。采用外部登记保持旧 manifest、4 组 started/outcome、Baseline 初始输出及规范化结果、blind preview、评价空模板、隔离数据库和 summary 的字节不变；没有向历史 Run 回填摘要或新版本。

登记包含原报告及运行的 **24 个文件 SHA-256**，4 次尝试的 Run ID、Prompt / requirement hash，manifest hash、数据集 hash 和快照。原 `instance` 的 **154 个文件**也建立了保护清单。最终复核结果见第 7 节。

## 2. 成功 Smoke 与两次 Proposed 失败对比

Smoke 来自原 `instance/audio_test_platform.sqlite` 的 Run 2；Pilot A/B 来自旧运行的 `proposed.sqlite` 的 Run 1/2。**数据库不同，Run ID 不能跨库视为同一记录。**

| 元数据 | 第二阶段 Smoke | Pilot A | Pilot B |
|---|---|---|---|
| requirement_id | NULL，非数据集需求 | PILOT_AUTH_001 | PILOT_SEARCH_001 |
| requirement length（字符） | 104 | 413 | 526 |
| category | Demo 登录，非数据集分类 | 用户认证 | 查询搜索 |
| GenerationRun ID | 2（原业务库） | 1（Pilot 库） | 2（Pilot 库） |
| provider | deepseek | deepseek | deepseek |
| requested model | deepseek-v4-pro | deepseek-v4-pro | deepseek-v4-pro |
| provider_model | deepseek-v4-pro | deepseek-v4-pro | deepseek-v4-pro |
| 单独保存的 returned_model | 未独立留存 | deepseek-v4-pro | deepseek-v4-pro |
| returned_model 证据来源 | 不可据此证明服务端返回值 | provider_response_metadata | provider_response_metadata |
| prompt_version | test-design-v2 | test-design-v2 | test-design-v2 |
| prompt_hash | V2（见下文） | V2（见下文） | V2（见下文） |
| requirement_hash | S（见下文） | A（见下文） | B（见下文） |
| prompt_tokens | 933 | 1139 | 1162 |
| completion_tokens | 1253 | 1673 | 1315 |
| total_tokens | 2186 | 2812 | 2477 |
| finish_reason | stop | stop | stop |
| max_tokens | 8000 | 8000 | 8000 |
| timeout（秒） | 60 | 60 | 60 |
| latency（毫秒） | 9110 | 10915 | 8779 |
| input_chars | 3997 | 4303 | 4417 |
| output_chars | 5332 | 4267 | 3555 |
| status | succeeded | failed | failed |
| error_type | NULL | AIResponseError | AIResponseError |
| safe error message | NULL | 统一安全文案，见下文 | 统一安全文案，见下文 |
| structured_output_json 为 NULL | false | true | true |
| Session ID | 1 | NULL | NULL |
| Draft 数量 | 6 | 0 | 0 |

V2 Prompt SHA-256：`47204e231b71bac5f94010b88e406f35bdf66e2f21d7cd1e06d28b9e6dfb3cf1`。

Requirement SHA-256：

- S：`6115979f68afd791cf2159408357340c6fe0f7fa9cf3202fb75b5d410dc343ac`。
- A：`da159c2dde16b9f5544f32932dfb82724e2dd640ed53166f1f7a3bdafc1c3735`。
- B：`5e311733a368609ec8ea85e4b620b76c24a4749643c8084d890ae181fb7be113`。

两次失败仅保存固定安全文案：`AI test design output failed validation.`。该文案由 `safe_error` 折叠，不能证明特定 Schema 字段错误。比较摘要在 `failure-comparison.json`，来自只读数据库与已有 outcome / Smoke 证据，没有保存原始失败响应。

## 3. 根因：confirmed 与未证实的候选

**confirmed：两次请求均取得模型响应元数据，随后在输出验证／安全检查路径失败；失败发生在生成合法结构快照和成功业务持久化之前。** finish_reason 都是 stop，不能按 length 截断失败处理。Token、返回模型和输出字符数支持请求已完成，需求长度增加与失败同时出现，但不能推出因果关系。

**confirmed 的诊断缺陷：历史统一错误分类丢失了 JSON 解析、Schema 子类型及安全拒绝之间的区别。** 未通过验证的响应没有保存，这是现有安全边界；现有记录也没有字段路径、错误代码或数量。因此无法从旧证据准确恢复两次失败的具体字段与值，不能事后补写一个推测的原因。

| 用户要求的失败层 | 证据判断 |
|---|---|
| A. Provider/API 失败 | 现有记录不支持：保留了实际响应 usage / 模型信息，失败类别为输出验证 |
| B. finish_reason=length 截断 | 未发生：两次均为 stop |
| C. JSON 解析失败 | 可能；历史记录无法确认 |
| D. JSON 结构错误 | 可能；历史记录无法确认 |
| E. Pydantic 字段缺失 | 可能；历史记录无法确认 |
| F. 字段类型错误 | 可能；历史记录无法确认 |
| G. enum 值错误 | 可能；历史记录无法确认 |
| H. 数量限制错误 | 可能；历史记录无法确认 |
| I. 安全校验拒绝 | 可能；与 Schema 错误共享安全错误分类，无法确认 |
| J. 业务持久化失败 | 现有记录不支持：该路径有不同的持久化错误分类 |
| K. 其他 | 未建立导致旧两次失败的其他具体原因 |

**most likely：只能定位到输出契约／安全验证这一族；C–I 之间没有足够证据可靠排序。** 未把 abnormal、edge、high、数组 steps、null 或缺字段写成旧模型实际输出。也没有证明任何代码缺陷直接造成这两次 DeepSeek 失败。

离线创建了两个**合成候选**：enum 错误与敏感内容安全拒绝。它们都复现旧记录的外围表现（stop、有 usage、AIResponseError、无快照／Session／Draft），新增摘要能够区分二者。这证明旧记录存在诊断歧义，并非恢复了历史响应。用户要求的“两次真实失败的精确最小 fixture”因信息未留存而无法可靠构造；本报告保留这个限制，没有伪造 fixture。

另一个独立确认的通用问题是：第三方 Provider 自行抛出的 Pydantic ValidationError 原先会被服务内层转换成 Provider/API 错误。现已归入 Schema 路径并增加回归测试；没有证据表明旧 DeepSeek Pilot 走过此分支。

## 4. Prompt / Schema 核对与修复

### 4.1 逐字段契约

v2 的完整 JSON 示例通过实际 Pydantic Schema 验证，未发现直接文字冲突。实际顶层键是 `case_drafts`，不是 `drafts`。所有字段必填、禁止 null；根对象及嵌套对象禁止额外键。文本会 trim；除 precondition 外必须非空。

| 字段 | 实际 Schema（本阶段不变） |
|---|---|
| summary | string，1–2000 字符 |
| test_points | array，1–20 项 |
| test_points.category | functional / reliability / boundary / compatibility / recovery / security |
| test_points.title | string，1–200 字符 |
| test_points.description | string，1–1000 字符 |
| test_points.priority | P0 / P1 / P2 / P3 |
| case_drafts | array，1–20 项 |
| case_drafts.suggested_code | string，3–80 字符，`^[A-Z][A-Z0-9_]{2,79}$` |
| case_drafts.title | string，1–200 字符 |
| case_drafts.module | string，1–80 字符 |
| case_drafts.priority | P0 / P1 / P2 / P3 |
| case_drafts.case_type | checklist |
| case_drafts.scenario_type | normal / negative / boundary / compatibility / recovery / security |
| case_drafts.precondition | string，0–4000 字符；允许空字符串 |
| case_drafts.steps | string，1–4000 字符；不接受数组 |
| case_drafts.expected_result | string，1–4000 字符 |
| limitations | 1–8 项 string 数组；每项 1–1000 字符且非空 |

v2 的 3–6 个点／草稿、1–2 条 limitations 和简短文本是兼容的生成指导，没有与 Schema 的上限冲突。v2 对 module 长度、所有文本必填／非空、空前置条件与 null 的区别、limitations 元素类型／非空、嵌套额外键的说明不足。v3 明确补全这些约束，继续使用合法通用示例和原枚举，没有增加需求专用规则。完整审计摘要在 `prompt-schema-audit.json`。

Schema 的 StrictModel 名称本身不意味着 Python strict=True；本报告的类型拒绝结论以真实 JSON 路径的测试为准。没有为了配合模型输出放宽 Schema。

### 4.2 格式漂移验证与接受边界

| 离线输入 | 结果及原因 | 实验边界 |
|---|---|---|
| scenario_type=abnormal 或 edge | 拒绝，enum | 继续使用 negative / boundary 等既有合法值，不自动替换 |
| priority=high | 拒绝，enum | 只允许 P0–P3 |
| case_type=functional | 拒绝，enum | 只允许 checklist |
| steps 为数组 | 拒绝，string_type | 既有九字段文本契约，不拼接修复 |
| precondition=null | 拒绝，string_type | 应输出 string；空字符串合法 |
| limitations=[] | 拒绝，too_short | 至少一条局限说明 |
| test_points 或 case_drafts 超过 20 | 拒绝，too_long | 保留原数量上限 |
| 额外字段 | 拒绝，extra_forbidden | 顶层与嵌套均禁止额外键 |
| 缺字段 | 拒绝，missing | 保留所有必填字段 |
| 完整 bare/json/JSON Markdown 围栏 | 接受（内部 JSON 合法时） | 原有去完整围栏行为，无语义转换；行为未扩展 |
| 不完整围栏、JSON 前后解释文字／多个对象 | 拒绝，JSON 解析失败 | 不抽取片段、不修复 JSON、不二次生成 |
| 数字或布尔值替代文本 | 拒绝，string_type | 不转成字符串 |
| 合法 JSON、precondition 空字符串 | 接受 | 原 Schema 允许 |
| module 空白或超过 80 字符 | 拒绝，字符串长度 | v3 明确告知已有边界 |

### 4.3 安全诊断与通用稳定性修复

1. 新增 `app/services/test_design/diagnostics.py`。内存摘要只有 `stage`、`error_categories`、`field_paths`、`error_count`、`schema_error_codes`。Pydantic 提取关闭 input/context/url，忽略 message；仅允许固定类别与代码。未知键名掩码为 extra_field，负数或超出 9999 的索引掩码整条路径。摘要数组最多 20 个标识，数量最多 10000，路径有长度／深度边界。
2. API、输出上限、无内容、JSON 解析、Schema、安全拒绝、业务持久化分别设置固定阶段。每次调用重置摘要。安全原因只给敏感内容／缺少 Demo 范围等固定类别，不保存匹配文本。第三方 Provider 的 ValidationError 正确归类；不支持额外属性的 slotted Provider 仍可使用。
3. 新增默认关闭的 `--validation-diagnostics`。仅新 Pilot 的 Proposed 显式启用时，在 `audit/<attempt>.validation.json` 写关联标识与清洗后摘要；Adapter 与框架再次清洗。不加入数据库字段、不改旧 outcome。先写请求 outcome，再写 audit；audit 写入失败会停止并保留已有请求证据，禁止重放。
4. Prompt 升级 v3。依赖简单的共享常量 `test_design_contract.PROMPT_VERSION`，Prompt、Run、Session 和计划一致；共享文件包含在源代码 hash 清单中。dry-run 不因读取版本而初始化 app/config/数据库。
5. 保留 SDK max_retries=0、每次生成一次 create 调用；没有 LLM 修复、纠错重试、挑选多次生成结果、本地枚举替换或字段类型转换。

新增虚构认证、上传、权限状态、数值边界 fixture 共用同一契约，未使用正式 28 条输入或参考场景。两条合成失败候选与诊断恶意字段 fixture 也未使用历史 raw response。

## 5. 对论文方法与数据的影响

| 项目 | 本阶段变化 |
|---|---|
| Prompt | 从 v2 升级 v3；补充已有输出约束，模板 hash 改变 |
| 方法架构 | 不变：一次调用联合生成点与草稿，严格验证、本地评分、持久化、人工审核 |
| Schema / 数据库 / migration | 不变；不迎合模型格式 |
| 评价标准、规则质量分、接受流程 | 不变 |
| Baseline | baseline-v1 与模板 hash 不变 |
| 正式需求与参考场景 | 字节与 v1.0 hash 不变 |
| 历史第二阶段及 Pilot-v1 | 不回填版本、诊断或结果；旧记录保留 v2 |

Prompt 是实验配置的一部分，所以 v2 Pilot 不能被改写成 v3 的验证结果；后续新批次应有独立版本、目录和代码快照。当前提交 HEAD 仍为 fc58042，本阶段修改未提交／推送。

正式数据集 SHA-256（与 DATASET_README v1.0 一致）：

- requirements.jsonl：`7eaf3c824d35318f910c2134adbd0f5e2314ff6d56a7a04a00c96f4aea67c6d7`。
- reference_scenarios.jsonl：`4b7663d5a73df3676c0ff97043911a8cfb0118399dfe2c3ee965d31c2dc8b178`。

`reference scenarios leaked to provider = false`：框架 tasks 只传 title / requirement_text；Adapter 只构造这两个 Context 字段；Prompt 消息构造不接收参考场景。未读取正式参考场景内容来构造修复或 fixture，只计算文件 hash。计划中的参考项供后续评价使用，不进入 Provider 参数；本阶段无真实 Provider 请求。

## 6. 新版本

- 当前 Proposed：`test-design-v3`。
- v3 Prompt SHA-256：`1ce470e27c23fea69d0554dedb3d4a88f16053af3fb44f166181b9f01bd3cf9f`；重复计算稳定。
- 历史 Smoke / Pilot-v1：保留 `test-design-v2` 与 V2 hash。
- Baseline：`baseline-v1`，hash `ec5f5690c0e6ada964cafe3a8903ab070269733c3b87363eeef2a7e450859dd3`。

`offline-contract-checks.json` 只保存上述版本／hash 和合成错误的安全摘要，不保存完整 Prompt 或模型响应。正式实验尚未开始冻结；后续真实技术 Pilot 前需冻结包含本次修改的新代码快照。

## 7. 自动化验证

测试先 RED 后 GREEN；原测试没有删除，覆盖率阈值没有降低。初始诊断测试 28 项失败；第三方服务分类、slotted Provider 和位置掩码分别补充 RED；Prompt 契约 RED 为 14 failed / 5 passed。最终新增聚焦测试 **58 passed**。RED 记录只保留固定测试标识、数量和耗时，未保存异常内容、source 摘录或完整 Prompt。

| 检查 | 实际执行结果 | 审计文件 |
|---|---|---|
| 新增诊断／v3 聚焦回归 | 58 passed，2.61 秒 | diagnostics-locator-green.txt |
| AI Test Design / 实验 / Run / Review / Smoke 相关回归 | 393 passed，56.65 秒 | pytest-related.txt |
| Provider 元数据、配置、既有 AI 审核补充回归 | 183 passed，6.71 秒 | pytest-ai-support.txt |
| 完整 pytest + coverage | **977 passed**，130.51 秒 | pytest-full-final.txt |
| 覆盖率 | **95.14%**；原门槛 90% | coverage.xml 与完整测试日志 |
| Ruff | `ruff check . --no-cache`，All checks passed | ruff.txt |
| Migration current | d7e2f6a9b301 (head) | db-current.txt |
| Migration check | No new upgrade operations detected | db-check.txt |
| 原库与旧 Pilot SQLite | foreign_key_check=[]；integrity_check=ok | preservation-final.json |
| 旧报告／Pilot 保护 | 24/24 文件 SHA-256 一致 | preservation-final.json |
| 原 instance 保护 | 154/154 文件 SHA-256 一致 | preservation-final.json |
| 正式数据集 | 两个 SHA-256 与 v1.0 一致 | preservation-final.json |
| 原测试／受保护源码 | 原 test 函数删除 0；Schema／模型／migration／正式数据变更 0 | preservation-final.json |
| 额外围栏／类型兼容探针 | 10/10 预期结果；每个 FakeClient create 一次 | offline-wrapper-probes.json |
| 新文件实际本地凭据扫描 | 匹配 0；不记录凭据值／环境值 | artifact-safety-final.json |

完整验证通过 `.venv` Python 调用 `pytest.main`，参数保持为：

```text
--cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90
```

外包一层仅用于本阶段的网络 guard，不修改业务代码或 pytest 配置。393 + 183 = **576 项相关回归**均通过，相关 guard 的被拦截网络尝试为 0。完整最终 guard 的被拦截外部连接尝试为 0；仅放行当前测试进程登记的精确临时 loopback IP:port，避免误放行普通本地代理。

首次全量测试保留了 **4 failed / 973 passed** 的证据：最初的“禁止所有 socket 连接”guard 误挡既有本地 HTTP Smoke，本机代理也参与了 localhost 请求。只修正审计 guard 的本地 fixture 连接与 loopback proxy 绕过，不修改业务代码、不删原测试；先验证交付测试 **18/18**，再完整重跑获得上述 977 passed。首次日志为 pytest-full.txt / network-guard-full.json，最终为 pytest-full-final.txt / network-guard-full-final.json，没有把首轮失败写成通过。

网络计数限于受控 Python connect/connect_ex/create_connection；这不是系统级防火墙证明，不覆盖 PowerShell 子进程、OS DNS 或 sendto。源码审查确认相关子进程为本地 HTTP fixture 或干跑；生成测试注入 FakeClient，无真实 DeepSeek 调用路径。本阶段没有执行 `--execute` 的真实运行命令。

全量记录有 357 条 warning（包括弃用与资源警告），没有测试失败；保留在完整日志中，未修改 warning 规则掩盖结果。独立只读代码审查及报告审查通过，位置掩码问题已先 RED、修复、GREEN，并被独立复核。历史真实失败的字段级原因仍不可恢复，这是证据限制，不被本次测试结果消除。

## 8. 是否可以重新进行技术 Pilot

**ready**。

含义是离线契约、诊断、安全边界、测试和审查已满足申请另一次技术 Pilot 的条件。技术 Pilot 准备状态不代表真实服务可用性、Proposed 成功率提升、语义覆盖质量或正式实验结果。

建议下一步另行授权 **Pilot-v2**：先冻结包含 Step 3-C 修改的新代码快照，使用新的独立运行目录，明确最多 2 条虚构 Pilot 需求 × 2 种方法 = 4 次请求；同一模型及参数，启用安全 validation diagnostics，一次尝试只调用一次，不对旧 Run 重放或覆盖。新结果应与 v1 分开保留，成功与失败都统计；正式 28 条实验和人工评分仍须另行安排。

本阶段已停止于离线修复和报告；未提交、未推送、未发送真实请求，等待下一步授权。
