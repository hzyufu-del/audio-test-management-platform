# Formal Executor Implementation Plan

**Goal:** 完成用户 Step 4-A 的正式执行器与离线验收，真实 Provider 请求 0。

**Architecture:** 独立 formal plan/store/adapters/runner，复用原有方法；固定正式目录和不可变 manifest，逐次落盘、单次请求及框架故障停止。

**Tech Stack:** Python、pytest、Flask/SQLAlchemy 既有业务链、标准库原子文件；不增加依赖。

## Global Constraints

- 不改 baseline-v1、test-design-v3、Schema、质量评分、normalization 语义、数据或评价标准。
- 不改写首次 preflight/Pilot 证据，不执行真实请求，不恢复续跑，不 push。
- 所有网络测试只用 Fake/MockTransport；外网被验证包装器阻断。

## Tasks

- [x] 保存 preflight-v1 独立标记和保护清单；完成设计。
- [x] `experiment/formal_plan.py` + `tests/test_formal_plan.py`：先 RED 后 GREEN；`build_formal_plan(dataset_dir=None)`、`validate_formal_plan(plan, dataset_dir=None)`、`verify_dataset_hashes(dataset_dir=None)`；固定 v1.0 hashes、56 pairs、顺序、纯输入和方法摘要，计划不得含 reference 正文。
- [x] `experiment/formal_storage.py` + `tests/test_formal_storage.py`：先 RED 后 GREEN；`FormalStore(path).initialize(manifest)`、`start_attempt(task, evidence)`、`record_call(task)`、`finish_attempt(task, result)`、`fail(task, code)`、`verify()`、`summary()`；不可变证据与原子状态、固定安全错误、防重。
- [x] `experiment/formal_adapters.py`、`experiment/normalization.py`、冻结规则 JSON 及对应测试：先 RED 后 GREEN；`FormalAdapters(output, settings, before_call, client_factory=None)` 提供 `generate(method, *, title, requirement_text)`，`close()`；每次调用 wrapper 报告实际边界，逐字消息检查及异常分类；结果附 `failure_origin=method/framework/null`，保留安全源结果。
- [x] `experiment/formal_runner.py`、`scripts/run_experiment.py`、`tests/test_formal_runner.py`：先 RED 后 GREEN；调用前后 hash gate、立即保存及 verify、异常不重试、56 Fake 集成与故障 A/B/C/D、双显式 CLI 门禁。
- [x] 审查所有差异，执行新增 formal 测试、Ruff、完整覆盖率回归及迁移/数据库只读检查；如失败按最小反例修复后验证。
- [x] 生成 FORMAL_EXECUTOR_VALIDATION.md，保存新 dry-run 与安全验收证据，核对保护 hash；本地提交冻结、最终 dry-run、停止。

各模块测试命令：`.venv/Scripts/python.exe -B -m pytest tests/test_formal_*.py -q`。正式原入口的旧 dry-run 测试只调整到新正式语义，Pilot 测试保留。外网禁用的包装器运行全套 `--cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90`，不使用真实配置执行模型。
