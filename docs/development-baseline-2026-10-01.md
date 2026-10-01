# 毕业设计第一阶段开发基线报告

暂定题目：《基于大语言模型的智能测试用例生成与管理系统设计与实现》

验证日期：2026-10-01（Asia/Shanghai）。本报告全部结果来自本轮真实执行；没有新增业务功能、删除或跳过测试、降低覆盖率门槛、自动提交或推送。

## 1. Git、环境与修改文件

- 起始分支：`docs/final-portfolio-sync`。
- 起始及最终 HEAD：`b623a05c2af5d0f4d616f99ac297b3fe80e48eba`。
- 起始工作区干净，没有用户未提交修改。
- 使用仓库 `.venv\Scripts\python.exe`，Python **3.14.3**；CI 配置为 Python **3.12**，本轮未在 3.12 上重跑。
- 实际安装：Flask 3.1.3、Flask-SQLAlchemy 3.1.1、SQLAlchemy 2.0.51、Flask-Migrate 4.1.0、Alembic 1.18.5、pytest 8.4.2、pytest-cov 7.1.0、coverage 7.15.0、Ruff 0.15.21。`pip check` 通过。
- 当前 `.env` 已检查且保留，未输出 API Key、Secret Key 或其他敏感值；其文件摘要在示例验证前后不变。
- 当前未配置 `DATABASE_URI`，实际使用 `config.py` 的绝对路径默认值。Flask `instance_path` 是仓库的 `instance` 目录。

| 文件 | 修改原因 |
|---|---|
| `.env.example` | 将 SQLite URI 改为 `sqlite:///audio_test_platform.sqlite`，消除重复 `instance/instance` 路径。 |
| `README.md` | 同步启动示例并说明 Flask-SQLAlchemy 相对路径解析规则，Compose 绝对路径保持原配置。 |
| `docs/superpowers/plans/2026-10-01-development-baseline.md` | 记录第一阶段范围、数据保护和执行检查清单。 |
| `docs/development-baseline-2026-10-01.md` | 保存本轮真实基线结果及验证边界。 |

本地数据库、备份、日志、隔离副本、`.coverage`、`coverage.xml` 和 `.codex` 验证脚本均被现有 Git ignore 规则排除，不提交数据库或敏感配置。

### 示例配置实际验证

原 `sqlite:///instance/audio_test_platform.sqlite` 的 engine 路径解析到 `<repo>/instance/instance/audio_test_platform.sqlite`。修正后解析到 `<repo>/instance/audio_test_platform.sqlite`。

在隔离目录复制 `app/`、`migrations/`、`config.py`、`run.py`，把修正后的 `.env.example` 原样复制为 `.env`，使用现有虚拟环境实际执行 `flask --app run.py db upgrade/current/check`，三条命令均 exit 0。数据库实际创建在隔离目录的 `instance/audio_test_platform.sqlite`，没有嵌套 `instance/instance`；revision 为 head，模型差异为空。原 `.env` 未改动。

## 2. 数据库结果

- 原文件：`C:\Users\lipuy\Documents\audio-test-management-platform\instance\audio_test_platform.sqlite`。
- 原文件大小：**118,784 bytes**；迁移后：**163,840 bytes**。
- 迁移前备份：`C:\Users\lipuy\Documents\audio-test-management-platform\instance\backups\audio_test_platform-pre-baseline-20261001-171556.sqlite`，**118,784 bytes**。
- 使用 SQLite backup API；备份存在，表数据摘要与原库一致，`integrity_check = ok`；备份已确认被 Git 忽略。
- 原 revision：`02e4b0712fc4`。
- 现有 migration 链：`02e4b0712fc4 → 7c9d0e4f6a21 → c5d8a9e4f2b1`。
- 最终 revision：**`c5d8a9e4f2b1 (head)`**。
- `test_design_session`、`test_case_draft` 已存在。
- `log_file` 已有 `file_size_bytes`、`sha256`、`analysis_status`、`risk_level`、`total_lines`、`critical_count`、`error_count`、`warning_count`、`info_count`、`analysis_summary`。
- 应用连接 `PRAGMA foreign_keys = 1`；`PRAGMA foreign_key_check = []`；`PRAGMA integrity_check = ok`。
- 未手写 SQL 绕过 Alembic，未重建或删除原数据库，未新增或修改历史 migration。

| 模型 | 迁移前 | 迁移后 |
|---|---:|---:|
| Project | 2 | 2 |
| Version | 4 | 4 |
| TestCase | 4 | 4 |
| TestExecution | 15 | 15 |
| Defect | 4 | 4 |
| TestRun | 1 | 1 |
| LogFile | 1 | 1 |
| TestDesignSession | 表不存在 | 0 |
| TestCaseDraft | 表不存在 | 0 |

User 也保持 1 条。所有旧业务记录数量、ID 和迁移后仍保留的旧字段均逐行比对一致。历史 Log migration 按其原设计移除 `category`、`storage_path`，这些旧字段的值保存在迁移前备份；不能把这描述为“所有字段完全不变”。该 migration 为旧日志回填 `legacy_metadata` 及空分析统计；没有伪造原日志分析结果。原库的 AI 表为空属于正常初始状态，本轮没有向原库添加演示数据。

迁移后的原数据库 SHA-256 为 `372a11796ae07303d823e23484512e7b9d691de42f8246a775e1834d0a115001`；隔离 Seed 检查前后原文件及逻辑数据摘要不变。

## 3. 页面验证

实际启动 Flask：`python -m flask --app run.py run --no-debugger --no-reload --host 127.0.0.1 --port 5017`。使用真实 HTTP GET 验证以下地址均返回 **200**，HTML 页面含标题，health JSON 内容正确。

| 页面 | 地址 | 结果 |
|---|---|---|
| Dashboard | `/`、`/?range=all` | 正常 |
| Project 列表/详情 | `/projects/`、`/projects/1` | 正常 |
| Version 列表/详情 | `/versions/`、`/versions/1` | 正常 |
| TestCase 列表/详情 | `/test-cases/`、`/test-cases/1` | 正常 |
| TestExecution 列表/详情 | `/test-executions/`、`/test-executions/1` | 正常 |
| Defect 列表/详情 | `/defects/`、`/defects/1` | 正常 |
| TestRun 列表/详情 | `/test-runs/`、`/test-runs/1` | 正常 |
| Log Analysis 列表/旧日志详情 | `/logs/`、`/logs/1` | 正常 |
| AI Session 列表/设计表单 | `/ai-test-design/`、`/ai-test-design/new` | 正常 |
| API health | `/api/v1/health` | 正常，`status=ok` |
| AI 示例会话详情 | `/ai-test-design/2`，隔离 Seed 副本 | Flask test client 返回 200，含三个草稿编号 |
| 已完成日志分析详情 | `/logs/1`，隔离 Seed 副本 | Flask test client 返回 200 |

共 **19 个原库 HTTP 地址**以及 **2 个隔离副本详情**。Dashboard、Log 旧日志详情、AI 新建表单另经内置浏览器截图和页面内容检查；AI 列表空状态经浏览器内容检查。未新增 Playwright/Selenium 依赖或测试模块。

- 异常：本轮最终检查未发现页面阻断错误。
- 未验证：原库无 AI 会话，未向原库写入会话以验证详情；详情已在隔离副本验证。未对全部页面的浏览器交互、所有视口和所有图表进行穷尽验证，也未发起真实 DeepSeek 请求。
- Health 不查询数据库，因此数据库可用性由业务页面、schema 和外键检查另行证明。

### Demo Seed

真实命令为 `flask --app run.py init-db`，不存在 `seed-demo` 命令。使用升级后的 SQLite backup 副本，并显式覆盖 app 的数据库 URI，实际 CLI runner 执行两次 `init-db`，均 exit 0。

- 第二次没有新增/删除记录，各表数量及全部 ID 稳定。
- 创建 1 个 mock AI 示例会话、3 个 pending 草稿，覆盖 normal/negative/boundary，没有自动接受为正式 TestCase，没有调用外部模型。
- 11 条具有独立标识的人工测试记录（含已接受/已拒绝 AI 草稿）所有列均保留；12 条原有非 Seed 记录所有列均保留。
- 副本外键检查为空、完整性检查通过；原库内容不变。
- Seed 是**数量和 ID 幂等**，不是完整内容幂等：它刷新匹配的 Demo 用例、日志、执行时间及缺陷快照。同名 Demo 标识上的人工编辑可能被覆盖。这是现有行为边界，本轮没有修改 Seed 架构，也没有在原库执行 Seed。

## 4. 完整测试结果

使用与 CI 一致的参数，未使用 append、skip 或旧 coverage 数据：

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90
```

```text
collected: 622
passed: 622
failed: 0
skipped: 0
xfailed: 0
xpassed: 0
warnings: 181
duration: 78.51s
exit code: 0
```

Warnings 如实保留，主要包含 `datetime.utcnow()` 弃用和 SQLite 未关闭连接的 `ResourceWarning`。181 是 pytest 最终 summary 的计数，原始输出还包含 coverage/GC 阶段直接打印的连接资源警告。没有过滤或隐藏警告。无失败测试需要归类或修复。

## 5. 新覆盖率

本轮 pytest-cov 重新生成 `.coverage` 和 `coverage.xml`（2026-10-01 17:21，Asia/Shanghai），XML 与总表语句计数交叉核验一致。

```text
statements: 3354
missed: 201
covered: 3153
coverage: 94.01% (line coverage)
threshold: 90% — passed
```

下表从本轮 XML 汇总；是行覆盖率，不是 branch coverage。分组不重复计算文件：auth/API 为各自 blueprint；AI 为 blueprint、test_design provider/quality/schema/security 和 service；JUnit 为 parser/import service；Log 为 blueprint 和 analysis service；core CRUD 为 Project/Version/TestCase/Execution/Defect blueprint 及相应业务 service。

| 模块 | Statements | Missed | 行覆盖率 |
|---|---:|---:|---:|
| auth | 54 | 39 | 27.78% |
| AI Test Design | 514 | 29 | 94.36% |
| API | 285 | 2 | 99.30% |
| JUnit | 360 | 8 | 97.78% |
| Log Analysis | 210 | 7 | 96.67% |
| core CRUD | 792 | 90 | 88.64% |

auth `routes.py` 单文件覆盖率是 25%；全项目通过门槛不代表每个模块达到 90%。本阶段不新增与运行恢复无关的测试扩展。

## 6. 工具验证

```text
Ruff: python -m ruff check . --no-cache → All checks passed!, exit 0
pip check: No broken requirements found.
compileall: app/tests/migrations 通过
db current: c5d8a9e4f2b1 (head), exit 0
db check: No new upgrade operations detected., exit 0
```

升级前已执行 current/heads/history，升级后及最终再次执行 current/check。模型与迁移一致，不需要新 migration。

## 7. 本轮修复的阻断问题

1. **示例启动数据库路径错误** → Flask-SQLAlchemy 相对 SQLite 文件名以 `instance_path` 为基准，示例重复加入 `instance/` → 修正 `.env.example` 和 README → engine 路径复现与隔离复制示例后的真实 upgrade/current/check 全部验证。
2. **Log Analysis OperationalError** → 原库停留在 `02e4b0712fc4`，缺少 `file_size_bytes` 等字段 → 备份后执行现有 Alembic Log migration → 前置复现、schema 检查、原库 HTTP 列表/详情与隔离 completed 日志详情均通过。
3. **AI Session OperationalError** → 原库没有 `test_design_session`、`test_case_draft` → 执行现有 AI migration → 前置复现、AI 表检查、原库 HTTP 列表/表单、隔离示例详情及完整 pytest 均通过。

未发现需要修改应用业务代码的额外阻断 Bug。

## 8. 剩余问题与验证边界

- **无本阶段阻断项。**
- 本轮仍有 181 条 pytest summary warnings，以及原始输出中的资源警告；未扩大范围改写测试 fixture/时间逻辑。
- auth 及部分 CRUD 路由覆盖率偏低，已如实记录；全项目 90% 门槛通过。
- Seed 会覆盖匹配的 Demo 内容；在含人工编辑的数据库重复执行时需要理解这个已有边界，本轮只在副本执行。
- 本轮环境是 Windows/Python 3.14.3，未重新执行 Linux/Python 3.12 CI 或 Docker 构建；Docker/Compose 配置仅检查路径，未改动。
- 原日志仅为旧元数据，迁移不会凭空恢复原始日志内容；旧 `category/storage_path` 值在原库备份中。

## 9. 毕业设计基线判断

```text
应用可启动：是，真实 Flask HTTP 已验证；验证进程完成后停止
数据库已到最新：是，c5d8a9e4f2b1 = head
核心管理流程可用：是，现有列表/详情及完整 CRUD/API/JUnit 测试通过
AI Test Design 页面可用：是，列表/表单和隔离详情通过
Log Analysis 页面可用：是，原库旧日志与隔离 completed 日志详情通过
完整 pytest：622 passed，0 failed
Coverage ≥ 90%：是，94.01% 行覆盖率
Ruff：通过
Migration check：通过，无模型差异
Git 工作区状态：2 个已跟踪文件修改，2 个新增文档；未 commit/push
```

**当前已经达到本阶段要求的“毕业设计开发基线”。** 本阶段完成后停止，没有继续实现下一阶段功能。

本地详细执行证据保存在 Git 忽略的 `instance/baseline-evidence/`，包括 `before.json`、`after.json`、`before-pages.json`、`http-pages.json`、`replica-pages.json`、`example-config.json`、`seed.json`、`coverage-summary.json`、`pytest.txt`、`ruff.txt`、`upgrade.txt` 和最终迁移命令输出。
