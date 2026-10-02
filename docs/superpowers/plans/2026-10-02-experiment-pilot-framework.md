# 实验执行框架与 Pilot 实现计划

目标：新增独立实验工具，保持现有 app、模型、API、前端、配置及正式 v1.0 数据集不变。本轮只进行离线验证，不调用真实 LLM，不运行正式实验。

## 文件和职责

- experiment/framework.py：JSONL 校验、数据版本/hash、AB/BA 计划、显式执行门禁、排他运行目录、逐次安全结果及空白评价表。
- experiment/adapters.py：baseline-v1 普通文本单次调用；Proposed 复用现有服务并使用独立实验 SQLite。
- experiment/pilot_dataset/：2 条单独的 PILOT_* 虚构需求及 12 个参考点，避免先查看正式需求结果。
- scripts/run_experiment.py：正式 28 条的只读计划入口，不开放真实批量执行。
- scripts/run_pilot.py：默认 dry-run；仅 --execute 且 AI_ENABLED=true 时可进行最多 3 条独立 Pilot 需求的真实调用。
- tests/test_experiment_framework.py、tests/test_experiment_adapters.py：使用临时目录、FakeClient 的离线验证，网络不会参与。
- experiment/EXECUTION_README.md、experiment/.gitignore：命令、数据口径、限制与运行产物隔离。

## 实施步骤

1. 记录既有工作区与保护文件摘要，核对现有服务边界。
2. 先编写门禁、计划、落盘和适配器测试，执行并确认缺失实现导致失败。
3. 实现数据校验与计划；请求只使用 title 和 requirement_text，参考点只用于评价表。
4. 实现两种适配器：相同模型/预算/timeout/thinking/retry；保留实际 metadata；Baseline 不使用 Schema 质量过滤。
5. 添加入口、Pilot 材料及说明。运行目录禁止覆盖，调用前保存 started 证据；不自动重试、不提供 resume。
6. 用 FakeClient 验证 Proposed 的独立库闭环和 Baseline 安全正文；运行无网络 dry-run、Ruff及相关回归。
7. 对比保护摘要，报告具体验证结果。不得用离线 fixture 或 Pilot 产生正式实验结论。

## 结果约定

Pilot manifest 与每个记录均为 sample_role=pilot、formal_eligible=false；测试为 offline_fixture，真实未来调用为 real_api，预览为 dry_run。保存请求/返回模型来源、Token 原值及缺失、方法特定 latency_scope、失败状态。完整 Prompt、凭据、原始异常和未经检查的响应不落盘。

每次尝试保存独立 started 与 outcome 文件；终态采用排他创建，不覆盖、不再次调用。写入故障须停止并保留未解决证据。正式计划按类别内 AB/BA/AB/BA 排序，56 个动作，14 AB 与 14 BA。调用顺序不根据结果调整。

## 验收边界

本轮不执行 --execute，不产生真实生成结果、不建仓库内实验数据库、不接受草稿；测试数据库只在 pytest 临时目录。框架不是自动人工评分器，评价表分值为空。源码/环境/数据版本在执行 manifest 中追溯。

