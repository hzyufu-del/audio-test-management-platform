# Step 4-A 正式执行器设计

日期：2026-10-03。范围：执行编排、保存、导出、审计、离线测试；真实请求固定为 0。本设计落实本轮已明确授权的执行器实现，不修改研究方法。

## 现状与选型

现有路径是 dataset → build_plan(formal_plan) → 只读 CLI；唯一执行器 execute_pilot 拒绝正式输入。Pilot 已有数据结构验证、确定性 AB/BA、单次 Adapter、独立 Proposed SQLite、来源验证、安全元数据和逐次证据。其角色标签、1–3 条限制、四次私有控制器、自动评价模板、导出错误后继续行为不能直接作为正式路径。

采用独立正式编排，复用既有 Adapter/业务链和安全规则。相比放宽 Pilot（容易改写历史语义）或直接批调 Adapter（缺少持久化与防重），独立编排使本次状态机和防重边界明确。Pilot 源码和全部历史结果保持不变。

## 模块与流程

`formal_plan.py` 负责冻结数据 hash、56 对输入/顺序、无 reference 正文的正式计划、模板 hash 和源码证据。`formal_storage.py` 负责独占运行目录、不可变 manifest、原子 JSON、逐次 running/outcome、状态表和导出。`formal_adapters.py` 负责复用 Adapter、实际 SDK 调用计数/单次门禁、消息白名单、异常分类和 Baseline 逐字转录。`formal_runner.py` 负责 preflight、逐次调用、完成即审计及 fail-stop。CLI 默认只输出计划，只有同时显式 `--execute --confirm-formal` 才允许加载配置和进入真实执行。

正式输出固定在 `experiment/formal_runs/formal-v1/`，不提供新目录覆盖/换目录补跑选项；目录独占创建即锁定该批次。存在目录、部分 running、终态或损坏证据均拒绝再次执行，提示 `partial formal experiment detected; manual recovery authorization required`。不提供 resume。测试显式注入临时目录及假客户端，与真实目录分开。

请求前建立 manifest 和 56 个 not_started 状态；每次先原子持久化 running，成功后才允许 SDK create。调用标记也在发送前持久化。单个 pair 最多一次 SDK create，总数最多 56；SDK max_retries=0，消息必须逐字等于该方法模板加当前 title/requirement_text，不接收参考点或 requirement_id。

## 状态机与停止边界

`not_started → running → succeeded / failed / framework_error`。

- not_started：尚未进入 attempt；running：请求前证据已落盘，调用结果可能未知；不可回退。
- succeeded：方法结果、保存和立即完整性校验通过；Baseline 与 Proposed 成功含义按既有方案解释。
- failed：已知 API 失败、length、JSON/Schema/输出安全验证失败，或正常返回但 Baseline 无法按冻结规则解析；保存失败证据后继续。
- framework_error：本地异常、配置/映射/来源错配、意外第二次调用、导出/写入异常、数据/manifest/源码改变或导出泄密；停止整批，剩余 pair 保持 not_started。

进程中断时保留 running 或可持久化的 framework_error。若终态写入也失败，不覆盖已有 running；全局批次锁仍拒绝重启。错误消息为固定安全文本，不保存异常字符串/堆栈。已落盘证据不删除。

## 不可变与验证

manifest 包含正式身份、模式、基线、数据/参考文件 hash、方法版本/hash、统一模型参数、顺序和 56 对。独立 mutable state 保存进度；manifest 原字节/hash 永不改写。每次前后重新校验 manifest、输入文件和冻结源码，验证已完成记录与 pair 状态；最终再审计。原子写使用同目录临时文件、flush/fsync、replace；不可变记录用独占保护避免覆盖。

Baseline 转录沿用 Pilot-v3 literal-transcription-v1：只映射明确标签、trim 字段边缘、保留多行/编号/枚举原值；缺失和歧义为 null，保留 raw、源行及未解析段，不新增业务内容。正式模块只迁移解析器，不迁移匿名展示或评分流程。

Proposed 使用真实 TestDesignService：每需求独立 Version/Session，现有 GenerationRun 和 Draft 落库；成功后核对 requirement hash、模板、Run/Session/Draft、pending 状态及初始快照。框架分类补充位于实验层，不修改 Provider/Schema/业务评分逻辑。

## 离线验收与冻结

先写测试再实现：56 假调用全成功、第 10 项方法失败后继续、writer/source 错误后停止、调用前 running 写入失败零调用、中断后拒绝重启、hash/manifest 改变、重复调用/错误方法/缺 pair、参考 sentinel、secret 和完整 Prompt 拦截。测试不得连接外网。

完成新增测试、Ruff、完整 pytest 覆盖率门槛 90%、migration current/check、原库只读完整性验证。重新 dry-run 应为 formal_experiment=true、execution_mode=dry_run、provider_calls_allowed=false、56 对；ready_to_execute 表示静态执行器/计划就绪，实际执行仍需双显式参数和重新执行含凭据、干净源码、防重的 preflight。

首次 preflight 的 12 个文件原样保护，新增独立 preflight-v1 标记及 hash 清单。本轮不生成正式数据库/结果、不运行真实 --execute、不评分、不 push；以本地提交冻结实现和安全文档，报告后停止。
