# 项目讲解与面试准备

## 1. 项目背景

这个仓库把消费电子音频产品的常见测试流程抽象成一个可运行的 Flask 项目。它解决的不是某家公司的具体流程，而是几个通用问题：怎样组织版本和用例，怎样保留执行历史，怎样从失败执行跟踪缺陷，以及怎样把自动化结果和日志分析接进同一套数据模型。

仓库中的项目名、固件版本、用例、缺陷、日志和账号都是 mock、demo 或 sample 数据。页面截图也来自本地 seed。项目不复刻公司内部系统，不包含实习期间的日志、需求、版本号或接口信息。

## 2. 核心业务闭环

手工测试主链路：

```text
Project
→ Version
→ TestCase
→ TestExecution
→ Defect
→ Dashboard
```

Project 和 Version 提供测试上下文。TestCase 记录当前定义；TestExecution 保存执行当时的用例快照；只有 failed Execution 可以创建 Defect。Dashboard 从数据库聚合通过率、结果分布和缺陷状态，不使用写死的图表数据。

自动化导入链路：

```text
JUnit XML
→ 安全解析
→ TestRun
→ TestExecution
```

`JUnitXmlParser` 负责有边界的 XML 解析，`JUnitImportService` 负责用例匹配、幂等判断和事务写入。一次报告对应一个 TestRun，报告中的用例结果写成 TestExecution。

其他能力通过明确边界接入：

- Log Analysis 接收 `.log` 或 `.txt`，在内存中完成确定性分析，只保存元数据和有上限的摘要。
- AI TestCase Review 是旁路审查。它不生成正式用例，也不自动写数据库。
- REST API V1 暴露 TestCase、TestExecution 和 Defect 的核心闭环，Web 页面仍可独立使用。

## 3. 技术设计

### 数据快照

`TestExecution.capture_test_case_snapshot()` 保存执行时的用例编号、标题、前置条件、步骤和预期结果。后续修改 TestCase 不会改写历史执行。`Defect.capture_execution_snapshot()` 同样保存环境、实际结果和执行时间。

这套设计比详情页临时 join 当前数据多占一些字段，但历史证据更可靠。对测试管理系统来说，这是有意的取舍。

### 约束与事务

SQLite 连接会执行 `PRAGMA foreign_keys=ON`。Version code、TestCase code、JUnit 报告摘要等字段有唯一约束。应用层先做可读的业务检查，数据库约束处理并发下的最后一道冲突。

写操作在 Service 或明确的路由事务中执行。捕获 `IntegrityError` 或其他数据库异常后会 rollback，响应不返回 SQL、路径和异常原文。

### JUnit 导入

解析器使用 `defusedxml`，拒绝 DTD、实体和外部引用，并限制文件大小、用例数量、嵌套深度和字段长度。导入前，所有外部 case key 都必须在目标 Version 中找到匹配 TestCase。只要有一项失败，整批不写入。

报告 bytes 的 SHA-256 摘要用于幂等判断。相同 Version 下重复导入同一报告会得到明确冲突，而不是重复生成执行记录。

### Log Analysis

`LogTextParser` 不依赖 Flask 和数据库。输入是 bytes，输出是稳定的结构化结果。它根据固定规则统计级别、判断风险、识别领域并提取有上限的关键片段。

原始日志不会落盘或进入数据库。这样做减少了演示项目处理敏感内容的风险，也避免给仓库制造日志生命周期和下载权限问题。

### AI 旁路审查

AI Review 先执行确定性规则，再调用可插拔 Provider，最后通过 Pydantic v2 严格校验结构。额外字段、非法 JSON 和不完整输出都会被拒绝。Provider 只接收字段白名单；数据库 ID、日志、凭据和 JUnit 原文不会进入提示词。

默认 Provider 是离线 mock，外部 AI 默认关闭。审查结果只在页面展示，不写回 TestCase。

### REST API

`app/blueprints/api_v1/` 处理 HTTP 和 JSON 边界，Pydantic Schema 负责字段白名单、长度、类型和枚举，三个 Workflow Service 负责查询、业务约束和事务。

状态码有明确分工：

- 400：JSON 无法解析、分页或日期参数格式错误；
- 409：唯一性或业务状态冲突；
- 415：写请求不是 `application/json`；
- 422：JSON 可解析，但字段不满足 Schema；
- 500：服务端无法安全恢复的错误，响应不泄露内部细节。

### Docker 交付

镜像基于 Python 3.12 slim，只安装运行依赖。容器由非 root 用户运行，Gunicorn 监听 5000 端口。入口脚本先执行 migration，再根据 `SEED_DEMO_DATA` 决定是否运行幂等 seed。

Compose 使用 named volume 保存 `/app/instance` 下的 SQLite 数据，并用 Python 标准库访问 `/api/v1/health`。外部 AI 在容器中默认关闭。

## 4. 测试策略

测试分层不是为了追求数量，而是把失败定位到更小范围：

- Model：字段、关系、唯一约束、快照方法和删除保护。
- Service：聚合、解析、导入、业务状态、rollback 和幂等。
- Route：表单、页面、权限跳转、错误反馈和 HTML 转义。
- API：状态码、Content-Type、分页、筛选、Location、快照和统一错误格式。
- Migration：从空数据库 upgrade、current、模型漂移，以及需要时的 downgrade/re-upgrade。
- Security：XXE、二进制日志、超大输入、未知字段、Mass Assignment 和异常信息泄露。
- Smoke：通过真实 HTTP 串起 TestCase、Execution 和 Defect，不直接操作数据库。
- Delivery：解析 Compose 和 Postman JSON，检查 Docker 非 root、entrypoint、忽略规则和文档命令。
- CI：Python 3.12 下执行依赖检查、compileall、Ruff、migration 和 coverage。

Coverage 门槛是 90%。它用来防止明显回退，不代表所有风险都已覆盖；状态机、事务和安全边界仍需要针对性断言。

## 5. 重点难点

### 1. 为什么 Execution 必须保存 TestCase 快照

测试用例会持续修改。如果 Execution 详情每次都读取当前 TestCase，历史报告会随着主数据变化，无法解释当时为什么判定 passed 或 failed。创建 Execution 时复制关键字段，可以保留执行时事实。

### 2. 为什么 Defect 只能关联 failed Execution

这是当前 V1 的业务约束：缺陷需要一条明确的失败证据。规则放在应用 Service 中，便于返回 409 和可读提示；数据库外键只保证 Execution 存在，并不判断 result。

### 3. JUnit 导入怎样保证整批 rollback

服务先完成解析、Version 范围内用例匹配和重复报告检查，再构造 TestRun 与 Execution。所有记录在同一事务中提交。任何匹配或数据库错误都会 rollback，因此不会留下半个 TestRun。

### 4. 为什么原始日志不落库

V1 只需要风险统计和复核片段。保存全文会引入敏感数据、存储生命周期、下载权限和删除策略。当前实现只保留文件元数据、SHA-256 和截断摘要，范围更适合本地作品项目。

### 5. 为什么 AI 输出不能直接写正式用例

模型输出可能不完整，也可能受到用例文本中的指令干扰。这个项目把 AI 定位为审查提示，结果先经过结构校验，再由人判断。它不修改数据库，核心 CRUD 在 AI 配置错误时仍能运行。

### 6. 400、409、415、422 怎样区分

400 表示请求语法或查询格式无法正常解释；415 表示媒体类型不支持；422 表示 JSON 已解析，但字段不合法；409 表示字段本身合法，却与现有数据或业务状态冲突。

## 6. 项目边界

当前版本没有生产级认证、多租户、分布式任务、对象存储或面向大规模并发的数据库。SQLite 和两个 Gunicorn worker 只服务于单机 demo。REST API 不应直接暴露公网。

项目不接入真实公司数据。Log 不保存原文，AI 默认离线，Postman 和 smoke 脚本只创建唯一的 sample 记录。Docker 化解决的是可重复交付，不等于生产部署方案。

## 7. 三分钟项目介绍

这个项目是我用 Flask 做的消费电子音频测试管理平台，主要目的是把我理解的测试流程落成一套能运行、能验证的系统。数据全部是 mock 和 sample，不涉及任何公司内部内容。

主流程从 Project 和 Version 开始。一个 Version 下维护 TestCase，执行后生成 TestExecution，失败执行可以关联 Defect，Dashboard 再从数据库聚合质量数据。这里我比较看重历史一致性，所以 Execution 会保存 TestCase 快照，Defect 也会保存执行环境和实际结果。后面即使用例被编辑，历史执行和缺陷证据不会变化。

自动化部分支持 JUnit XML 导入。我把 XML 解析和数据库写入拆开：解析器使用 defusedxml，并限制文件大小、节点数量和字段长度；Service 先检查目标 Version 中的用例是否全部匹配，再用报告 SHA-256 做幂等判断。整批记录在一个事务里提交，失败就 rollback。

日志分析没有使用大模型。它按固定规则统计 error、warning 等级，识别音频、连接和电源领域，只保存摘要，不保存原始日志。AI 功能也不是生成用例，而是对已有 TestCase 做旁路质量审查。默认使用离线 mock，输出必须通过 Pydantic 校验，而且不会写回数据库。

REST API 覆盖 TestCase、Execution 和 Defect 闭环，明确区分 400、409、415 和 422。测试包括 Model、Service、Route、API、Migration、安全输入和 rollback，CI 有 90% coverage 门槛。

交付方面，我补了非 root Docker 镜像、自动 migration 和可控 demo seed，还提供 Python、PowerShell smoke 以及 Postman Collection。面试演示时，我会先展示 Dashboard 和 JUnit 导入，再用 smoke 脚本证明 API 闭环。这个项目的边界也很清楚：它是单机求职 demo，不把 SQLite、无认证 API 或同步任务包装成生产方案。

## 8. 高频追问

### 1. 为什么选择 Flask

项目规模适合应用工厂和 Blueprint。Flask 的约束少，我可以清楚展示 Route、Service、Model 和扩展初始化，而不是把业务藏在框架自动行为里。

### 2. 为什么使用 SQLite

它便于本地演示和自动化测试，部署成本低。代价是写并发和运维能力有限，所以项目明确限定为单机 demo。

### 3. SQLite 外键默认不一定开启，项目怎么处理

`app/extensions.py` 在连接事件中执行 `PRAGMA foreign_keys=ON`。测试和 migration 也会验证外键行为。

### 4. 快照和普通外键有什么区别

外键指向当前对象，快照保存过去的事实。Execution 既保留 `test_case_id`，也保存执行当时的用例内容。

### 5. 为什么不用级联删除

执行和缺陷属于历史记录。当前路由在删除 Project、Version 或 TestCase 前检查下游数据，提示用户先处理依赖，避免无意删除证据。

### 6. JUnit 报告重复导入怎么处理

服务计算报告 bytes 的 SHA-256，并结合目标 Version 检查唯一性。重复报告返回冲突，不会生成第二个 TestRun。

### 7. XML 安全只靠 defusedxml 吗

不是。defusedxml 负责阻止危险 XML 特性，解析器还限制总大小、嵌套深度、用例数量和字段长度。数据库写入在完整校验之后发生。

### 8. 数据库提交失败会发生什么

Service 捕获数据库异常并 rollback。API 返回统一、安全的错误，不包含原始 IntegrityError、SQL 或本地路径。

### 9. 为什么 Log Analysis 不用 AI

当前目标是可重复的基础分析。固定规则更容易解释、测试和复现，也不会把可能敏感的日志发送到外部服务。

### 10. AI Review 如何防止脏数据进入系统

它不写数据库。输入使用字段白名单，输出通过 Pydantic `extra="forbid"` 校验。非法配置或 Provider 失败只会关闭旁路能力。

### 11. REST API 为什么不用统一返回 200

调用方需要区分解析错误、校验错误、资源冲突和服务端异常。正确状态码能让 smoke、Postman 和其他客户端采取不同处理方式。

### 12. 为什么业务规则放在 Service

Web 页面和 REST API 都需要相同约束。Service 让路由只处理协议和展示，也便于直接测试事务与状态变化。

### 13. Docker 启动为什么先跑 migration

新 volume 没有表结构。entrypoint 先 upgrade 到 migration head，再根据开关 seed，保证首次启动和已有 volume 使用同一流程。

### 14. `init-db` 每次容器启动都执行会重复吗

默认会执行，但 seed 按稳定 code、marker 或摘要查询后更新/创建，因此重复运行不会重复插入同一批 demo 数据。也可以设置 `SEED_DEMO_DATA=false` 跳过。

### 15. 为什么容器不用 root

应用只需要读取代码和写入 `/app/instance`。使用专用用户可以减少容器进程拥有的权限，named volume 的目录也提前配置了所有权。

### 16. 为什么用 Gunicorn，不直接用 Flask 开发服务器

Flask 开发服务器用于本机调试。容器需要稳定的进程模型和明确的 bind 参数，所以运行依赖中加入 Gunicorn，本地启动方式不变。

### 17. smoke 脚本和 pytest API 测试有什么区别

pytest 在测试应用和临时数据库中覆盖边界条件；smoke 脚本连接一个已经运行的服务，验证容器、路由、序列化和数据库迁移能组成完整链路。

### 18. 如果继续迭代，最先补什么

先讨论认证和部署环境，而不是继续加 CRUD。没有明确威胁模型前，不会临时拼一个 JWT；如果要面向多人使用，还需要换数据库并补权限、审计和备份方案。
