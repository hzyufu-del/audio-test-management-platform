# 正式采集 Preflight 阻塞记录

日期：2026-10-03（Asia/Shanghai）。记录：formal-v1-preflight-20261003T061617Z。

源码基线：29d271f3b4ee2ad4bfeefd2e2d8d3902c86551ca。

性质：调用前发现正式执行能力缺口；不是模型失败，不是已启动正式 attempt 的运行事故。实际请求 0，已开始 pair 0，56 个 pair 全部 not_started。已有 Pilot 数据没有修改。

## 直接阻塞

| 证据位置 | 当前行为 | 本轮要求 |
|---|---|---|
| scripts/run_experiment.py:11–25；run_experiment_help.txt | 仅 formal_plan JSON，无 --execute | 已冻结正式入口，可执行 56 个首次 attempt |
| experiment/framework.py:201–203；dry_run_plan.json | formal_experiment=false | dry-run 必须确认 formal_experiment=true |
| experiment/framework.py:299–345 | 只接受 1–3 条 PILOT_*，拒绝 formal_plan | 28 个正式 REQ_*、两方法各一次 |
| experiment/framework.py:401–448 | 部分适配器异常、ExportSafetyError 保存后继续循环 | 框架故障保存已有证据并立即停止 |

`tests/test_experiment_framework.py:64–77` 明确验证拒绝正式计划，且未调用工厂、未创建目录。本轮相关测试全部通过，说明限制是当前既定行为，不能按运行参数遗漏处理。

## 已有 Pilot 能力与正式缺口

Pilot-v3 私有 `run_control.py` 固定两条 Pilot ID、4 次请求、既有路径；其独占启动和 SDK/HTTP 计数不能直接被称为正式 56 次控制器。通用执行器具备逐 attempt 独占 started/outcome 与 fsync，但正式批次的防重复登记、56 次硬预算和实际请求计数尚无已冻结入口。

`execute_pilot` 自动创建评价模板（framework.py:275–296、376）；本轮正式采集要求不产生这些文件，因而不能不加核对地复用该路径。Baseline 逐字转录工具目前位于 Pilot 私有目录并固定 Pilot 批次，正式 normalization 入口也未冻结。

Proposed Adapter 复用业务服务、独立 Session 和来源核验；两方法任务输入及消息构造只取 title/requirement_text。这些基础能力和 Prompt hash 已确认，但不替代正式控制器和正式落盘验收。顶层 dry-run plan 仍含 reference_scenarios，必须保留本地审计属性，不能将其作为完整模型输入。

## 已执行处置

1. 审查并仅提交 Pilot-v3 最终报告；提交后工作区干净，记录新基线。
2. 运行既有正式 dry-run，保存原始 JSON 和 CLI help；未改标记或临时生成顺序。
3. 复核 v1.0 数据结构、文件 hash、56 个唯一 pair、14 AB/14 BA 和各类别平衡。
4. 将全部 pair 记录为 not_started；没有任何 Provider 请求、重试、补跑、DB 结果或评分。
5. 新鲜离线测试 163 passed，Ruff 通过；保存收尾完整性与安全审计。

停止依据来自本轮用户要求：所有 preflight 通过后才授权调用，以及本轮开始冻结方法/导出逻辑。没有借用历史未授权限制否定本轮 56 次条件授权；当前条件本身未满足。

## 后续需要人工决定的范围

若继续开展正式采集，需要先单独完成正式执行器准备：保持 Prompt、Schema、Provider 参数、评分、数据和转录语义不变，冻结正式 manifest、逐次持久化、防重/硬预算、实际请求计数，以及模型失败与框架故障的不同停止策略；离线验收后提交新的源码基线，再重新执行全部 preflight。

这只是缺口清单，不表示本轮已经实现或获准修改冻结边界。正式 manifest 未建立，56 次请求预算尚未使用。本轮停在人工审核处。
