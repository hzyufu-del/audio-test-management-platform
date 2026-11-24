# 项目状态与上下文入口

更新时间为 2026-11-24（Asia/Shanghai）。11 月 22 日开题材料见第 5 节，主仓库清单和本轮全量离线回归见第 14 节。
隔离修复及历史回归结果见第9节，WEB-02换行误计修复见第10节。2026-11-13单次真实DeepSeek生成验收通过：1次POST、Schema/安全校验通过、1 Run/1 Session/6 Points/6 Drafts持久化及来源链通过，断网同key重放不新增记录；详见第13节。本次为Web请求处理链验收，不新增浏览器操作结论。中断调用人工恢复记录保留。此前 37 项环境阻塞已在 2026-11-24 的本地离线回归中逐项复测通过。人工评价与正式实验原件仍按各节记录跟进。正式实验原件定向追溯见第11节，历史完整性核验日期仍为2026-11-06。
这是综合进度入口，原始证据仍以链接中的文件为准；长期规则见 [AGENTS.md](AGENTS.md)。

## 1. 当前结论与读取顺序

系统主要功能和实验工具已有实现及历史验收。2026-11-06 核验记录：正式计划的 56 次调用已登记，49 成功、6 失败、1 未决、0 未开始。
人工评价停在 Step 5-B0 材料准备完成；现存评分表仍为空白版本，尚无人工评价结果或论文效果结论。
正式实验证据定向追溯结果见第11节。用户随后明确授权最多一次真实DeepSeek验收，已执行并通过，许可已消耗；准备与结果分别见第12、13节。该授权不包含后续付费请求、批量实验、评分或正式56项补跑。

新对话先读 AGENTS.md → 本文件 → 当前任务对应证据；不需要默认读取全部旧线程。
以下标记用于区分证据性质：

- **已核实**：按条目标注的日期直接读取文件、账本、Git、只读数据库或比对封存哈希；正式实验为 2026-11-06 核验，独立演示体验补核为 2026-11-09。
- **历史记录**：已有报告/线程记录的过去验收；不代表本次重跑或当前线上状态。
- **待确认**：缺少当前证据、实际人员安排或明确决策；不能按已完成填写。

## 2. Git 与工作区地图（2026-11-06 核验记录，11-09 补核见下）

| 工作区 | 路径 | 当前用途与状态 |
|---|---|---|
| 主仓库 | `C:/Users/lipuy/Documents/audio-test-management-platform` | 分支 thesis/llm-experiment-foundation；综合文档与阶段证据 |
| 正式冻结工作区 | `C:/Users/lipuy/.codex/worktrees/formal-preflight-1f112e4/audio-test-management-platform` | detached HEAD；原始正式运行所在地；已跟踪文件干净 |
| 恢复实现工作区 | `C:/Users/lipuy/.codex/worktrees/formal-manual-resume/audio-test-management-platform` | detached HEAD；保留受控恢复实现及未提交修改 |

2026-11-06 记录中三处 HEAD 均为 `1f112e4d6291bf0ceaf870857151e8e5a62a232e`，冻结正式执行器提交。
不要把业务 V1、数据集 v1.0、formal-v1 运行及发布 tag 混为同一版本身份。

**2026-11-09 路径补核**：主仓库分支及 HEAD 与上表一致；当前 `git --no-optional-locks worktree list` 仅列主仓库。上表两处实验工作区路径 `Test-Path` 均返回 False，当前不可见，资料位置待核实。尚未确认是否迁移、备份或另有路径；未搜索替代位置、恢复或重建。下文正式实验计数和哈希匹配结论保留为 2026-11-06 历史核验，不表述为本次重新验收通过。

**2026-11-11 测试工作区补核**：本次 Git 列表包含主仓库及 `C:/Users/lipuy/.codex/worktrees/generation-submit-safety/audio-test-management-platform`，后者分支 `codex/generation-submit-safety`、HEAD 仍为 `1f112e4d6291bf0ceaf870857151e8e5a62a232e`。目标工作区代码无未提交差异；新增测试辅助文件、报告与独立临时库被 Git 忽略，保留在 `.pytest_cache/env-repair-20261111` 和 `experiment/.pytest_cache/env-repair-*`。这不是正式实验工作区恢复的证据。

- 整理前主仓库已有修改：[正式采集报告](experiment/results/FORMAL_EXPERIMENT_COLLECTION_REPORT.md)，相对 HEAD 增加 508 行；原样保留。
- 本次整理新增 AGENTS.md、PROJECT_STATUS.md；未提交、未推送。
- 恢复工作区已有修改：scripts/run_experiment.py。
- 恢复工作区已有未跟踪文件：experiment/formal_resume.py、experiment/formal_resume_adapters.py、experiment/FORMAL_RESUME_DESIGN.md、tests/test_formal_resume.py、tests/test_formal_resume_evidence.py、docs/superpowers/plans/2026-10-05-formal-manual-resume.md。
- 正式数据、评分包和多份调查证据被 Git 忽略；本机存在不代表已进入版本历史或已有异地备份。
- 不清理上述工作区或未提交文件；本轮不改变分支、提交、远端或发布状态。

## 3. 已实现功能及验证边界

| 范围 | 实现与证据入口 | 状态说明 |
|---|---|---|
| 管理闭环 | [模型](app/models.py)、[业务蓝图](app/blueprints)、[基线报告](docs/development-baseline-2026-10-01.md) | Project/Version/TestCase/Execution/Defect；源码存在，历史页面及测试验收 |
| 自动化结果 | [JUnit 导入服务](app/services/junit_import_service.py)、[README](README.md) | TestRun、用例匹配、快照、幂等及事务保护；历史验收 |
| 日志与统计 | [日志分析](app/services/log_analysis_service.py)、[Dashboard](app/services/dashboard_service.py) | 确定性日志分析和数据库聚合；不把日志分析称为 LLM 功能 |
| REST API | [API 文档](docs/api/rest_api_v1.md)、[API 蓝图](app/blueprints/api_v1) | 现有 V1 查询/写入及校验；不宣称生产级完整认证 |
| AI 用例审查 | [审查服务](app/services/testcase_ai_service.py) | 对已有用例的可选旁路审查，与草稿生成区分 |
| AI 测试设计 | [设计说明](docs/ai/test_design_assistant.md)、[生成服务](app/services/test_design_service.py) | 单次联合生成测试点与草稿 → 校验/规则分 → 人工编辑、接受或拒绝 |
| 证据数据链 | [第二阶段报告](docs/llm-experiment-foundation-2026-10-01.md) | GenerationRun、ReviewRecord、调用元数据与审核追踪；历史验收 |
| 实验工具 | [执行说明](experiment/EXECUTION_README.md)、[执行器设计](experiment/FORMAL_EXECUTOR_DESIGN.md) | Pilot、正式执行、保存与导出；恢复实现在独立工作区 |

技术结构：Flask 单体、Jinja2、SQLAlchemy、Pydantic、Flask-Login，默认 SQLite。
代码默认 AI_ENABLED=false、Provider=mock，可选 DeepSeek；本轮未读取或改变实际凭据配置。
上述“已实现”来自源码及历史报告；2026-11-06 整理时未启动 Web、执行测试、迁移、Seed 或真实模型请求。2026-11-09 用户亲自进行的独立演示操作见下节补记。

历史验证口径：

- 2026-10-01 开发基线：622 passed，94.01% 行覆盖率；README 中数字属于这一阶段。
- 2026-10-02 数据基础补验：861 passed，95.14%；单条真实成功 Smoke，不等于正式效果实验。
- 2026-10-04 [正式执行器离线验收](experiment/FORMAL_EXECUTOR_VALIDATION.md)：专项 85 passed，全量 1103 passed，95.14% 应用行覆盖率。
- 旧报告中的 warnings、局部覆盖率和平台验证限制继续保留；本轮不宣布最新 CI/Docker/运行验收通过。

### 2026-11-09 独立 Mock Web 首次体验

证据入口：[今日体验报告](docs/portfolio/2026-11-09-web-experience-report.md)。用户亲自执行启动和浏览器操作，Codex 提供单步说明；报告阶段只读核对演示库，未调用 Harness 实现。

- 明确使用独立库 `instance/web-demo-ce9198703df5477e86de1bb580773b57.sqlite`，`FLASK_SKIP_DOTENV=1`、`AI_PROVIDER=mock`、`AI_ENABLED=false`、debug off。用户完成初始化、启动及关机后重新启动。
- 体验 Mock 生成 → 人工编辑 → 接受入库，以及执行/缺陷追溯、JUnit 示例导入、现有日志分析和看板筛选。
- 只读核实：2 Project、3 Version、4 TestCase、12 TestExecution、4 Defect、1 TestRun、1 LogFile。新增演示 Session #2 有 3 条草稿（1 accepted、2 pending）；Run #1 为 mock/succeeded；2 条审核为 edit、accept。
- 新 TestCase #4 已入库，业务状态仍为 `draft`，未实际执行；本轮没有激活该用例。通过率等界面数字仅描述演示执行记录。
- 用户反馈：单次生成 3 条偏少，与实习日执行 100 多条、项目 200 多条的体验有差距；英文及通用模板影响理解。代码核实：本次 Mock 基础场景 3 条；冻结真实提示词建议每次 3–6 条，单次 Schema 上限 20。产品建议尚未实施，不改变冻结实验。
- 这次 Demo edit/accept 不属于正式实验评分；真实模型效果、拒绝流程、REST API、新日志上传、200 条规模与完整回归均未在本轮验收。服务关闭仅已指导 Ctrl+C，实际关闭待用户确认。

### 2026-11-10 独立真实 DeepSeek 首次体验

证据入口：[真实 API 首次体验报告](docs/portfolio/2026-11-10-deepseek-first-experience-report.md)、[非敏感核验快照](docs/portfolio/evidence/2026-11-10-deepseek-first/verification.json)。

- 用户授权全新独立演示库和一次浏览器提交；新库为 `instance/llm-web-demo-24ce99e089ee46d69b9ff4bcfbd5be8a.sqlite`。用户执行迁移、初始化和 5001 服务启动；debug/reloader off、跳过 .env，凭据由用户本地隐藏输入。
- 真实请求前，用户明确将本次演示模型从 deepseek-v4-pro 改为 DeepSeek-V4.1-Flash-1017，对应进程配置 deepseek-flash；未修改正式实验模型或配置文件。
- 只读核实实际有两条重叠的 DeepSeek Run（#1/#2），均 failed/AIResponseError、finish_reason=stop；token 总数为 1883/1816，耗时 7809/4432 ms。支持真实接口返回响应，应用生成闭环失败。
- 两条 Run 的 session_id 均为空，无本次有效生成批次入库。现存 1 Session、3 Draft、3 TestCase 为初始化演示内容；0 ReviewRecord。无可审阅的本次模型正文，生成数量及内容质量未评定。
- 原计划一次，实际两次的触发来源待核实；生成 SDK max_retries=0，不能解释为 SDK 自动重试。原记录保留，Codex 未执行请求或重试。
- 详细校验字段和原始响应未持久化，尚不能确定具体失败字段；后续先明确非敏感诊断和防重复提交改进范围，不沿用本次授权补跑。服务停止及窗口凭据环境项清理待用户确认。
- 本次仅新增体验报告、元数据快照、截图副本并同步本入口；业务代码、Prompt、Schema、正式实验资料和数据库记录保持原状，未评分、commit/push。

### 2026-11-11 pytest 临时目录权限修复

证据入口：[测试环境完整报告](C:/Users/lipuy/.codex/worktrees/generation-submit-safety/audio-test-management-platform/.pytest_cache/env-repair-20261111/TEST_ENVIRONMENT_REPORT.md)、[基线完整输出](C:/Users/lipuy/.codex/worktrees/generation-submit-safety/audio-test-management-platform/.pytest_cache/env-repair-20261111/baseline-run/pytest-full.log)、[独立核验与实际模型记录](C:/Users/lipuy/.codex/worktrees/generation-submit-safety/audio-test-management-platform/.pytest_cache/env-repair-20261111/verification.json)。

- 用户本轮仅授权测试环境处理和原基线复跑。原 Harness 基线 27 passed、120 setup errors，唯一拒绝路径是工作区 `.pytest_cache/harness-submit-safety/run-ivths_fg/pytest`。原父目录的 0700 私有 ACL 关闭继承，缺少 Harness 受限写 SID；同一受限身份下的目录模式对照探针复现了原因。
- 新增进程级测试启动器，仅使本次随机临时目录内新建目录继承既有 worktree ACL；范围外权限错误仍保留。TMP/TEMP、pytest basetemp、SQLite 临时目录隔离在目标 worktree 的 `experiment/.pytest_cache/env-repair-*`，pytest 缓存插件继续关闭；没有改动测试逻辑、业务源码或全局权限。
- 原五个测试文件全部正常收集：147 collected；同组执行 147 passed、0 断言失败、0 环境错误、0 skipped，28.85 秒、退出码 0，最终完整测试日志无 PermissionError。网络拦截预检通过，Mock/FakeClient 测试保留；这是专项基线，不是全项目回归。
- 本次一次性 patch 仍请求 `hzyufu / qwen3.8-max-0902`，但模型调度 421.78 秒无 assistant/message 和工具执行后终止，实际响应模型未观察到。成功测试由 Codex 直接调用 Harness 安装中的 AclSandbox 受限执行组件完成；不能表述为 Harness 模型代理已经恢复或完成修复。历史原基线实际模型记录另行保留。
- 原测试启动器未覆盖；新启动器和证据保留。普通直接 pytest 未做全局修复；后续 Harness 任务需采用本次隔离启动方式，并单独确认模型调度恢复。业务实施继续暂停，没有项目真实 API、正式实验运行、评分或 commit/push。

## 4. 正式实验现状（2026-11-06 核验快照）

身份：formal-v1；数据集 v1.0；28 条虚构需求 × 2 种方法 × attempt_no=1；baseline-v1 / test-design-v3。
冻结模型记录为 deepseek-v4-pro；max_tokens=8000、timeout=60、thinking off、temperature 不发送、max_retries=0。
这是历史冻结配置，不是当前服务可用性或模型推荐。

| 方法 | succeeded | failed | unresolved | not_started |
|---|---:|---:|---:|---:|
| Baseline | 24 | 4 | 0 | 0 |
| Proposed | 25 | 2 | 1 | 0 |
| 合计 | 49 | 6 | 1 | 0 |

- state.dispatch_count=56；started=56、call=56、outcome=55；使用持久化 SDK dispatch 口径，远端接收/完成数未独立核实。
- 第 43 项 REQ_ORDER_002__proposed 保持 running/unresolved（GenerationRun 22），没有 outcome；根因未知，禁止补跑或补造终态。
- Step 4-F 已完成原第 44–56 项的授权恢复，原许可已消耗；不存在仍待执行的 13 项。
- all_planned_calls_issued=true、all_pairs_accounted_for=true、generation_collection_completed=true；all_pairs_terminal=false。
- 正式 Proposed 库：28 Run、25 Session、178 Draft（全部 pending）、0 ReviewRecord、0 正式 TestCase；这不代表系统无审核能力。
- 22 条需求双方成功，另有 2 条仅 Baseline 成功、3 条仅 Proposed 成功、1 条双方未成功；保留全部失败及未决记录。
- human_evaluation_completed=false；formal_results_conclusion_available=false；不能宣称覆盖、质量或人工成本改善。

原始运行位置：[formal-v1](C:/Users/lipuy/.codex/worktrees/formal-preflight-1f112e4/audio-test-management-platform/experiment/formal_runs/formal-v1)。
计数读取 state/attempt 文件；manifest 是冻结计划，里面初始调用计数不能代替运行后账本。
采集事实入口：[采集报告](experiment/results/FORMAL_EXPERIMENT_COLLECTION_REPORT.md)第 14 节、[Step 4-F 报告](experiment/results/formal_recovery_20261010/STEP4F_REPORT.md)、[56 项清单](experiment/results/step5a_20261010/pair_inventory_56.json)。
事故边界：[第 43 项调查](experiment/results/FORMAL_EXPERIMENT_INCIDENT_43.md)；只保留解释，不据旧状态再次执行恢复。

## 5. 人工评价与论文准备

最新评价入口：[Step 5-B0 准备报告](experiment/results/step5b0_20261010/准备报告.md)。

- 已准备 22 组双方成功需求、44 批、297 条初始用例；R1/R2 独立随机顺序、完整原文和空白评分表。
- 每份表含 44 行五维记录、264 行覆盖判断、297 行逐用例依据；不把自动结构检查视为评分。
- 2026-11-06 核实：14 项准备文件与封存一致，评分表为空白版本，未发现已回收评分证据；11-09 未重做该项核验。
- 该包保留 43 处 null、8 处空字符串、23 个未解析片段；不补写缺失字段、不丢弃原文。
- 未纳入优先评分包的 5 个单方成功输出仍保留于全量台账；22 组结果不能代表全部 28 组无失败。
- 待落实：两名实际评价者、培训/统一规则说明、映射保管者、截止时间、明确开评安排。
- 待落实：生成前 reference 人工复核记录；缺失时登记方案偏离，事后复核不得改称事前完成。
- 候选协议中的待确认项不能自动成为冻结规则；后续接受阶段的显示转换、edit 计数及分歧记录按协议明确后再做。
- 先独立评价初始结果，再按获准方案开展审核修改；无审核数据不能报告 0 修改成本。

协议与证据：[冻结实验设计](docs/experiment-design.md)、[冻结指标](experiment/results/step5a_20261010/FROZEN_METRICS_CATALOG.md)、[候选操作协议](experiment/results/step5a_20261010/SCORING_PROTOCOL_CANDIDATE.md)、[Step 5-A 报告](experiment/results/step5a_20261010/STEP5A_REPORT.md)。
Step 5-A 的 READINESS 是当时快照；匿名材料已在 B0 准备完成，但人员/复核手续仍待落实，不改写旧 JSON。

论文材料状态：

- 历史审查已梳理学校规范、导师注意事项和往届参考材料；以“审查毕业设计论文准备情况”线程为入口。
- 2026-11-22 开题材料已形成。题目为《基于大语言模型的智能测试用例生成与管理系统设计与实现》。[Markdown 草稿](proposal_draft.md)和 [Word 版开题报告](开题报告-郭逢盛.docx)均包含选题依据、主要内容、研究方法、进度安排及参考资料。[图 1.1 系统功能结构图](fig_1_1_system_structure.png)同时用于 Markdown，且与 Word 内嵌图片逐字节一致。
- 2026-11-17 [项目技术实现全览](thesis_context.md)记录当前工作区架构、模块、数据模型、接口、测试与部署，可用于撰写系统设计和实现章节。其正文核验日期和本机文件时间均为 11 月 17 日；11 月 22 日形成的开题材料与此技术快照可并行引用。
- 2026-11-24 核对了开题文件正文结构与配图。指导教师意见及签名栏仍为空，具体开题日、提交状态、模板适用性和参考资料核验仍待确认。
- [个人任务书](C:/Users/lipuy/Downloads/郭逢盛_毕业论文（设计）任务书.docx)文件存在；线程记录已交付 3 页 Word，本轮未重做版式或文献验收。
- README/设计文档已有架构、E-R、流程图及历史截图；不能据此认定学校要求的全套论文图表已齐。
- 历史审查所列缺口：用例图、规范活动图、时序图、完整模块图、字段级数据字典、最新审核/看板截图及独立演示验收；需逐项核对后补齐。
- 待确认：现行学校规范与正式开题模板、导师章节/题目意见、AIGC 政策、评价安排和提交节点；不推定已获得导师同意。

## 6. 文档职责与证据保护

| 文档/目录 | 保留职责 |
|---|---|
| AGENTS.md / PROJECT_STATUS.md | 长期规则 / 唯一综合状态和导航 |
| README.md、docs/api、docs/ai、docs/portfolio | 项目说明、操作、接口与模块解释；历史数字按日期理解 |
| docs/development-baseline-*、docs/llm-experiment-foundation-* | 阶段验收原文，保留历史状态 |
| docs/experiment-design.md、experiment/dataset、normalization_policy.json | 冻结研究方法、数据和规则；不为同步进度改写 |
| experiment/pilot、FORMAL_EXECUTOR_*、EXECUTION_README.md | 技术试点与执行器设计/验收；不混入正式效果结论 |
| experiment/results 各阶段、collection_report_before_* | 原始审计与报告快照；不按重复内容清理 |
| docs/superpowers、.codex 历史报告 | 实施计划和技术决策来源；计划勾选不自动等于完成 |

已检查 docs/experiment 下 40 份 Markdown，无字节完全相同的文件；主要是职责/阶段重叠。
2026-11-06 首次整理只新增两个入口；README、研究方案、阶段报告及快照均保留原文。2026-11-09 另按用户要求新增独立体验报告并同步本入口。
正式数据与评分文件受 experiment/.gitignore 影响；复制 Git 仓库并不能恢复全部证据。
跨机器恢复必须另行确认本地证据和 worktree 保存情况，不自动搬迁、复制或公开评分管理员材料。

2026-11-06 完整性核验：

- [canonical 封存](experiment/results/step5a_20261010/canonical_sha256_seal.json)：178 个正式文件匹配。
- [冻结来源封存](experiment/results/step5a_20261010/frozen_sources_sha256_seal.json)：240 项跨工作区源码条目匹配。
- [B0 材料清单](experiment/results/step5b0_20261010/PACKAGE_MANIFEST.json)：14 项准备文件匹配。
- 哈希匹配证明与所选封存版本一致，不证明语义质量、外部备份或真实远端请求完成。

## 7. 工作线程索引（建议；未更名或归档）

按主仓库路径识别到 23 条未归档、2 条已归档 Codex 对话；已重点检查关键线程，未全量审阅所有消息。
标题按应用返回原文保存；同名线程以完整 ID 区分。线程只用于补充决策背景，当前状态从文件恢复。

| 使用方式 | 原始线程标题 | 完整线程 ID | 用途 |
|---|---|---|---|
| 常用 | 整理毕设项目上下文 | 01a1ac9b-2dd0-7123-b2ba-f49fb6f59b68 | 总控、上下文维护、Harness 任务与验收 |
| 常用 | 执行 Step 4-F 正式恢复 | 01a123cb-f4ed-7b12-8b89-216e0f3459e4 | 实际推进至 Step 5-B0；另有首次演示指导，标题不是待恢复指令 |
| 常用 | 审查毕业设计论文准备情况 | 01a13f24-3392-7b13-a4ae-f5587fa55a4b | 学校要求、任务书、开题及论文证据 |
| 历史依据 | 执行正式 LLM 对照实验 | 01a10063-0dbf-7c82-8c0d-d611126c498e | Step 4-A 冻结与执行器验收；注意存在另一同名线程 |
| 历史依据 | 执行毕业设计正式实验采集 | 01a1058e-8355-7722-9976-a19efa18be37 | 初次采集、第 43 项中断及恢复边界 |
| 历史依据 | 核验 Step 4-E 恢复安全 | 01a1210e-27b3-7f61-a507-0d94c2e7543e | 当时的 13 项候选与授权前安全核验 |
| 历史依据 | 恢复毕业设计开发基线 | 01a0f6bc-6862-7c20-b16a-96c76f1cdeb9 | 环境、迁移、数据保护和早期验收 |
| 历史依据 | 建立模型生成实验数据链 | 01a0f6d4-d3af-7e30-a676-9596c5cce196 | GenerationRun/ReviewRecord 实现背景 |

其他 Pilot、CI、架构讲解、发布和技能线程保持原状，后续确需归档时再单独决定。
“完成 v1.2.0 发布收尾”（01a0106a-10a7-7321-8475-8a13006d9c87）历史记录停在网络错误；本地仅见 v1.0.0/v1.1.0 tag，未核验当前远端，不能称 v1.2.0 已发布。

## 8. 下一步与最近交接

1. 人工评价组织：确认两名评价者及安排、reference 复核记录或偏离说明；Codex 核对开评条件。
2. 在明确开评后完成独立评分并保留初判；再按冻结方案推进审核修改、裁定与统计。
3. 整理开题/论文图表、数据字典和独立 Mock 演示证据；实现辅助任务由 Codex 限定范围后交 Harness。
4. 有真实评价及审核证据后开展结果分析，报告失败、未决、分母、盲法与样本限制。
5. Git 收尾、备份/迁移和对话归档属于独立任务，本次未实施，也不默认获准。

2026-11-09 补充事项：核实第 2 节两处实验工作区当前资料位置；按[体验报告](docs/portfolio/2026-11-09-web-experience-report.md)讨论生成细化、中文体验及项目级规模验收。产品改动需另行授权，不与冻结方法混用。

2026-11-06 交接：用户批准首轮两个入口文件；新增 AGENTS.md、PROJECT_STATUS.md。
原报告、业务代码、数据、冻结规则及历史记录保持原状；无模型请求、评分、迁移、Seed、应用测试、commit/push 或对话管理操作。

2026-11-09 交接：用户完成独立 Mock 演示库的首次主要流程体验。新增今日体验报告，更新本入口；只读核对库中保存结果及数量约束，记录实验工作区路径当前不可见这一待核实事项。报告阶段未改业务代码或数据库，未恢复实验、评分、commit/push。主仓库既有采集报告修改保留；AGENTS.md、PROJECT_STATUS.md 与新增体验报告仍未提交。
后续每轮只更新相关状态、日期、证据指针与本节简短交接；旧实验事件仍保留在原报告，不在此复制完整流水账。

2026-11-10 交接：独立 DeepSeek 接口已返回响应，输出校验失败；实际两条失败调用均保留，生成内容质量和重复触发来源待确认。已保存体验报告、非敏感快照与用户截图副本并同步本入口；无代码修改、补跑、评分或 Git 提交。停止演示服务及清理当前窗口 Key 环境项待用户确认。

2026-11-11 交接：仅处理测试执行环境。Harness 受限执行组件内的原五文件基线 147 passed，完整日志、JUnit、权限探针、精确命令及模型调度记录见第 3 节。目标 worktree 代码与主仓库既有文件、数据库、Harness profiles 经前后核对保持一致，随后仅更新本状态入口；测试辅助文件和临时产物保留且未提交。下一步是确认 Harness 模型调度恢复并在后续授权下安排业务任务，本轮停止于环境验收。

## 9. 2026-11-12 修复任务 V1

授权：隔离实现、Harness 调度、本地 Mock/FakeClient 测试、非破坏性集成；不含项目付费真实模型调用、原库迁移、实验修改、评分、提交或推送。

本次直接核实：主仓库分支 `thesis/llm-experiment-foundation`、HEAD `1f112e4d6291bf0ceaf870857151e8e5a62a232e`；既有报告差异与未跟踪文档保留。旧 generation-submit-safety worktree 仍登记。由于外部目标目录写入被拒绝，采用项目 `.pytest_cache/repair-20261112/{baseline,backend,frontend,integration}` 四份 HEAD 导出快照作为等效隔离区，未复制 `.env`、现有数据库或被忽略的实验记录。

| 优先级 / 任务 | 原因与范围 | 依赖 / 负责 | 验收条件 |
|---|---|---|---|
| P1 生成请求保护 | 每次提交均新建 Run；缺少唯一请求和并发防重 | A：后端 Harness；先明确表单与服务契约 | 同键并发一次 Provider；成功重放原结果；失败不自动重试；异内容冲突 |
| P1 配置与诊断 | 配置错误可退回 Mock；校验摘要未保存 | A：服务、记录器、模型/增量迁移定义 | 配置错误明确失败；无凭据诊断可刷新查询；严格 Schema 保持 |
| P2 生成交互 | 无提交锁、等待提示、返回恢复 | B：模板和 JS；依赖 A 的请求键/状态契约 | 连击仅一次、失败可恢复、刷新不自动生成、明确实际模式 |
| P1 审核并发 | 仅检查读取时 pending；聚合状态可过期 | A 后续串行任务 | 双 Session 旧编辑冲突；正式用例与草稿一致；审核聚合一致 |
| 验收 | 已有编辑/接受/拒绝和核心管理代码保留 | Codex 独立审查 + 离线回归 | 生成→编辑→接受/拒绝→保存→重查；错误路径及原功能不回归 |

历史真实 Schema 失败字段不明，不能宣称已确定根因。新诊断用于定位下一次获准请求；冻结 Prompt、Schema、模型参数不修改。任何新模型输出失败仍应真实失败，禁止伪造或放宽校验。

执行证据暂存于 `.pytest_cache/repair-20261112`：`prepare.py`、`protected-before.json`、`run_tests.py`；基线执行使用新随机临时目录、Mock 环境、网络拦截和禁用 pytest 缓存，不覆盖旧覆盖率。当前基线运行中，不能据进度输出称为通过。

调度记录：使用官方 `DSH_HOME` / `DSH_AGENTS_HOME` 隔离运行目录及 credentials.path 只读引用，已解决全局 profile 写入阻塞。真实实现派发 `hzyufu / qwen3.8-max-0902` 在 2.03 秒退出 1，TRANSPORT/Connection error；会话 `session-4bc48878-9692-4700-b719-bc598895c248`，request/context 确认模型，assistant/message=0、tool/call=0。底层原因未记录，不推测为具体服务故障。没有反复重试或切换模型，记录在 `.pytest_cache/repair-20261112/harness-backend/{summary.json,events.jsonl,stderr.log}`。另两视觉配置仅只读核对存在，未调用。无全局配置/权限变更或密钥复制。

2026-11-12 用户追加授权：自主推进不依赖 Harness 阻塞的业务代码修复，随后由两名 Codex 实现代理分 backend/frontend 快照并行执行，明确不称为 Harness 完成。2026-11-13 继续现有成果，未重做首次审计或连通探针。

初始全量基线：1064 passed / 39 failed。缩短临时路径、恢复导出时被 core.autocrlf 转换的 shell 文件为 HEAD LF、允许本地回环后，对受影响四文件复跑为20 passed /37 failed。剩余37项为原环境阻塞：30项依赖硬链接（新临时文件探针 WinError5），7项依赖回环HTTP（WinError10013）；保留失败，未修改正式存储实现或有效断言。原日志在 baseline/experiment/.pytest_cache/repair-a0d19d9c31d84f6a8a08f4a010a8b6a3；复跑在 `.pytest_cache/t/9c82b5c1`。

独立动态审计探针4项通过（表示3个缺陷复现及1个既有闭环可用，不是修复通过）：重复POST两条Run；错误配置产生Mock成功；接受后旧编辑导致草稿与正式用例分叉；Mock请求→编辑→接受/拒绝→新连接重查可用。证据 `.pytest_cache/repair-20261112/audit-probes-results.json`、`test_audit_probes.py`、`.pytest_cache/t/187a4a35`。

2026-11-13 集成完成：前端7文件、后端13文件及主控新增端到端/演示入口、模型契约测试更新和操作说明，共26个相对基线变更文件。主控逐项检查实际差异，未替换主仓库业务代码；运行版本位于 `.pytest_cache/repair-20261112/integration`，另已打包独立源码，防止仅依赖缓存保存。没有 Git commit/push/合并。

### 问题、修复及验收

| 原问题 | 修复 | 本轮证据与结论 |
|---|---|---|
| 重复POST/并发生成 | nullable唯一request_key、输入指纹与活动scope；调用前持久claim，同键重放旧结果；无key旧实验调用保持原语义 | 独立线程/Session竞争测试，仅一次Fake Provider调用；失败key不自动重试；异payload拒绝 |
| 配置错误静默Mock成功 | AI_CONFIG_ERROR明确阻断；页面显示实际模式和安全错误 | 错误配置不创建成功Run，不调用Provider |
| 诊断未落盘 | allowlist摘要写入Run；新增只读运行页和错误入口 | Schema、timeout、业务提交失败均保留分类；无半套草稿；未保存失败原文或伪造输出 |
| 按钮连击/状态不明 | 同步提交锁、等待/断网提示、pageshow恢复、运行页仅GET查询 | 模板与Node真实JS事件测试；尚非浏览器验收 |
| 接受后过期编辑、聚合状态竞争 | Draft.revision和Session.review_revision乐观锁、整事务回滚、表单版本校验 | 独立Session交错及过期网页提交测试；409保留旧token，不能再次覆盖新内容 |
| 并发完成窗口提示失真 | scope消失后按指纹查询已有Run入口，不重调Provider | 专项竞争测试通过 |
| 重启演示可能重新Seed | 专用Mock入口，新库迁移初始化；复用仅校验版本，不Seed/迁移 | 新建和重启测试通过，已准备独立演示库 |

### 本轮测试与业务链路

- 集成联合专项：**130 passed / 0 failed**，39.09秒；含生成、诊断、前端、审核、迁移与完整请求级链路。证据：[targeted.log](docs/portfolio/evidence/2026-11-13-repair/targeted.log)。
- 全量未跳过：**1098 passed / 39 failed**，176.40秒；[full.log](docs/portfolio/evidence/2026-11-13-repair/full.log)。其中2个精确字段集合仍使用旧模型，已加入新字段并增加默认值/nullable检查，保留其余原断言；两文件复跑 **74 passed**，15.83秒：[model-contract.log](docs/portfolio/evidence/2026-11-13-repair/model-contract.log)。未把不同轮次简单相加成一次全量通过。
- 剩余37项全部与既有失败集合一致：30项硬链接权限、7项本地HTTP套接字权限。没有删测试、改FormalStore、替换硬链接语义或放宽断言来绕过。
- 静态检查：显式枚举147个Python文件执行Ruff通过；随后修改的两个模型测试及演示脚本再检查通过。目录级检查曾因缓存目录被忽略而未发现文件，未将那次空检查作为证据。
- 演示只读连接显式关闭修正后，演示专项再跑 **2 passed**，1.93秒，`.pytest_cache/t/7d7c2bbe`。
- 核心链路真实执行范围：Flask请求登录→选择Project/Version→Mock生成→同key重放→渲染草稿→编辑→接受/拒绝→关闭连接→新App实例重开SQLite→查询正式Case/Run/ReviewRecord。正式Case仍为draft，来源链和3条模拟审核记录保持。不是实际评价者评分，也不是设备测试结果。
- FakeClient覆盖DeepSeek适配器失败/timeout与持久化错误；项目真实付费API调用为0。11月10日Schema失败具体字段仍未知，未宣称旧根因已修复。
- 最终第二审查代理因额度限制中断；主控已自行核对合并差异、失败集合、旧断言保留、冻结文件与测试结果。先前独立审查发现的并发完成窗口已修复并测试。

### 安全与交付

本次前后比对113个既有数据库、profile、实验JSON/报告文件，哈希全部一致；主仓库业务源码没有写入。修复版的Prompt、Schema、quality、security、test_design_contract和config与隔离基线逐字一致。新版本的业务源码变化不能称为旧formal-v1实现；原封存清单和#43没有更改。该核验不等于找回或重新完整验收历史不可见的正式工作区。

- [修复源码包](docs/portfolio/evidence/2026-11-13-repair/repair-source.zip)：不含现有数据库、`.env`、Harness凭据/运行目录。
- [代码补丁](docs/portfolio/evidence/2026-11-13-repair/repair.patch)、[26文件清单](docs/portfolio/evidence/2026-11-13-repair/changed-files.json)、[源码哈希清单](docs/portfolio/evidence/2026-11-13-repair/source-manifest.json)。
- [机器可读验收记录](docs/portfolio/evidence/2026-11-13-repair/validation.json)、[Harness调用记录](docs/portfolio/evidence/2026-11-13-repair/harness-dispatch.json)。
- [演示操作说明](.pytest_cache/repair-20261112/integration/docs/repair_demo_usage.md)。已准备库 `integration/instance/repair-demo-f9f5c4a48ed54bb88938230eff90afc9.sqlite`，仅Mock；本轮没有启动常驻Web服务。

能够据实展示的实现：原测试管理闭环、结构化草稿生成服务、严格校验与规则分、人工编辑/接受/拒绝、正式用例保存、来源/审核记录；本轮补充数据库防重、并发审核、失败诊断、状态页及隔离演示重启。论文效果提升、真实模型输出质量和人工评价结果仍不能据此推导。

### 尚未完成与下一步

1. 在允许本地网络/硬链接的执行环境补验剩余37项；当前环境不改权限，不隐藏失败。
2. 用户按操作说明完成真实浏览器演示。当前已验证HTML与JS及Flask请求，但没有完整浏览器操作证据。
3. 单独授权后，在新库按明确模型和调用预算验收真实API；保留失败，不自动重试或改变冻结方法。
4. 进程中断/终态记录失败的running Web Run仍保持活动锁和结果待确认；没有自动解锁或人工恢复按钮。需人工确认原调用后单独处理，不能自动改成failed或影响#43。
5. 新增迁移只在全新临时/演示库执行，旧数据库升级和此迁移降级未授权/不支持。当前源码包可审查，未合并主分支。

收尾：授权内隔离实现、集成、Mock请求级业务验收已完成；整体系统最终验收仍有上述明确边界。后续从本节的交付代码和证据继续，不重新从头审计或连通测试。

## 10. 2026-11-13 WEB-02 审核换行误计定向修复

本轮用户明确授权由 Codex 直接修复与测试；未调度 Harness、未调用真实模型。范围限于审核变更字段比较与针对性回归。用户提供的真实浏览器结果是本轮定位输入，不表述为本轮自动化浏览器复验。

修复前直接核实：主仓库仍为 `thesis/llm-experiment-foundation` / `1f112e4d6291bf0ceaf870857151e8e5a62a232e`；隔离版 `.pytest_cache/repair-20261112/integration` 的249个清单文件全部匹配11-13原交付。主仓库原有报告差异及未提交文档保留。

根因：`app/services/test_design/reviews.py` 的 `build_review_record()` 对审核前后字符串直接比较；浏览器提交 steps 的 LF/CRLF 表现差异被纳入 `changed_fields_json`，随后 `len(changed_fields)` 使计数偏大。修复仅将 steps 的比较临时值执行 `replace("\r\n", "\n")`；原始快照、草稿保存、正式用例创建、版本控制、Schema和实验 normalization 均未修改。真正文字、顺序、空行、缩进变化仍计为 steps 修改；单独CR及其他字段保持原比较行为。

源码修改共3个文件（均在隔离版）：

- `app/services/test_design/reviews.py`：比较逻辑与局部辅助函数。
- `tests/test_review_records.py`：新增13项参数化/边界测试，检查字段与计数、双向/混合换行、快照原文保留和真实内容变化。
- `tests/test_experiment_routes.py`：新增5项请求级测试，覆盖仅标题、标题伴CRLF、仅步骤、二者同时修改、仅换行；同时检查版本递增、两次旧表单409、接受仅建一条正式用例且状态draft、拒绝不建用例、刷新不新增记录、来源关联和旧审核记录保持。

实际验证（全新临时库，Mock，网络阻断，无ACL/目录mode修改、无覆盖率或旧pytest缓存覆盖）：

- 修复前新增18项：**6 failed / 12 passed**，6项均为预期的steps误计断言，无setup错误；[red.log](docs/portfolio/evidence/web02-20261113/red.log)。
- 修复后4个相关文件：**93 passed / 0 failed，44.86秒**；包含原有独立Session并发控制与数据库重开闭环；[green.log](docs/portfolio/evidence/web02-20261113/green.log)、[JUnit](docs/portfolio/evidence/web02-20261113/green.xml)。
- Ruff 对3个变更源码/测试及离线启动器检查通过。没有重跑全系统、WEB-03/WEB-05浏览器验收或37项环境阻塞测试。

主仓库PowerShell可复跑命令（标签须使用新名称以保留既有日志）：

```powershell
.\.venv\Scripts\python.exe -B docs/portfolio/evidence/web02-20261113/run_offline.py verify-next tests/test_review_records.py tests/test_experiment_routes.py tests/test_review_concurrency.py tests/test_repair_end_to_end.py
```

本次实际标签为 `red`（前两个测试文件并加 `-k web02`）和 `green`（上述四文件）；完整命令、退出码及工作区在 [red-execution.json](docs/portfolio/evidence/web02-20261113/red-execution.json) 和 [green-execution.json](docs/portfolio/evidence/web02-20261113/green-execution.json)。

保护与交付：[前置哈希](docs/portfolio/evidence/web02-20261113/protected-before.json)、[验证记录](docs/portfolio/evidence/web02-20261113/validation.json)、[局部补丁](docs/portfolio/evidence/web02-20261113/web02.patch)、[新版源码包](docs/portfolio/evidence/web02-20261113/repair-source-web02.zip)、[新版清单](docs/portfolio/evidence/web02-20261113/source-manifest.json)。旧源码包、旧验收证据和现有数据库不覆盖；新包仅含源码清单文件，不含运行数据库或凭据。

影响范围：后续新建审核记录使用修正后的字段计数，相应编辑率/平均修改字段数沿用现有聚合逻辑；仅换行差异的edit仍留审核记录并消耗版本，但修改字段数为0。历史误计记录不回填，因此历史展示和统计可能仍含旧误计。没有改写原始steps或批量更新数据库。当前修复在隔离版且未提交、合并或推送。可按需在重启加载新版后补做WEB-02单点浏览器复核，本轮自动化通过不冒称新的浏览器验收。

## 11. 2026-11-13 正式实验原始证据定向追溯

机器记录：[findings.json](docs/portfolio/evidence/formal-trace-20261113/findings.json)。范围：主项目、已登记的 generation-submit-safety 工作区、两处原实验工作区及项目内 `instance/backups`；优先读取历史路径与封存索引，排除 `.git`、虚拟环境、已知测试缓存和依赖目录，不跟随符号链接、不全盘搜索。用户表示不清楚其他备份位置。本轮没有重做评分包内容、量表或匿名映射完整性审计；ZIP只查看目录索引以排除原归档。

| 对象 | 本次实际发现与结论 | 证据入口 |
|---|---|---|
| 原 formal-v1 目录 | 封存登记的原路径不存在；formal-preflight-1f112e4 与 formal-manual-resume 的外层目录仅剩 `.codex-worktree-name`，项目子目录不存在。主仓库及现存 worktree 的 `experiment/formal_runs/formal-v1` 也不存在 | findings.json 的 registered_paths、old_worktree_parent_contents |
| canonical 封存 | 清单自身 SHA-256 与既有 Step 5-A PACKAGE_MANIFEST 匹配；登记178个原始文件。限定范围普通文件按封存大小筛选后比对SHA-256，未发现原件匹配。完整匹配归档0、部分匹配归档0；原归档为“未找到、无法重新确认”，不记为178项哈希失败 | [canonical_sha256_seal.json](experiment/results/step5a_20261010/canonical_sha256_seal.json) |
| 正式数据库 | 应为557,056字节的 `proposed.sqlite3`，SHA-256 `68f02bc5c649de1063a6e80b3e0dc7a13159854d719bbc070eff092bf37857da`。当前业务库及三份已登记备份均不匹配；只读查询当前库为2 Run/1 Session/6 Draft，备份无正式采集数据规模，属于早期业务/Smoke资料 | [备份目录](instance/backups)、findings.json 的 database_candidates |
| 压缩包与备份索引 | 两份修复源码包均无formal-v1或正式数据库；R1/R2 ZIP各为两份评分材料，目录索引无原始归档。仅找到Pilot-v1归档索引，没有发现指向另一formal-v1备份的已登记路径 | findings.json 的 archive_indexes；[Pilot索引](experiment/pilot_runs/step3c-audit-20261002T053436Z/PILOT_V1_ARCHIVE.json) |
| Reference 事前记录 | 找到10-02 DATASET_README 中“仍需实际评价人员复核”的要求；没有找到记录人员、时间、范围和结论的真人完成复核证据 | [DATASET_README.md](experiment/dataset/DATASET_README.md)、[实验方案](docs/experiment-design.md)第4.3节 |
| Reference 事后记录 | 10-10 Step 5-A 与 B0 记录的是复核证据缺失和偏离处理要求；未找到事后真人复核完成记录。当前Reference字节与冻结来源清单匹配，仅证明版本一致 | [READINESS.json](experiment/results/step5a_20261010/READINESS.json)、[准备报告](experiment/results/step5b0_20261010/准备报告.md)、[冻结来源清单](experiment/results/step5a_20261010/frozen_sources_sha256_seal.json) |

**证据缺口与披露：**原始manifest/state/attempt/outcome/JSONL及正式SQLite尚未在本次限定范围找到，当前无法从原件重新独立复核生成链及数据库关联；历史审计报告、封存索引和已核验匿名材料仍在。未找到Reference生成前真人复核的可核验记录，应登记为该方案环节缺少执行证据；不能据此断言从未发生复核，也不能声称已完成。事后真人复核如后续开展，须写实际日期并保持冻结Reference不变。

论文可用披露文字：本研究对双方均成功生成的22条需求开展配对人工评价。评分材料已完成完整性核验；原formal-v1归档和正式数据库在当前限定追溯范围内未找到，原始采集链的复核依赖既存审计记录。未找到Reference在生成前经真人复核的可核验记录，该环节作为方案执行证据缺口披露。评价结果反映成功配对样本在冻结参考标准下的表现，不替代全28条需求的交付表现。

**当前评分范围与开评条件：**按用户已完成的核验，R1/R2材料可用于22对双方成功、44批、297条用例的初始五维质量与Reference覆盖评价；本轮不再次核算包内数据。其余5个单方成功输出及失败/未决不在该配对评分范围，仍保留全计划台账；没有新增审核事件时，不产生人工修改成本、接受率等结论。原件未找到限制来源链的独立复核，不妨碍对现存已核验文本作人工判断。按既有B0开评规则，登记上述限制、Reference证据缺口/方案偏离并完成下列实际安排后，可继续这22组正式评分；本轮没有替用户确认开评。

用户本人仍需登记：R1/R2对应的真实人员及基础测试背景、统一规则说明/培训日期、评分截止时间、匿名映射保管者和各人的既有来源知情情况；明确独立评分、分歧复核及未决项保留办法，并确认实际开评日期。只向各评价者分发各自包，保留初判；已知来源的作者/保管者如参与评分须披露盲法限制。

收尾：仅新增本轮findings.json并更新本状态入口。13个直接核验的关键封存/规则/Reference/数据库文件前后哈希一致，数据库只读连接均关闭；未改原数据、匿名映射、旧报告或旧READINESS，未生成用例、调用模型、代填评分、开发系统、commit/push。下一步由用户落实人员和偏离登记；如取得新的具体备份路径，再对该候选按178项封存核验，不重建历史证据。主仓库原有未提交状态继续保留。

## 12. 2026-11-13 真实AI生成验收准备（未授权调用）

**准备结论：**隔离版本、独立库、虚构需求和生成表单已就绪；真实请求尚未执行。用户选择 `deepseek-flash`，该选择不是调用授权。当前执行进程没有注入Key，账户余额、密钥有效性、模型网络可达性均未探测；后续仍需明确一次调用授权、本机凭据注入和传输层单次限额的离线自检，满足后才可放行。

本次只读检查生产源码和既有证据；按用户第3项要求，仅对全新验收库执行迁移并新增虚构Project/Version。没有修改应用代码、启动常驻服务、执行生成或操作正式实验。准备证据：[preparation.json](docs/portfolio/evidence/real-ai-preparation-20261113/preparation.json)、[迁移日志](docs/portfolio/evidence/real-ai-preparation-20261113/migration.log)、[只读表单检查](docs/portfolio/evidence/real-ai-preparation-20261113/form-readonly-check.json)。

### 已核实的版本、配置与契约

- 运行源码必须来自 `.pytest_cache/repair-20261112/integration`；249个文件全部匹配WEB-02新版 [source-manifest.json](docs/portfolio/evidence/web02-20261113/source-manifest.json)，包括steps换行比较补丁。主分支和HEAD未变，不使用主仓库旧业务源码。此前93项测试是WEB-02历史结果，本轮未重跑。
- `scripts/run_repair_demo.py` 强制Mock；`python run.py` 会开启debug。真实验收选择单进程 `create_app(显式配置)` + Flask `test_client` 调用同一Web生成路由，不用上述两种启动方式；不启用debug、reloader或常驻Web服务。本次覆盖真实Provider与Web请求处理链，不冒称新的真实浏览器验收。
- 仅白名单读取非敏感配置：主仓库 `.env` 为 `AI_ENABLED=true / AI_PROVIDER=mock / DEEPSEEK_MODEL=deepseek-v4-pro / timeout=20 / max_tokens=2000`；隔离版无 `.env`，当前进程无AI设置及Key。旧配置不能作为本次实际运行配置；未输出或修改Key、`.env`。
- Provider为DeepSeek官方HTTPS Chat Completions；SDK `max_retries=0`、`stream=false`、`response_format=json_object`、thinking明确disabled、temperature不发送。JSON模式只保证输出形式，之后仍执行原Pydantic Schema与安全校验。
- Prompt保持 `test-design-v3`。Schema顶层为 `summary/test_points/case_drafts/limitations`，禁止额外字段；points和drafts各1–20项、limitations为1–8项。测试点4字段，草稿9字段，枚举、长度、编码正则和非空字符串约束保持原样；3–6项是Prompt指导，不把它误写成Schema的硬边界。
- 入口为 `POST /ai-test-design/new`，必须携带已保存的唯一request_key和相同Project/Version/需求。Run先持久claim，成功后同key/同指纹重放原Session；失败key不重调Provider。失败页面会提供新key，因此本次禁止再次提交失败页或“重新生成”。
- 失败Run保留 `error_type/error_message/validation_summary_json` 及可用模型、token、耗时、finish_reason；Schema摘要含错误类别/字段路径/错误码，不保存失败响应全文。终态保存失败时保留running及待确认信息，不能伪造failed或自动解锁。11-10失败的具体字段仍未知。

### 已准备的独立数据

数据库：`.pytest_cache/repair-20261112/integration/instance/ai-acceptance-a699c1fcc6504d2cae2c3203c4251adf.sqlite`。最新迁移 `e8f3a7c1d902`，integrity=ok、外键违规0；1 Project、1 Version、0 Run/Session/Draft/TestCase/ReviewRecord。未调用init-db，未Seed生成样例，未复制旧库。既有数据库、Reference及封存文件的保护摘要前后一致。

请求原件：[request.json](docs/portfolio/evidence/real-ai-preparation-20261113/request.json)。题目“Demo 虚构耳机音量边界与断连行为”：初始音量5、整数范围0–10、上下限饱和、非法输入不改变原值、断连不能调音、重连保留原音量。上下文Schema、Demo范围和敏感内容检查通过。实际静态消息为5,233字符、5,767 UTF-8字节；这不是已测得的模型token数。Prompt/需求摘要已保存。未发送需求。

### 待授权的一次调用方案

1. 执行前重新核对249项源码摘要、验收库摘要及零生成计数，确认无其他使用该库的执行进程；任何差异先停下核查，不覆盖旧记录。
2. 从隔离源码启动单进程，`FLASK_SKIP_DOTENV=1`，显式指定上述数据库、`AI_PROVIDER=deepseek`、`AI_ENABLED=true`、官方端点、`DEEPSEEK_MODEL=deepseek-flash`、超时60秒、输出上限8000。Key仅通过本机隐藏输入/获准的进程内方式提供，不放入聊天、命令参数、配置文件或报告；本轮没有提供或读取该值。
3. 在该一次性执行进程的HTTP传输边界加观测和限额，离线自检通过后才放行：只准官方端点的一次Chat Completions POST，禁用重试及重定向后续请求；持久化一次执行标记，进程重启不复用许可。不发送models列表、连通性或额外负向付费探针。该临时观测器尚未在本轮编写或运行，不能声称单次守卫已经验证。
4. 用request.json向现有Web生成路由提交一次。记录请求模型、服务端返回model（缺失则记缺失，不用配置值冒充）、HTTP状态/安全请求标识、usage、finish_reason、Run ID及时间。一次本地发送登记不冒称远端独立计数证据。
5. 无论成功或失败，关闭外部网络后再做同key/同payload重放和只读页面刷新；此时任何新增模型发送尝试都被阻断并判为验收失败。读取新数据库确认计数、关联及内容，保存脱敏结果。不用新key，不再发真实请求。
6. 失败即停止并留证，不更改Prompt/Schema、不自动重试、不换模型。保存当次Run错误原件和诊断摘要；传输观测器额外保留服务端原响应中可安全保存的错误字段或校验失败正文，以及原响应字节长度/SHA-256、字段脱敏记录。请求头/认证信息始终不落盘；敏感检查不能确认正文安全时，整段省略并明确记录，只留摘要与哈希，不补造可读“原文”。当前应用自身只有摘要，不能把它称为完整原始响应。观测器异常或安全检查失败也不重发请求。

上述观测器只属于独立验收执行过程，不修改Provider、Schema或产品业务文件。若实现需要改业务代码或放宽保存安全规则，先报告范围变化。

### 价格与验收判据

用户选定请求模型 `deepseek-flash`；官方2026-11-13读取页面标示对应 `DeepSeek-V4.1-Flash-1017`，实际服务端返回版本待本次响应确认。[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)与[价格摘录](docs/portfolio/evidence/real-ai-preparation-20261113/pricing.json)：每百万token，高峰未缓存输入US$0.30、输出US$1.20；非高峰分别US$0.15/0.60。按估算6000输入token及8000输出token预算，约US$0.0114（高峰）或US$0.0057（非高峰）；不是硬费用封顶或当前余额承诺。实际费用按usage、缓存命中及执行时价格/时段核算；Schema失败也可能已产生调用费用。

| 验证项 | 成功标准或失败处理 |
|---|---|
| 真实返回 | 直接使用选定官方端点与真实Provider，保留HTTP返回、请求/返回模型及可用usage；不回退Mock。未返回、认证失败或被限流不算成功 |
| 原契约 | 原Schema及安全检查均通过；截断、非法JSON、缺字段/枚举错误保留真实失败，不自动修复输出 |
| 持久化 | 仅1条succeeded Run关联1个Session；Points按原设计存于Session.test_points_json，Drafts数量与结果一致且全pending；关闭连接后只读重查仍一致；正式TestCase和ReviewRecord均0 |
| 来源链 | Run的输入/Prompt摘要、provider/model、request_key、Session ID可追溯；每条Draft.generation_run_id关联该Run，结构化初始输出与保存内容符合原有空precondition转换契约 |
| 幂等 | 断网后相同key/输入返回原结果，Run/Session/Draft数量不增加；失败key不重调；刷新仅GET，不触发调用 |
| 异常安全 | 不留半套Session/Drafts；错误诊断可刷新查询；若终态持久化失败则保留running/未知及活动锁，停止人工核查；不记虚假成功 |

一条真实调用只能验证实际出现的成功或失败分支；其他失败、并发分支仍引用此前FakeClient/离线证据，不称为本轮全部真实覆盖。本次生成验收不包含人工接受、正式56项采集或人工质量评分。

收尾：新增独立验收库及本节链接的准备证据，更新状态入口；源代码249项前后匹配，旧库与封存文件未改，模型请求0。等待用户明确授权一次调用，并通过本机安全方式提供执行进程所需Key；本轮“继续”和模型选择均未作付费调用授权。

## 13. 2026-11-13 单次真实DeepSeek生成验收结果

用户在准备完成后明确授权最多一次真实生成，自检通过无需再次确认；该授权已消耗。本次直接核验结果为**通过**，没有第二次真实请求、自动重试、模型切换或Schema放宽。原第12节保留为调用前准备记录。

执行时间：2026-11-13 22:37:53–22:38:00（Asia/Shanghai；HTTP观测14:37:53–14:38:00 UTC）。源码仍为含WEB-02的隔离integration版；使用第12节已准备的 `ai-acceptance-a699c1fcc6504d2cae2c3203c4251adf.sqlite` 和原request.json，没有新建第二套需求或数据库。

| 验证项 | 实际结果 |
|---|---|
| 限额守卫离线自检 | 8组检查通过、真实网络请求0：第二次POST/重新arm、持久标记重启、错误目标、超时后再次调用、并发、307重定向补发、SDK 500不重试、敏感正文省略 |
| 调用与模型 | 本执行器HTTP传输发送登记1次，收到1次HTTP 200；请求及服务端返回model均为 `deepseek-flash`，finish_reason=stop。服务端没有单独返回底层版本号，不将官方别名映射冒称响应中的版本证明 |
| 参数 | 官方HTTPS端点；timeout=60、max_tokens=8000、thinking disabled、temperature不发送；SDK及HTTP transport retries=0 |
| Schema与安全 | 原Schema及安全校验通过；主控另对保存的真实响应独立执行Schema校验，响应内容与Run结构化快照一致 |
| 数据库前后 | 前：1 Project/1 Version，其余生成及审核记录0。后：Run #1 succeeded、Session #1、6 Points（Session JSON）、Draft #1–6全pending；TestCase=0、ReviewRecord=0 |
| 来源链与持久化 | Run输入/Prompt摘要与准备记录一致；Session关联Run，6条Draft的generation_run_id/session_id及9字段内容逐项匹配；关闭连接后只读回查通过；integrity=ok、外键违规0 |
| 关闭网络后的幂等与刷新 | 首次与同key重放均302且结果入口一致；Run/Session页各刷新两次均200。请求后快照与重放/刷新后快照完全相同，新增模型发送尝试0 |
| 原有成果保护 | 249项隔离源码哈希和10个准备阶段登记的旧数据库/封存/Reference/源码包哈希保持一致；未修改正式数据、匿名映射或业务代码 |

Token：输入1,334（缓存命中896、未命中438），输出1,195，总计2,529。调用处于官方非高峰时段；按准备阶段已核对的[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)计算，费用估算为 `(896×0.003 + 438×0.15 + 1195×0.6)/1,000,000 = US$0.000785388`。这是返回usage对应的价目估算，未额外查询账户余额或实扣账单。

失败项：本次验收检查无失败。未验证项：账户实际扣费、底层精确模型版本、真实浏览器交互、其他真实失败分支和人工质量评分；本次成功也不能解释11-10旧Schema失败的具体字段。质量评分及正式实验效果不由本次生成成功推导。

凭据由用户在本机PowerShell隐藏输入，仅注入一次子进程环境；执行器读取后从子进程环境移除，退出时父进程清除环境项并释放安全输入缓冲。未写入命令参数、源代码、日志、数据库或验收报告。执行过程中默认阻断网络，仅在一次性HTTP守卫内部放行；请求结束关闭内层HTTP客户端并永久关闭守卫，才进行重放与刷新。未启动常驻Web服务，已关闭本轮本机输入窗口。

证据目录：[real-ai-acceptance-20261113](docs/portfolio/evidence/real-ai-acceptance-20261113)。主要入口：

- [自检结果](docs/portfolio/evidence/real-ai-acceptance-20261113/selfcheck.json)、[执行器锁定清单](docs/portfolio/evidence/real-ai-acceptance-20261113/execution-manifest.json)、[执行前核验](docs/portfolio/evidence/real-ai-acceptance-20261113/preflight.json)。
- [单次发送占用标记](docs/portfolio/evidence/real-ai-acceptance-20261113/model-post-claim.json)、[传输结果](docs/portfolio/evidence/real-ai-acceptance-20261113/transport-after-primary.json)、[安全响应证据](docs/portfolio/evidence/real-ai-acceptance-20261113/response-evidence.json)。
- [总结果](docs/portfolio/evidence/real-ai-acceptance-20261113/result.json)、[主控独立只读复核](docs/portfolio/evidence/real-ai-acceptance-20261113/independent-verification.json)。
- [调用前数据库快照](docs/portfolio/evidence/real-ai-acceptance-20261113/database-before.json)、[调用后快照](docs/portfolio/evidence/real-ai-acceptance-20261113/database-after-primary.json)、[断网重放后快照](docs/portfolio/evidence/real-ai-acceptance-20261113/database-after-offline-replay.json)。

收尾：新增独立验收执行器、自检与响应/数据库证据；仅已准备验收库新增本次Run/Session/Points/Drafts，并更新本状态入口。未提交、推送、合并或改动无关业务代码；正式56项未运行。不得再次运行此执行器、删除占用标记或将本次授权用于额外调用。后续仅可继续只读审阅已有结果；其他付费调用须另行针对性授权。

## 14. 2026-11-24 主仓库收口与全量离线回归

### 仓库和阶段提交范围

主分支 `thesis/llm-experiment-foundation` 的 HEAD 为 `1f112e4`（2026-10-04 冻结执行器），分支上此后没有提交。已跟踪修改 16 项，未跟踪 99 项，暂存区为空。登记的 `codex/generation-submit-safety` worktree 也指向 `1f112e4`。

- 实现与回归 28 份。含 `app/` 12 份、迁移 1 份、演示脚本 1 份、`tests/` 13 份和操作说明 1 份。涵盖生成提交幂等与诊断、审核并发保护、WEB-02 换行计数修正和 Mock 演示。28 份当前哈希均匹配 [11 月 17 日验收清单](C:/Users/lipuy/Documents/audio-platform-merge-20261114-153d6e2a/verification.json)。
- 论文材料 4 份。开题 Markdown、Word、配图和 11 月 17 日技术快照，路径和进度见第 5 节。
- 项目规则与状态 2 份。建议一起提交 `AGENTS.md` 和本文件。
- 建议本轮暂留 81 份。含正式采集报告的 508 行历史追加、2 份 Web 体验报告和 `docs/portfolio/evidence/` 下的 78 份证据。相关引用指向本地留存材料。

用户已授权仅补写本状态文件，已有实现、论文材料与历史证据继续保留在工作区。[逐文件拟提交清单](C:/Users/lipuy/AppData/Local/Temp/atm-0efcf8a7/proposed-commits.json)经用户确认后再按路径暂存并本地提交。本轮汇报时 HEAD 和暂存区未变。

### 测试和 37 项复测

当前主仓库的 248 份测试输入文件（含已跟踪文件及修复白名单新增文件）按原始字节复制到全新的临时目录。使用仓库 `.venv` 中的 Python 3.14.3 和 pytest 8.4.2 执行默认完整测试集。进程使用 Mock 配置、关闭外部 AI、排除外部模型 Key、使用独立 SQLite 和临时目录。Python 网络守卫只放行本地回环连接，外连阻断自检通过。测试期间守卫记录的外连尝试为 0，真实模型请求为 0。未执行正式采集、恢复或人工评价。

**1,155 通过，0 跳过，0 失败，0 错误，退出码 0。** 耗时 632.52 秒，有 1 条既有 `datetime.utcnow()` 弃用警告。测试前后输入文件哈希一致。

| 11 月 13 日历史阻塞 | 数量与具体位置 | 11 月 24 日复测 |
| --- | --- | --- |
| Windows 拒绝创建硬链接（`os.link`，WinError 5） | 存储 13 项、执行器 13 项、集成 4 项，均卡在 `FormalStore.initialize()` | 临时文件硬链接探针通过，30 项均通过 |
| Windows 拒绝连接本地回环（`socket.connect`，WinError 10013） | 交付冒烟 7 项，目标为测试自建的 `127.0.0.1` 动态端口 | 回环连接探针通过，7 项均通过 |

历史记录定位到文件和套接字权限。两组测试使用模拟数据或测试自建服务，无需额外环境变量、真实 API Key 或预启动应用服务。历史执行环境中的准确拦截策略仍未定位。

证据：[历史逐项归因](docs/portfolio/evidence/preacceptance-20261113/REPORT.md)、[本次 pytest 日志](C:/Users/lipuy/AppData/Local/Temp/atm-0efcf8a7/pytest.log)、[本次 JUnit](C:/Users/lipuy/AppData/Local/Temp/atm-0efcf8a7/pytest.xml)、[37 项逐项结果](C:/Users/lipuy/AppData/Local/Temp/atm-0efcf8a7/historical-37-outcomes.json)、[执行摘要](C:/Users/lipuy/AppData/Local/Temp/atm-0efcf8a7/result.json)。本次运行证据位于本机临时目录。
