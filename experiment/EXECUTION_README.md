# 实验执行框架与 Pilot 使用说明

## Step 4-A 更新：正式执行器（2026-10-04）

正式入口现在默认输出 `formal_experiment=true`、`execution_mode=dry_run`、
`provider_calls_allowed=false` 的 28 条/56 对确定性计划；不加载 `.env`、不创建客户端、
目录或数据库。`ready_to_execute` 只表示静态计划和执行器就绪，实际启动仍须重新检查
凭据、干净源码、冻结文件及是否已有批次。

```powershell
.\.venv\Scripts\python.exe -B scripts\run_experiment.py
```

只有后续明确授权采集时，才使用 `--execute --confirm-formal` 两个固定参数；缺一项
仍只打印 dry-run。**Step 4-A 不运行真实执行命令。** 固定输出为
`experiment/formal_runs/formal-v1/`，不存在换目录、选单条、attempt 2、调整参数或
自动 resume 的 CLI 选项。任何已存在批次均拒绝重启，要求人工决定恢复策略。

正式 manifest 不改写；每个 pair 在 SDK 调用前保存 running 和单次调用标记。
每次返回立即保存 outcome/方法 JSONL，核对数据、模板、规则、源码、manifest 和来源。
真实 API 错误（包括认证失败）、length、JSON/Schema/模型输出安全失败为方法 failed；
凭据泄露检测、本地异常、写入/导出/来源错误为 framework_error，并停止后续调用。
认证失败不等于把凭据写入输出；本地缺失或非法配置则在 preflight 零调用拒绝。

统一参数冻结为 deepseek-v4-pro、https://api.deepseek.com、8000 tokens、60 秒、
thinking disabled、temperature 未发送、非流式、max_retries=0。预算和超时由正式计划
固定，不接受逐条覆盖；本地配置用于启用开关、凭据、请求模型与端点一致性验证。
Baseline 采用 Pilot-v3 原样转录规则，只映射明确标签并保留缺失/歧义和原值。
不生成评价模板，不执行 Review/接受草稿或计算质量结论。

详见 [正式设计](FORMAL_EXECUTOR_DESIGN.md) 和 [离线验收](FORMAL_EXECUTOR_VALIDATION.md)。
下面原有说明保留为早期框架/Pilot 的历史范围；其中“正式入口仅预演”等状态仅适用于
Step 4-A 之前，不代表新增正式执行器的当前状态。

版本：experiment-runner-v1。状态：**已建立执行工具并进行离线验证；未发送真实模型请求，未执行 Pilot 或正式实验**。

本框架落实 [实验方案](../docs/experiment-design.md) 的输入校验、对照顺序、调用追溯和初始结果保存。正式实验仍需先完成需求及参考点的人工复核、参数冻结和评价准备。本文件不报告生成质量、人工成本或模型性能结论。

## 1. 文件与范围

| 文件 | 用途 |
| --- | --- |
| `experiment/framework.py` | 校验材料、生成计划、执行门禁、独立运行目录、逐次证据与空白评价表 |
| `experiment/adapters.py` | 普通文本 Baseline 和复用现有服务的 Proposed 适配器 |
| `scripts/run_experiment.py` | 正式 28 条需求的只读计划入口，仅预演 |
| `scripts/run_pilot.py` | 默认预演；显式执行时仅允许独立 Pilot 数据 |
| `experiment/pilot_dataset/` | 2 条独立虚构需求、12 个参考点，不使用正式 28 条需求 |
| `tests/test_experiment_*.py` | 假客户端、临时目录和临时 SQLite 的离线验证 |

不修改现有业务代码、数据库模型、API、前端或生成流程。Proposed 直接复用现有 `TestDesignService` 与 DeepSeek Provider；没有增加第二次测试点分析调用，没有自动补生成、自动修改或自动接受草稿。

正式 `dataset/v1.0` 的 ID、正文和参考点保持冻结。Pilot 使用 `pilot-v1`，ID 为 `PILOT_AUTH_001`、`PILOT_SEARCH_001`，每条也有正常、异常、边界参考点各 2 个。这些需求由 Codex 辅助编写为虚构 Demo 材料，没有读取公司、实习、日志、缺陷或已有 TestCase 数据，也没有调用 DeepSeek 制作数据。Pilot 只用于检查框架，不计入正式实验；实际评价人员的复核仍待完成。

## 2. 默认预演

在仓库根目录使用已有虚拟环境：

```powershell
.\.venv\Scripts\python.exe -B scripts\run_experiment.py
.\.venv\Scripts\python.exe -B scripts\run_pilot.py
```

两条命令向标准输出打印 JSON 计划，不加载 `.env`，不创建客户端、结果目录或数据库，不进行模型调用。第一条规划正式 28 条需求、56 次尝试；第二条规划 2 条 Pilot 需求、4 次尝试。这里的“次数”是计划数量，不是已发生请求。

可预览单条 Pilot：

```powershell
.\.venv\Scripts\python.exe -B scripts\run_pilot.py --requirement-id PILOT_AUTH_001
```

正式计划按类别内稳定 ID 顺序采用 AB、BA、AB、BA，每类两种顺序各 2 条，全体各 14 条；A 为 Baseline，B 为 Proposed。当前 Pilot 两条采用 AB、BA。计划中的每对输入只包含相同的 `title`、`requirement_text`，参考点不传入生成方法。计划含需求/参考文件 SHA-256、文本 hash、Git HEAD、当前源文件摘要及 Python 版本，因而未提交代码也有追溯依据。

`run_experiment.py` 不提供 `--execute`，本阶段不能借该入口执行正式批量实验。

## 3. 后续小规模真实 Pilot 的入口

以下是后续执行说明，**本次没有运行这些命令**。仅在具备有效本地配置、明确决定进行真实 Pilot 后使用：

```powershell
.\.venv\Scripts\python.exe -B scripts\run_pilot.py --execute
```

执行时才读取本地 `.env` 与现有 AI 配置，要求 `AI_ENABLED=true`、有效凭据、同一 DeepSeek 请求模型及 HTTPS 端点。凭据不通过命令行参数传递、不打印、不写入实验结果。可用 `--model`、`--timeout-seconds`、`--max-output-tokens` 统一覆盖两组参数，但必须在查看结果前确定；超时范围为 1～120 秒，输出预算为 100～8,000 Token。默认采用现有配置，不改写 `.env`。

Pilot 数据集和选中需求均限制为 1～3 条 `PILOT_*` 需求，每条每种方法恰好 1 次，最多 6 次尝试；现有材料默认 4 次。正式 `REQ_*` 数据无法作为 Pilot 输入。模型调用均为非流式、关闭 thinking、不发送 temperature、SDK `max_retries=0`。目录默认位于 `experiment/pilot_runs/`；`--output-dir` 也必须指定该目录下一个尚不存在的子目录。

Pilot 数据版本只接受独立一致的 `pilot-v1` 或 `pilot-v2`，拒绝混合或未知版本。新 Pilot-v2 通过 `--dataset-dir` 指定新材料；计划、调用前 manifest、逐次记录及 summary 明确标记 `pilot_version=pilot-v2`，不把新材料登记成 v1。历史 v1 材料和已有运行保持原状；该版本支持不授权额外请求，也不改变每方法一次尝试的限制。

同一请求模型标识并不能保证服务端实际返回模型始终相同。保存 `requested_model` 和有独立响应元数据依据的 `returned_model`；没有依据时后者为 null。现有 `GenerationRun.provider_model` 可能有配置回退，单列保存，不当作实际响应证据。若返回模型不同，需在后续分析中单列并检查对照条件。

## 4. 两种方法与保存边界

Baseline 使用方案规定的 `baseline-v1` 简单提示，要求 3～6 条、九个内容字段，以普通列表输出。不提取测试点，不启用 JSON 模式、Schema 或规则质量评分；安全且非空的普通正文均保留，字段缺失、数量偏差等留给人工评价，不自动丢弃。响应截断、空内容或安全检查失败记为失败。Baseline 不写入业务 GenerationRun 或 ReviewRecord。

Proposed 使用当前 `test-design-v3` 提示，在一次调用中联合生成测试点和草稿，沿用现有 Schema、安全检查和本地规则评分。首次使用时在本次运行目录创建新的 SQLite，采用现有模型建表，每次需求建立独立 Version 和 Session；不连接原 `instance` 数据库。导出时核对 Run、Session、Draft 的来源、初始内容和 pending 状态。不创建正式 TestCase，不替任何人进行审核。

每次尝试在调用前先写 `started.json`，完成后排他写入 `outcome.json`。无隐式重试、不追加重复尝试、不挑选结果、不覆盖已有运行，也不提供 resume。机器中断或写盘失败时可能只留下 started 文件，必须保留并人工核查，不能把它当成“从未调用”而重新执行同一尝试。不同新目录代表新的独立批次，不能覆盖首次证据或混入正式首次尝试。

完整 Prompt、凭据、原始 SDK 异常和未经安全检查的响应不落盘。模板版本/hash 和输入文本分别保存；固定错误类型与安全说明替代原始错误。Proposed 不保存未通过 Schema 的原始响应。安全过滤属于两种方法共有的保存条件，其失败应保留计数，不得静默删除。

## 5. 运行产物与指标口径

真实 Pilot 的预期目录结构如下；本次尚未创建运行目录：

```text
experiment/pilot_runs/<new-run>/
    manifest.json
    attempts/
        001_PILOT_AUTH_001_baseline/
            started.json
            outcome.json
        ...
    evaluation/
        coverage.csv
        human_scores.csv
    proposed.sqlite
    summary.json
```

`manifest.json` 保存输入计划、数据和源码摘要、方法顺序及统一请求参数。每份结果有 requirement_id、方法、顺序、尝试号、需求 hash、样本角色、执行模式、Prompt 版本/hash、请求/返回模型来源、UTC 时间、latency、Token、状态和安全错误；Proposed 另有 Run/Session/Version/Draft ID 及初始结构化结果，Baseline 保存安全普通正文。缺失 Token、耗时或返回模型使用 null，不填 0、不估算补齐。

样本标签为：预演 `dry_run`、离线假客户端 `offline_fixture`、未来真实调用 `real_api`。所有 Pilot 和 fixture 均标记 `formal_eligible=false`，禁止据此填入正式质量结果。`summary.json` 只统计已记录的状态及计划数量，不自动计算人工质量或成本指标。

状态含 `succeeded`、`failed`、`pre_call_failed`、`running`、`unresolved`。后两者和仅有 started 的记录尚未终结。调用前失败有外层记录，但可能没有 GenerationRun；不能将计划数、真实请求数、Run 数和完成数混用。Proposed succeeded 表示通过校验、保存并核实闭环，Baseline succeeded 表示取得可安全保存的非空完整正文，两者成功条件不同，语义质量另由人工判断。

Proposed 的 `latency_scope=test_design_service` 来自现有 GenerationRun，覆盖模型调用及解析、评分、业务保存准备，结束点在最终提交前；不包含实验建库和 Version 准备。Baseline 的 `baseline_adapter_including_validation` 从请求开始计至正文验证完毕。两者均不是完整用户等待时间，不能把差值直接解释为模型速度差异。Token 只使用响应 usage 的原值；离线 fixture 的 usage 也明确标记为 fixture。

SQLite 是隔离的现有表集合，初始 Run/Session/Draft 是结果源；当前没有真实 ReviewRecord 或人工审核动作。运行产物已通过 `experiment/.gitignore` 排除，不应提交含生成结果的实验库。预先保存的清单和逐次结果是主要外层追溯证据。

## 6. 人工评价与后续内容

`coverage.csv` 预填需求、参考点及方法；`human_scores.csv` 预填两组初始输出的索引，五项各 0～2 分，总分 0～10 分。所有判断和分数为空，不把规则分转换成人工分。

这些是内部采集表，**尚未完成盲评匿名化**。后续须由独立编号映射生成匿名评价材料，再交两名评价者独立评分；每名评价者保留自己的行和 reviewer_code，按方案处理差异。参考点不得在生成时透露，评价须使用初始结果，不能用修改后草稿替代。

后续仍需实现或组织：

1. 人工复核并冻结正式需求/参考点和实验参数；本框架不自动判断需求语义是否合理。
2. Baseline 无语义转录、离线审核表及修改字段记录；Proposed 通过现有界面真实审核并收集 ReviewRecord。不伪造审核用户或动作。
3. 匿名评价材料、多人评分登记、覆盖及人工成本汇总工具；零分母为 N/A，不能将“没有评分”填成 0 分。
4. 正式实验执行入口和正式结果分析，需在 Pilot 核查后另行完成。本次只建立正式执行计划，未开放完整批量执行。

## 7. 离线验证

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_experiment_framework.py tests/test_experiment_adapters.py -q -p no:cacheprovider
```

测试使用 FakeClient 和 pytest 临时目录。其验证对象是门禁、参数、配对输入、结果安全、失败路径及独立库闭环，不验证 DeepSeek 服务可用性、真实 Token、响应时间或测试用例语义质量。已有的历史 Smoke 和覆盖率不能代替本阶段的真实实验结果。


## 8. Step 3-C 安全诊断与版本边界

当前 Proposed 使用 `test-design-v3`。本次只澄清真实 Schema 已有的必填、
字符串非空、空前置条件、module 长度、limitations 元素和禁止 null/额外字段约束；
Schema、Baseline-v1、评价标准及正式数据集不变。旧 Smoke/Pilot-v1 的 v2 版本及
hash 保留，不回填新版本，不覆盖旧 manifest、attempt、数据库或报告。

后续新技术 Pilot 可显式设置 `--validation-diagnostics`，默认关闭。摘要只包含
固定阶段/错误类别、已知字段路径、数量及 Schema 错误代码，未知字段名称被掩码；
不保存 response、input、context、错误 message、完整 Prompt、headers 或异常原文。
只在新运行的 Git ignored audit 中输出 Proposed 诊断，不新增业务数据库字段或 migration。

该选项不发起第二次请求、不修复 JSON、不改变枚举或字段内容。单独开启该选项
仍然是 dry-run；真实请求始终需要另行授权和显式 --execute。本 Step 3-C 未执行
真实 Pilot，所有合成错误样本均为离线候选，不代表恢复了旧模型响应。

Pilot-v1 的永久状态登记及逐文件摘要保存在 Step 3-C 独立 audit 的
PILOT_V1_ARCHIVE.json，标记 pilot_version=pilot-v1、
status=completed_with_proposed_validation_failure、formal_experiment=false；
采用外部登记，保持旧 Pilot 每个文件字节不变。
