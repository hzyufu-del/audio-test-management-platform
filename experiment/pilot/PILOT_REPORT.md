# Step 3-B 小规模 Pilot 报告

pilot_only=true  
formal_experiment=false  
evaluation_status=not_evaluated

本轮仅验证真实调用、保存、关联及匿名展示准备。Pilot 不进入正式论文主实验统计，没有人工评分或用例接受/拒绝。

本轮执行完成：4 次真实响应，Baseline 2 次成功，Proposed 2 次输出校验失败。两条真实流水线的成功闭环尚未同时通过，因此当前不能开始正式 28 条需求 × 2 方法实验。

## 基线信息

```text
pilot_base_commit: fc58042f3457efe97e1b5ae2521b743995d6a2bc
branch: thesis/llm-experiment-foundation
provider: deepseek
requested model: deepseek-v4-pro
returned model: deepseek-v4-pro (四次均有本次响应元数据证据)
endpoint: https://api.deepseek.com
max_tokens: 8000
timeout: 60 seconds
temperature: not sent
thinking: disabled
retry: SDK max_retries=0; 无自动或人工补跑
attempts_per_requirement_per_method: 1
stream: false
baseline prompt: baseline-v1
proposed prompt: test-design-v2
```

正式数据集 SHA-256（执行前、执行后完全相同）：

```text
requirements.jsonl:
7eaf3c824d35318f910c2134adbd0f5e2314ff6d56a7a04a00c96f4aea67c6d7
reference_scenarios.jsonl:
4b7663d5a73df3676c0ff97043911a8cfb0118399dfe2c3ee965d31c2dc8b178
```

Pilot 使用单独的 pilot-v1 数据，未向模型提供正式 28 条需求或参考场景：

```text
Pilot requirements SHA-256:
8cfc102981eec36b0e358755d94f19fd4d4b36ebdcfa4541bc741076d94ddbe6
Pilot references SHA-256:
eb14e5f607134d78ef497084a0e83894c5a9acd7304602cb0182de2e7e275894
baseline prompt_hash:
ec5f5690c0e6ada964cafe3a8903ab070269733c3b87363eeef2a7e450859dd3
proposed prompt_hash:
47204e231b71bac5f94010b88e406f35bdf66e2f21d7cd1e06d28b9e6dfb3cf1
```

49 个已核对文件形成一个本地安全快照；范围为第二阶段追溯、Smoke 修复、第三阶段方案/数据/工具及测试，未发现未知修改。未 push、未重写历史。调用前 git status 干净；执行期间源码摘要未变。

本轮在请求前仅修复 experiment/framework.py 的审计字段：明确写入 pilot_only、formal_experiment、pilot_base_commit，并增加冻结 commit 的回归测试。未修改 Prompt、Provider、业务生成路径、参数或正式数据。新增测试先失败（缺少 pilot_only），修复后通过。原准备文件中两处末尾空行被保留；git diff --cached --check 的这两条空白提示不影响执行，本轮未为调整历史修改其内容。

## 预演和冻结

默认 scripts/run_pilot.py 预演已执行并保存在 [dry-run.json](../pilot_runs/step3b-audit-20261002T051152Z/dry-run.json)。默认预演不读取执行配置、不构造适配器、不开库、不调用模型。实际参数另存 [frozen-preflight.json](../pilot_runs/step3b-audit-20261002T051152Z/frozen-preflight.json)，所有检查通过后才执行 --execute。

固定顺序：

1. PILOT_AUTH_001：Baseline → Proposed。
2. PILOT_SEARCH_001：Proposed → Baseline。

每对标题和 requirement_text 完全相同，每方法 attempt_no=1。控制变量采用同一个 Provider/endpoint/model/max_tokens/timeout；thinking 关闭、不发送 temperature、SDK 重试关闭。Baselines 与 Proposed 的 Prompt 和 JSON/Schema 机制属于实验方法差异。

沿用已有 experiment/pilot_runs 设计；本次输出为 pilot-step3b-20261002T051712Z，预演审计为 step3b-audit-20261002T051152Z。未创建正式 results 或正式评价数据。

## 调用统计

```text
planned requests: 4
actual requests: 4
successful: 2
failed: 2
pre_call_failed: 0
unresolved/running: 0
unexpected retries: 0
known total tokens: 7787
provider usage present: 4/4
formal experiment started: false
```

真实请求数的证据是四份本轮 response model、usage、finish_reason 元数据，以及每个冻结 task 一次 SDK create、max_retries=0 的已验证代码路径；没有单独捕获 HTTP 传输事件日志。没有再次调用执行入口或手工补跑。进程退出码 1 表示存在失败结果；四个登记任务均已终结并保存。

## 每次尝试

Token 列依次为 prompt/completion/total；latency 单位 ms。

| requirement | method | status | latency | tokens | finish_reason | output |
| --- | --- | --- | ---: | ---: | --- | --- |
| PILOT_AUTH_001 | baseline | succeeded | 10532 | 339/915/1254 | stop | [outcome](../pilot_runs/pilot-step3b-20261002T051712Z/attempts/001_PILOT_AUTH_001_baseline/outcome.json) |
| PILOT_AUTH_001 | proposed | failed | 10915 | 1139/1673/2812 | stop | [outcome](../pilot_runs/pilot-step3b-20261002T051712Z/attempts/002_PILOT_AUTH_001_proposed/outcome.json) |
| PILOT_SEARCH_001 | proposed | failed | 8779 | 1162/1315/2477 | stop | [outcome](../pilot_runs/pilot-step3b-20261002T051712Z/attempts/003_PILOT_SEARCH_001_proposed/outcome.json) |
| PILOT_SEARCH_001 | baseline | succeeded | 6089 | 362/882/1244 | stop | [outcome](../pilot_runs/pilot-step3b-20261002T051712Z/attempts/004_PILOT_SEARCH_001_baseline/outcome.json) |

四次 finish_reason 均为 stop，两个 Proposed 失败并非 token 截断。它们的安全错误类型为 AIResponseError，说明为“AI test design output failed validation.”。现有文案未区分 Schema 与输出安全检查，不能据此定位某个字段；未保存未经校验的原始 Proposed 响应，亦未为诊断增加请求。

Baseline latency_scope 为 baseline_adapter_including_validation，Proposed 为 test_design_service，范围不同；本轮仅核对记录，不据此比较速度或质量。

## Baseline 验证

两份 initial_text 均成功保存，来自本轮虚构 Pilot 响应。每份 6 条，共 12 条；九字段均可明确读取，无缺失字段。原文与 outcome 保持不变，另存原文、规范化九字段以及逐字段转换记录。

[无语义转换表](../pilot_runs/step3b-audit-20261002T051152Z/transcription-rules.json) 在查看响应前冻结。仅整理版式、标签、首尾空白、编号大写及冻结表内的一一对应值；不补充步骤、预期或业务内容。无法映射的字段值按原文保留，不变成默认值或猜测值。

本次优先级“高/中”、用例类型“功能测试/异常测试/边界测试”及若干场景字面值不在冻结枚举转换表内，共 36 处保留字面值。编号中的连字符也未改成下划线。统一九字段展示完成不表示这些值已满足 DraftEditInput 的接受约束；本轮没有进行审核、修正或质量评分。

生成正文的前言、分隔线作为版式外内容保留记录，没有丢弃用例。转换链、字段来源行和结果校验另存本次 normalization 目录。

| Pilot requirement | 原文 | 九字段及逐字段转换 |
| --- | --- | --- |
| PILOT_AUTH_001 | [initial text](../pilot_runs/pilot-step3b-20261002T051712Z/normalization/001_initial_text.txt) | [normalized](../pilot_runs/pilot-step3b-20261002T051712Z/normalization/001_normalized.json) |
| PILOT_SEARCH_001 | [initial text](../pilot_runs/pilot-step3b-20261002T051712Z/normalization/004_initial_text.txt) | [normalized](../pilot_runs/pilot-step3b-20261002T051712Z/normalization/004_normalized.json) |

[转换汇总](../pilot_runs/pilot-step3b-20261002T051712Z/normalization/conversion-log.json)保留 12 条用例、108 个字段来源及 36 个未映射字面值。

## Proposed 验证

| Pilot requirement | GenerationRun | Version | Run status | Session | Draft IDs |
| --- | ---: | ---: | --- | --- | --- |
| PILOT_AUTH_001 | 1 | 1 | failed | null | [] |
| PILOT_SEARCH_001 | 2 | 2 | failed | null | [] |

两个 Run 都来自本轮独立 proposed.sqlite，Provider=deepseek，具有真实返回模型、Token、finish_reason、时间、Prompt/hash 和 requirement_hash。已按本轮 manifest、method、独立 Version、需求正文/hash 及时间范围核对，失败证据一致，未混入历史 Smoke/Mock/FakeClient。

实际到达 Requirement → GenerationRun → DeepSeek → 输出校验失败；没有可导出的成功结构化快照、Session 或 Draft。因此不能声称本轮验证了 strict Schema 成功及 GenerationRun → Session → Draft 成功闭环。失败 Run 本身的保存与来源关联已验证。

隔离库计数为 Project=1、Version=2、GenerationRun=2、Session=0、Draft=0、TestCase=0、ReviewRecord=0、User=0。PRAGMA integrity_check=ok，foreign_key_check 无违规。隔离库使用现有模型 db.create_all，不代表本轮执行了 Alembic migration。

## 盲评准备

[临时匿名预览](../pilot_runs/pilot-step3b-20261002T051712Z/blind_preview/BLIND_PREVIEW.md) 使用请求前冻结的随机 X/Y/Z/W 映射。材料显示相同需求及九字段内容，隐藏方法、Prompt 版本、Provider、Run、规则分、Token、latency 和内部结果路径。私有编号映射仅在 audit 目录保存，不放入公开预览。

两个有输出批次展示原始用例的无语义转录，两个失败批次如实显示无可展示用例，没有补造 Proposed 内容。预览为 Pilot 展示准备，未填写评分或邀请评价者。当前只能验证展示版式及空结果处理，无法用本轮验证两种方法成功输出的完整盲评配对；文本风格亦可能透露来源，不能保证完全盲法。

运行器生成的 evaluation CSV 仍是内部空白模板，含 method 字段，不作为匿名材料。覆盖判断、reviewer、人工分数全部为空，不属于正式评价数据。

## 数据保护

```text
formal dataset unchanged: true
formal dataset modified: false
formal experiment not started: true
formal experiment started: false
original instance files unchanged: true
frozen source hashes unchanged: true
credentials absent: true
formal quality scores created: false
formal TestCase created: false
```

两份正式 JSONL 的前后摘要与 DATASET_README 全部一致；原 instance 文件和正式 results/evaluation 路径状态与请求前完全一致。实际 API Key/Secret 的字节检查未在快照、Pilot 结果及审计材料中发现凭据。未保存 Authorization Header、环境变量内容、完整 Prompt 或原始 SDK 异常。Baseline 保存的正文限于本次虚构 Pilot 内容。

[postflight.json](../pilot_runs/step3b-audit-20261002T051152Z/postflight.json) 保存逐次元数据、Run 关联与保护核查；主证据摘要另存 primary-evidence-sha256.json，用于确认离线整理未覆盖 manifest/outcome/SQLite。

## 验证

- 相关回归：413 passed in 153.92s，全部离线测试；没有测试发出额外模型请求。
- 全仓库：ruff check . --no-cache 通过。
- Pilot：4 份 started、4 份 outcome、manifest/summary 均含显式隔离标签和冻结 base commit。
- 本轮调用后未修改实验框架或业务源码，没有修复后补跑或额外真实验证。
- [离线产物最终核查](../pilot_runs/step3b-audit-20261002T051152Z/final-artifact-verification.json)：原文逐字节相同、108 个字段来源及规范化值一致、12 条用例未丢弃，匿名材料无方法元数据；主证据和请求前冻结规则摘要未变。

## Pilot 结论

**当前尚不具备直接开展正式 28 条需求 × 2 方法实验的充分技术条件。**

原因是本轮两个 Proposed 请求均未形成成功的 Schema/Session/Draft 闭环，无法完成两种成功输出的配对展示验证；同时 scripts/run_experiment.py 当前仍只开放正式 dry-run 计划，没有真实 56 次执行入口。此前 Smoke 和离线测试不能替代本轮失败结果。

本轮没有足够原始错误细节确认一个可修复的实验框架 Bug，因此没有猜测修改 Prompt、Schema 或业务生成路径。失败记录保持原状。正式启动前仍需人工审查这两次失败、另行审查正式执行入口，以及完成正式需求/参考点和参数冻结；本轮不实施这些后续步骤。

到此停止。没有正式 56 次请求、论文主实验结果、人工评分、参考场景修改或第四阶段工作；本报告和 Pilot 产物没有自动提交，等待人工审核。此结论仅涉及执行准备，未比较两种方法的生成质量。
