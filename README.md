# audio-test-management-platform

中文名：消费电子音频产品测试管理与自动化辅助平台

这是一个用于求职作品集和 GitHub 展示的企业级软件测试项目。项目模拟消费电子音频产品测试团队的日常管理流程，覆盖测试项目、版本、Checklist 用例、执行记录、缺陷记录、模拟 Log 文件和统计看板。

> 数据边界：本项目只使用 mock / demo / sample 数据，不包含任何真实公司项目名、真实版本号、真实 Log、真实测试用例、真实缺陷编号或内部截图。

## 当前已完成功能

- Dashboard V1 测试质量决策页：基于数据库聚合 Project、Version、有效 TestCase、执行结果、通过率、失败率和当前缺陷风险；支持 Project、Version、7 天 / 30 天 / 全部时间筛选，并提供趋势图、版本质量表和需关注项。
- 登录 / 注册页面框架：提供基础账号入口，后续可扩展权限。
- Project 项目管理：支持列表、新增、详情、编辑、删除、基础表单校验和重复编码校验。
- Version 版本管理：支持列表、新增、详情、编辑、删除，并关联所属 Project；同一 Project 下版本编码唯一。
- TestCase 测试用例管理：支持列表、新增、详情、编辑、删除，并关联所属 Version；同一 Version 下用例编号唯一。
- TestExecution 执行记录管理：支持列表、新增、详情、编辑、删除，并关联所属 TestCase；failed 结果要求填写实际结果，创建时自动保存用例内容快照。
- TestRun 自动化运行管理：支持 TestRun 列表、详情和 JUnit XML Web 导入；导入过程使用安全 Parser、严格 TestCase 匹配、报告哈希幂等和单事务写入。
- Defect 缺陷管理：支持列表、新增、详情、编辑和删除；缺陷只能来源于 failed TestExecution，并自动保存执行环境、实际结果和执行时间快照。
- 数据一致性：TestCase 仅通过 Version 获取 Project，TestExecution 仅通过 TestCase 获取 Version 和 Project，避免重复父级字段产生矛盾。
- 历史可追溯：执行记录保存用例编号、标题、前置条件、步骤和预期结果快照；后续修改用例不会覆盖已有执行历史。
- SQLite 外键约束：开发环境和 pytest 环境均启用 `PRAGMA foreign_keys=ON`，数据库会拒绝孤儿关联记录。
- 删除保护：已有 Version 的 Project 不允许直接删除；已有 TestCase 的 Version 不允许直接删除；已有 TestExecution 的 TestCase 不允许直接删除，避免误删重要测试记录。
- 模拟 Log 管理页面框架：列表页和占位按钮。
- pytest：覆盖 Dashboard 聚合与筛选、Project / Version / TestCase / TestExecution / Defect CRUD、表单校验、快照、外键和关联删除保护。

## 技术栈

- Python 3.12
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-Login
- Bootstrap 5
- Chart.js 4.4.7
- SQLite
- pytest
- pytest-cov
- Ruff

## 目录结构

```text
audio-test-management-platform/
├── app/
│   ├── __init__.py
│   ├── extensions.py
│   ├── models.py
│   ├── services/
│   │   └── dashboard_service.py
│   ├── blueprints/
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── projects/
│   │   ├── versions/
│   │   ├── testcases/
│   │   ├── executions/
│   │   ├── defects/
│   │   └── logs/
│   ├── templates/
│   └── static/
├── migrations/
├── tests/
├── config.py
├── run.py
├── requirements.txt
├── README.md
├── .env.example
└── .gitignore
```

## 目录和文件说明

- `app/__init__.py`：Flask 应用工厂，负责创建 app、初始化扩展、注册蓝图和 CLI 命令。
- `app/extensions.py`：集中放置 `db`、`migrate`、`login_manager`，避免循环导入。
- `app/models.py`：基础数据模型，包括 `User`、`Project`、`Version`、`TestCase`、`TestExecution`、`Defect`、`LogFile`。
- `app/services/dashboard_service.py`：集中构建 Dashboard 查询范围、聚合执行与缺陷指标、生成趋势和版本质量数据。
- `app/services/junit_xml_parser.py`：安全解析 pytest JUnit XML，输出与数据库无关的标准化结果。
- `app/services/junit_import_service.py`：严格匹配目标 Version 下的 TestCase，并在单事务中创建 TestRun 与 TestExecution。
- `app/blueprints/`：按业务模块拆分路由，便于后续逐步扩展 CRUD。
- `app/templates/`：Jinja2 页面模板，包含基础布局、Dashboard、登录注册，以及 Project / Version / TestCase / TestExecution / Defect 页面。
- `app/static/`：静态资源，目前包含基础 CSS。
- `migrations/`：Flask-Migrate 迁移目录，后续数据库结构变更放在这里。
- `tests/`：pytest 测试目录，覆盖首页访问、核心 CRUD、表单校验和删除保护。
- `config.py`：项目配置，默认使用 SQLite，本地可通过 `.env` 覆盖。
- `run.py`：本地启动入口。
- `requirements.txt`：Python 依赖清单。
- `.env.example`：本地环境变量模板。
- `.gitignore`：忽略虚拟环境、数据库文件、缓存等本地文件。

## 本地运行

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
flask --app run.py db upgrade
flask --app run.py init-db
flask --app run.py run --debug
```

访问地址：

```text
http://127.0.0.1:5000
```

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 代码质量与 CI

安装本地开发和 CI 依赖：

```powershell
pip install -r requirements-dev.txt
```

运行 Ruff 基础代码检查：

```powershell
ruff check .
```

运行测试并生成终端缺失行报告和 `coverage.xml`：

```powershell
pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=90
```

GitHub Actions 会在 push 和 Pull Request 时检查依赖、Python 编译、Ruff、空 SQLite 数据库迁移、模型迁移一致性、pytest 和 coverage 门槛。

## 数据库说明

当前已使用 Flask-Migrate 管理数据库结构。Project、Version、TestCase、TestExecution、Defect 已接入数据库 CRUD；`init-db` 仅用于插入本地 mock/demo/sample 示例数据。

创建或更新本地 SQLite 表结构：

```powershell
flask --app run.py db upgrade
```

插入本地 mock/demo/sample 示例数据：

```powershell
flask --app run.py init-db
```

可公开展示的 JUnit XML 示例位于 `docs/samples/junit_demo_results.xml`，其中用例编码与 `init-db` 的 Demo Firmware Alpha 数据匹配。

后续如果修改模型，可以使用 Flask-Migrate 生成迁移：

```powershell
flask --app run.py db migrate -m "describe model change"
flask --app run.py db upgrade
```

如果本地 `instance/audio_test_platform.sqlite` 曾经由早期 `init-db` 或 `db.create_all()` 创建，可以删除该本地 demo 数据库后重新执行：

```powershell
flask --app run.py db upgrade
flask --app run.py init-db
```

## 后续扩展建议

- 为 Defect 增加受控状态流转和变更历史。
- 为 Log 增加完整 CRUD。
- 增加搜索、筛选、分页和导入导出。
- 为缺陷和 Log 增加关联关系。
- 增加角色权限，例如 tester、lead、viewer。
- 增加更多 pytest 覆盖路由、模型和表单提交。
