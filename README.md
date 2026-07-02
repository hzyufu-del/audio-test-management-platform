# audio-test-management-platform

中文名：消费电子音频产品测试管理与自动化辅助平台

这是一个用于求职作品集和 GitHub 展示的企业级软件测试项目骨架。项目模拟消费电子音频产品测试团队的日常管理流程，覆盖测试项目、版本、Checklist 用例、执行记录、缺陷记录、模拟 Log 文件和统计看板。

> 数据边界：本项目只使用 mock / demo / sample 数据，不包含任何真实公司项目名、真实版本号、真实 Log、真实测试用例、真实缺陷编号或内部截图。

## 第一版功能

- Dashboard 首页：展示项目数、用例数、已执行数、缺陷数等模拟统计卡片。
- 登录 / 注册页面框架：提供基础账号入口，后续可扩展权限。
- 项目管理页面框架：列表页和占位按钮。
- 版本管理页面框架：列表页和占位按钮。
- Checklist 用例管理页面框架：列表页和占位按钮。
- 执行记录页面框架：列表页和占位按钮。
- 缺陷管理页面框架：列表页和占位按钮。
- 模拟 Log 管理页面框架：列表页和占位按钮。
- 基础 pytest：验证首页可以访问。

## 技术栈

- Python
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-Login
- Bootstrap 5
- SQLite
- pytest

## 目录结构

```text
audio-test-management-platform/
├── app/
│   ├── __init__.py
│   ├── extensions.py
│   ├── models.py
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
- `app/blueprints/`：按业务模块拆分路由，便于后续逐步扩展 CRUD。
- `app/templates/`：Jinja2 页面模板，包含基础布局、Dashboard、登录注册和通用列表页。
- `app/static/`：静态资源，目前包含基础 CSS。
- `migrations/`：Flask-Migrate 迁移目录，后续数据库结构变更放在这里。
- `tests/`：pytest 测试目录，目前包含首页可访问测试。
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

## 数据库说明

当前第一版以骨架和页面框架为主，页面列表使用 mock 数据。模型已经提前放在 `app/models.py` 中，后续可以逐步把页面数据改为数据库查询。

创建或更新本地 SQLite 表结构：

```powershell
flask --app run.py db upgrade
```

插入本地 mock/demo/sample 示例数据：

```powershell
flask --app run.py init-db
```

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

- 为项目、版本、用例、执行记录、缺陷、Log 增加增删改查。
- 增加搜索、筛选、分页和导入导出。
- 将 Dashboard 统计从 mock 数据切换为数据库聚合查询。
- 为缺陷和 Log 增加关联关系。
- 增加角色权限，例如 tester、lead、viewer。
- 增加更多 pytest 覆盖路由、模型和表单提交。
