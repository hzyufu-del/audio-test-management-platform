# Step 4 正式 LLM 对照实验采集报告：Preflight 阻塞

日期：2026-10-03（Asia/Shanghai）。**正式采集未启动，真实 Provider 请求 0 次。** 数据集和配对顺序核验通过，但当前源码没有正式执行入口，默认 dry-run 也没有通过本轮要求的正式标记检查。按照本轮“所有 preflight 通过后才调用”和“从本轮开始冻结方法”的要求，在调用前停止。

## 1. 实验身份与源码基线

| 字段 | 本轮事实 |
|---|---|
| experiment_id | null；未启动正式运行、未分配运行身份 |
| preflight_id | formal-v1-preflight-20261003T061617Z |
| dataset_version | v1.0 |
| experiment_design | docs/experiment-design.md，设计日期 2026-10-02；文件摘要见 integrity_report.json |
| formal_experiment_base_commit | 29d271f3b4ee2ad4bfeefd2e2d8d3902c86551ca |
| provider / requested_model | 按 Pilot-v3 延续的目标为 deepseek / deepseek-v4-pro；本轮未实例化真实客户端或核定实时配置 |
| returned_model | null；没有正式响应 |
| Baseline Prompt | baseline-v1 |
| Baseline 模板 SHA-256 | ec5f5690c0e6ada964cafe3a8903ab070269733c3b87363eeef2a7e450859dd3 |
| Proposed Prompt | test-design-v3 |
| Proposed 模板 SHA-256 | 1ce470e27c23fea69d0554dedb3d4a88f16053af3fb44f166181b9f01bd3cf9f |

初始 `git status` 仅有未跟踪的 `experiment/pilot/PILOT_V3_REPORT.md`；`git diff --stat`、`git diff` 无已有源码修改。审查报告及本地既有验收证据后，仅提交该报告：`29d271f docs: record final experiment readiness gate`。未提交密钥、配置、SQLite、私有 Pilot 运行材料或临时文件，没有 push。提交后、生成本轮审计材料前，工作区完全干净。

本轮未修改 Prompt、Schema、Provider、评分、安全校验、导出、normalization、数据集、参考点、人工标准、调用预算、模型或执行顺序。当前 70 个执行源码文件与 Pilot-v3 冻结摘要逐项一致；最终检查见 [integrity_report.json](audit/integrity_report.json)。

## 2. 停止原因

1. `scripts/run_experiment.py:11–25` 只接受数据目录和需求筛选，输出 `formal_plan`。`--help` 中没有 `--execute`，当前没有可直接执行的正式采集入口。
2. `experiment/framework.py:201–203` 的既有计划明确返回 `formal_experiment=false`、`formal_eligible=false`。本轮要求确认 `formal_experiment=true`，该项未通过；未修改输出标签。
3. `experiment/framework.py:339–345` 的唯一现有执行器只接受 Pilot；`299–337` 行限制独立 Pilot 的版本、1–3 条输入及 `PILOT_*` 标识。没有把正式需求改作 Pilot，也没有直接调用 Adapter 绕过门禁。
4. 现有 Pilot 循环会把部分适配器异常、导出安全失败写入 outcome 后继续下一任务（`framework.py:401–448`），尚不满足本轮正式采集的“模型失败保留并继续、框架故障立即停止”要求。

这是**正式执行能力的预检缺口**，未发生正式运行中的新故障。Pilot-v3 的四次技术链路验收及历史结果保持原样。详见 [PREFLIGHT_BLOCKER_REPORT.md](audit/PREFLIGHT_BLOCKER_REPORT.md)。

由于 preflight 未通过，没有创建或伪造 `experiment_manifest.json`，也没有将本地预演计划改成已冻结、可执行的正式 manifest。正式请求配置、实际请求消息隔离、正式落库和运行中防重尚未得到正式执行验证。

## 3. 数据与执行计划核验

本轮实际执行 `.venv/Scripts/python.exe -B scripts/run_experiment.py`，退出码 0；stdout 原字节保存在 [dry_run_plan.json](audit/dry_run_plan.json)。脚本执行时没有创建结果目录，之后才创建本轮审计目录保存证据。计划核验见 [preflight.json](audit/preflight.json)。

| 检查 | 结果 |
|---|---|
| 正式需求 / 参考点 / 类别 | 28 / 168 / 7 |
| 各类别需求 | 4 |
| 每需求 normal / negative / boundary | 2 / 2 / 2 |
| requirement_id / point_id 唯一、参考点关联 | 通过 |
| 每个 requirement × method | attempt_no=1，恰好一项 |
| 计划任务 / 方法数 / 重复 / 缺失 / Pilot 项 | 56 / 2 / 0 / 0 / 0 |
| 全体方法顺序 | 14 AB、14 BA |
| 各类别方法顺序 | 2 AB、2 BA |
| 两方法输入 | 相同 title、requirement_text |
| formal_experiment=true | **未通过：实际为 false** |
| 正式执行入口 | **未通过：不存在** |

A 为 Baseline，B 为 Proposed。沿用既有类别顺序 `AUTH → INFO → SEARCH → FILE → PERM → ORDER → SETTING`，各类别按 001–004；001/003 为 AB，002/004 为 BA。没有随机生成或替换顺序。

| 正式文件 | 执行前及收尾 SHA-256（均与 DATASET_README v1.0 相同） |
|---|---|
| requirements.jsonl | 7eaf3c824d35318f910c2134adbd0f5e2314ff6d56a7a04a00c96f4aea67c6d7 |
| reference_scenarios.jsonl | 4b7663d5a73df3676c0ff97043911a8cfb0118399dfe2c3ee965d31c2dc8b178 |

## 4. 调用与 Pair 完整性

```text
planned_attempts=56
actual_provider_requests=0
unexpected_retries=0
baseline_succeeded=0
baseline_failed=0
baseline_unresolved=0
baseline_not_started=28
proposed_succeeded=0
proposed_failed=0
proposed_unresolved=0
proposed_not_started=28
running=0
unresolved=0
not_started=56
```

[pair_audit.json](audit/pair_audit.json) 保存全部 28 个需求的两种方法、顺序号、首次 attempt、需求 hash、Prompt 版本及 `not_started` 状态；56 个 pair 均保留。没有把未调用项算为模型失败，没有生成伪 outcome、GenerationRun、Session 或 Draft。没有正式数据库或待审核正式草稿，因此 Run → Session → Draft 来源审计为“不适用：成功项 0”，不声称完成了正式来源链验收。

## 5. 工程元数据与控制变量

没有正式响应，latency、usage、finish_reason、error_type 均无正式观测值；不以 0 冒充缺失 Token 或延迟，不计算成功率或质量指标。离线测试的假客户端和临时库不计入正式请求、结果或 pair。

用户要求两方法相同控制变量。Pilot-v3 已有参数为 `max_tokens=8000`、`timeout=60s`、thinking disabled/off、temperature 未发送且为 null、`max_retries=0`、非流式。本轮因入口预检失败，没有读取这些参数创建真实客户端，没有冻结正式执行配置；不能将历史配置记录当成已验证的正式请求证据。

## 6. 参考点隔离与数据保护

```text
formal_dataset_unchanged=true
reference_dataset_unchanged=true
reference_scenarios_leaked_to_provider=false
credentials_absent=true
```

隔离证据分为两层：计划中的每个 `task.input` 只含对应需求的 `title`、`requirement_text`；本轮实际 Provider 请求为 0。没有将参考点提供给模型、补齐用例或用来选择重跑。既有 `build_plan` 的顶层仍含本地参考点，原始 dry-run 审计文件保留该事实；它是内部预检材料，不能整份作为 Provider 输入或发给生成模型。本报告不将任务输入隔离声称为生成进程从未读取参考文件。

收尾复核数据集、70 个执行源码文件，以及本轮开始时登记的历史 Pilot 目录摘要。安全扫描覆盖本轮 results 中全部文本证据，核对凭据模式、本地凭据值及完整方法模板；仅输出扫描计数，不输出配置或密钥。本轮没有真实响应、SDK 原始异常或推理内容。扫描和保护结果见 [integrity_report.json](audit/integrity_report.json)。

## 7. 本轮新鲜代码验证

| 验证 | 结果 |
|---|---|
| `ruff check . --no-cache` | 通过 |
| 实验框架、适配器、生成 smoke、Prompt v3、诊断测试 | 163 passed，8.73 秒 |
| 离线测试进程被阻断的网络尝试 | 0 |
| 本轮真实 Provider 请求 | 0 |

证据为 [related_regression.json](audit/related_regression.json)、[pytest_related.txt](audit/pytest_related.txt)、[ruff_verification.json](audit/ruff_verification.json)。没有再次运行完整 pytest，也没有重新测量行覆盖率；Pilot-v3 报告中的 1018 passed / 95.14% 属于既有验收记录。

## 8. 正式实验状态与交接

```text
preflight_passed=false
formal_experiment_started=false
generation_collection_completed=false
human_evaluation_completed=false
formal_results_conclusion_available=false
```

本轮仅提交 Pilot-v3 最终报告；本目录是新建的本地预检、验证和停止报告，未提交、未 push。未产生 initial/final cases、human_scores、覆盖评价、审核结果或效果结论。

下一步需要人工决定是否先单独完成并冻结正式执行器及其离线验收，再重做正式 preflight。该工作涉及本轮要求冻结的执行与导出边界，不在此处临时实现或静默启用。本轮不自动进入 Step 5、Prompt 修改、Pilot-v4 或第二轮生成。
