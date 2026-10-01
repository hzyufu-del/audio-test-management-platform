# 第一阶段开发基线实施计划

> 按用户已给定的第一阶段范围直接实施，独立检查由子代理协助，所有修改保留为未提交状态。

**目标：** 恢复可启动、数据保留、迁移一致、完整测试及质量检查通过的毕业设计开发基线。

**实施方式：** 使用当前仓库和 `.venv`，先以 SQLite backup API 保存实际数据库并核验，再通过现有 Alembic 链升级。仅修改错误示例、对应文档和经复现确认的阻断问题。

**技术栈：** Flask、Flask-SQLAlchemy、Flask-Migrate/Alembic、SQLite、pytest-cov、Ruff。

## 约束

- 不新增业务模块，不大规模重构，不删除测试，不降低 90% 覆盖率门槛。
- 不覆盖用户改动，不删除原数据库，不修改业务数据来消除异常。
- 不打印敏感配置，不自动 commit，不 push。
- Seed 验证使用隔离副本；原数据库仅执行已授权迁移。

## 执行清单

- [x] 记录 Git 分支、HEAD、工作区；检查虚拟环境、依赖和 CI 命令。
- [x] 安全解析当前 `.env`，定位实际数据库，记录表数量和行摘要，备份并验证完整性。
- [x] 复现错误示例路径，修正 `.env.example` 和 README 对应两处；使用隔离 instance 实际执行示例迁移。
- [x] 执行 `db current / heads / history / upgrade / current / check`。
- [x] 检查 AI 表、Log 新字段、外键开关、外键检查及迁移前后旧业务数据。
- [x] 启动 Flask，匿名 GET 验证指定页面及 health；无现有记录的详情在隔离副本上验证。
- [x] 在副本执行两次 `init-db`，核查数量幂等、AI 示例及人工数据保留边界。
- [x] 执行 `python -m ruff check . --no-cache` 和 CI 对应完整 pytest 覆盖率命令。
- [x] 如出现阻断 Bug，先复现并定位，再进行最小修复及回归验证（路径修正及现有 migration 恢复，无业务代码 Bug）。
- [x] 根据新 `.coverage` 和 `coverage.xml` 输出行覆盖率与模块数据。
- [x] 再次检查迁移、数据及 Git diff，保存真实基线报告，完成后停止。
