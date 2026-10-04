# Step 4-A 正式执行器离线验收

验收日期：2026-10-04。实现起点：`29d271f3b4ee2ad4bfeefd2e2d8d3902c86551ca`。
本报告对应执行器实现和离线验收，真实 Provider 请求为 **0**；未开始正式采集、未人工评分、未形成生成质量结论。

## 原 preflight 停止原因与保护

首次正式 preflight 在旧入口缺少 execute、计划仍标记 `formal_experiment=false`，且 Pilot 执行器未满足正式防重、持久化及 fail-stop 要求时安全停止。56 个 pair 均为 `not_started`，Provider 请求 0。

原 `results/FORMAL_EXPERIMENT_COLLECTION_REPORT.md` 及 11 个相关审计文件共 12 个文件均保持原字节，不将历史 manifest 改为 true。新增独立 `results/PREFLIGHT_V1_METADATA.json`，登记各文件 SHA256，并标记：

```text
formal_preflight_version=preflight-v1
execution_started=false
provider_requests=0
stop_reason=formal_executor_not_ready
```

## 实现内容

| 能力 | 实现与边界 |
| --- | --- |
| Execute gate / confirmation | 默认 CLI 只输出正式 dry-run；只有同时显式传入 `--execute --confirm-formal` 才进入真实入口，缺一项仍为零调用预演。本阶段未运行真实 execute。 |
| 正式计划 | 固定 28 条需求、baseline/proposed 两方法、56 唯一 pair、`attempt_no=1`；拒绝重复、缺失、额外、未知方法/需求及 Pilot 需求。 |
| AB/BA | 确定性 14 AB / 14 BA；七类各 2 AB / 2 BA，顺序写入 manifest。 |
| 正式 preflight | 重新校验数据及参考 hash、方法与规则、源码、干净提交、配置、固定输出目录和现有批次；失败时不进入 Provider。 |
| Formal manifest | 核心 manifest 及其 hash 不改写；记录 base commit、数据/参考版本及 hash、模板、参数、顺序、时间、56 对；mutable state 单独保存。 |
| Attempt persistence | 请求前保存 running 及单次调用标记，返回后立即保存 outcome、状态及方法 JSONL，再做完整性核验。 |
| Duplicate prevention | 固定目录 `experiment/formal_runs/formal-v1/` 独占创建；已有目录、running 或任何终态均拒绝重启，无覆盖、attempt 2 或自动 resume 入口。 |
| Fail-stop | 方法失败保存后继续；框架、写入、导出、来源、hash、重复调用或泄密异常立即停止后续请求。 |
| Source validation | Proposed 复用原业务链，逐项核对 requirement hash、prompt version/hash、Run/Session/Draft 关联与初始快照；不自动修库。 |
| Baseline normalization | 沿用 Pilot-v3 冻结 literal-transcription-v1 规则；保存 raw、normalized、conversion_log，保留原枚举、缺失和歧义，不补写语义。 |
| Safe export | 每项持久化前后扫描 JSON/JSONL、附加文件和二进制数据库中的实际凭据及完整模板；最终再完整扫描。未知异常只记录固定安全代码。 |
| Evidence integrity | 不可变记录独占写入，mutable 文件临时写入、flush/fsync 后原子替换；恢复只使用成功保存的内存快照，不信任被污染的磁盘状态。 |

新增模块为 `formal_plan.py`、`formal_storage.py`、`formal_adapters.py`、`formal_runner.py`、`normalization.py`；`scripts/run_experiment.py` 接入独立正式路径。原 Pilot 执行器、Adapter、Prompt、Schema、业务评分及评价标准未改动。`.gitattributes` 仅防止 Git 换行转换改写冻结输入、规则和已登记历史证据的字节。

统一参数保持：DeepSeek / deepseek-v4-pro，端点标识 api.deepseek.com，max_tokens=8000，timeout=60 秒，thinking=disabled，temperature 不发送，stream=false，max_retries=0。无应用重试或 fallback。

Adapter 签名仅向方法传递 `title`、`requirement_text`；参考点只参与数据集完整性校验，不进入消息。测试捕获全部消息并逐字核对方法模板与当前需求输入。

## 状态机

```text
not_started → running → succeeded / failed / framework_error
```

| 状态 | 含义及后续动作 |
| --- | --- |
| not_started | 尚未进入 attempt；框架停止后剩余项保持此状态。 |
| running | 请求前证据已成功保存；调用标记可能已存在，返回结果也可能未知，不能回退或重试。 |
| succeeded | 方法结果、保存、来源及立即完整性校验通过。 |
| failed | 真实 API 错误、length、JSON/Schema/模型输出安全失败或 Baseline 正常返回但无法按冻结规则解析；保存后继续下一个 pair。 |
| framework_error | 配置、源码/数据/manifest hash、写入、导出、映射、来源、意外重复、泄密及本地异常；停止整批。 |

真实 API 认证错误按 API 方法失败处理；本地凭据缺失在 preflight 拒绝，凭据被写入输出则属于框架泄密故障。三者分别记录。

KeyboardInterrupt、SystemExit 或本地异常不触发重试。若 framework_error 也无法落盘，保留 running 和已有证据；批次锁仍拒绝再次启动。被污染的原始文件保留，安全摘要不回显污染内容，无法可靠计算的状态用未知值表示。

## Fake 56-run 与故障验收

完整业务链集成测试使用假客户端、临时数据副本及临时 SQLite：`execution_mode=offline_fixture`、`formal_eligible=false`。

| 指标 | 结果 |
| --- | ---: |
| planned / provider_fake_calls | 56 / 56 |
| unique pairs / duplicates / missing | 56 / 0 / 0 |
| succeeded / failed | 56 / 0 |
| 真实 Provider 请求 | 0 |
| Baseline 初始结果记录 / 转录用例 | 28 / 28 |
| Proposed GenerationRun / Session / Draft | 28 / 28 / 28 |
| ReviewRecord / 正式 TestCase | 0 / 0 |

该 Fake 返回每项一个人工固定样例，用例数仅证明链路保存与导出，不代表模型生成数量或质量。

| 故障 | 验证结果 |
| --- | --- |
| A：第 10 项 Schema 失败 | 第 10 项 failed，第 11 项继续；总计 56 次 Fake 调用、55 succeeded、1 failed；同时覆盖真实 Adapter/Service 路径。 |
| B：第 10 项结果 writer 异常 | 10 次 Fake 调用后停止，第 10 项 framework_error，第 11–56 项 not_started。 |
| C：第 10 项来源关联错误 | 10 次 Fake 调用后停止，余下 46 项 not_started；临时数据库内故意破坏的来源证据保留，未自动修复。 |
| D：第 10 项进程中断并重启 | 保留 running 或 framework_error；同目录重启拒绝，新增 Fake 调用 0。 |
| 请求前 running 写入失败 | Provider 调用 0。 |
| 数据 hash 改变、计划篡改或重复 pair | 请求前拒绝；不生成补跑。 |
| SDK/API 异常及意外第二次调用 | max_retries=0；已知 API 异常只发生一次请求；第二次调用在发送前被拦截并停止。 |
| 第 10 项附加文件或 state 写入测试凭据 | 第 11 项前停止；原污染证据保留，返回摘要不含凭据。 |
| 参考 sentinel | 仅临时参考文件加入 sentinel，正式数据未改；全部捕获消息不含 sentinel。 |
| 安全导出 | 实际凭据、Authorization 形式、完整模板、损坏 JSON 及数据库内凭据检测均有离线反例。 |

## 回归与运行证据

先运行新增 formal 测试，再 Ruff，再完整覆盖率回归；本节均为本次新执行结果。

| 检查 | 结果 |
| --- | --- |
| `tests/test_formal_*.py` | 85 passed，157.40 秒；退出码 0。 |
| `ruff check . --no-cache` | All checks passed，退出码 0。 |
| `pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90` | 1103 passed，404 warnings，289.52 秒；退出码 0。 |
| app 覆盖率 | 95.14%，达到 90% 门槛；该指标为应用代码覆盖率。 |
| `flask --app run.py db current` / `db check` | 两项退出码均为 0；终端分别确认 head 为 d7e2f6a9b301、无新增升级操作。 |
| 原业务库 | foreign_keys=1，foreign_key_check=[]，integrity_check=ok；检查前后文件 SHA256 相同。 |

全量测试保留 404 条 warning，日志包含 DeprecationWarning 与 SQLite ResourceWarning；未宣称无 warning，也未为此扩展修改业务代码。测试包装器拒绝所有外部 socket 连接，完整回归记录外部连接尝试 0、测试用 loopback 连接 14；formal 专项的两者均为 0。

本地原始验收材料位于 `experiment/executor_validation/`：`formal-final.json`、`full-final.json`、`ruff-verified.json`、`migration_database.json`、`fake_56_verified.json`、`protection_verified.json`、`safety-protection-final.json`、`dry-run-final.json`、`dry-run-verified.json` 及对应日志。迁移 JSON 中 `safe_output=[]` 是捕获限制，退出码与终端输出分别留证；不是失败。中间失败及修复前记录也保留，未覆盖。该目录按既有实验隔离方式忽略提交，安全结论在本报告记录。

## 数据与方法保护

275 个保护文件 hash 全部匹配，包含 12 个首次 preflight 文件、Pilot 历史证据、冻结研究方法及正式数据；原业务库 SHA256 为 `35a004110316c7c365dad9fbdbbc93692f818228e9d97e08e8ec288246750650`，完整回归后再次核对未变。提交前对 38 份拟提交内容和本地验收 JSON/日志做实际凭据及完整模板精确匹配，命中均为 0；此扫描只在内存中比对本地配置值，不打印或保存凭据。

| 冻结对象 | SHA256 |
| --- | --- |
| requirements.jsonl | `7eaf3c824d35318f910c2134adbd0f5e2314ff6d56a7a04a00c96f4aea67c6d7` |
| reference_scenarios.jsonl | `4b7663d5a73df3676c0ff97043911a8cfb0118399dfe2c3ee965d31c2dc8b178` |
| Baseline prompt template | `ec5f5690c0e6ada964cafe3a8903ab070269733c3b87363eeef2a7e450859dd3` |
| Proposed prompt template | `1ce470e27c23fea69d0554dedb3d4a88f16053af3fb44f166181b9f01bd3cf9f` |
| normalization_policy.json | `e9ef7c808bb9fd25c6490fefa9acb6de5a5b55ef5d403f62afb85b519a552540` |
| docs/experiment-design.md | `623bb3c4be122cc107500b8393b401790d7182fd096a8f939eaa24ebd7b946dc` |

```text
formal_dataset_unchanged=true
reference_dataset_unchanged=true
real_provider_requests=0
formal_human_evaluation=false
```

## 最新 dry-run 与停止位置

代码验收后运行无执行参数的默认正式入口，得到：

```text
formal_experiment=true
execution_mode=dry_run
provider_calls_allowed=false
requirements_count=28
planned_pairs=56
provider_calls=0
actual_provider_calls=0
ready_to_execute=true
AB=14
BA=14
```

七类各 2 AB / 2 BA。默认入口未加载 dotenv、OpenAI、app、formal_runner 或 formal_adapters，未创建正式目录或数据库。`ready_to_execute` 表示静态计划与执行器就绪；未来真实采集仍须重新通过运行时 preflight，并由用户另行明确授权。本阶段只本地提交冻结，不 push，不运行真实 execute，不推进正式采集或评分。

## 最终判断

```text
formal_executor_ready=true
```
