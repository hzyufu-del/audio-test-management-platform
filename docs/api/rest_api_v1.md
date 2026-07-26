# REST API V1

## 1. API 定位

REST API V1 用于求职作品展示和本地 demo，覆盖核心测试闭环：

```text
TestCase -> TestExecution -> Defect
```

接口强调严格 JSON 校验、明确 HTTP 状态码、历史快照、事务回滚和可重复的 pytest 自动化测试。示例只使用 mock / demo / sample 数据。

## 2. Base URL

本地默认地址：

```text
http://127.0.0.1:5000/api/v1
```

健康检查：

```http
GET /api/v1/health
```

```json
{
  "status": "ok",
  "service": "audio-test-management-platform",
  "api_version": "v1"
}
```

## 3. Content-Type

所有 `POST` 和 `PATCH` 请求必须使用：

```http
Content-Type: application/json
```

不接受表单、XML 或其他媒体类型。JSON 根节点必须是 object；未知字段和由服务端管理的字段会被拒绝。

## 4. 成功响应

列表接口：

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 0,
    "pages": 0
  }
}
```

详情、创建和更新接口直接返回资源对象。创建成功返回 `201 Created`，并通过 `Location` 响应头给出新资源的详情 URL。

## 5. 统一错误响应

```json
{
  "error": {
    "code": "validation_error",
    "message": "请求参数校验失败。",
    "details": {
      "title": [
        "字段不能为空。"
      ]
    }
  }
}
```

没有字段级详情时，`details` 为 `{}`：

```json
{
  "error": {
    "code": "not_found",
    "message": "资源不存在。",
    "details": {}
  }
}
```

响应不会返回 traceback、SQL、数据库路径、异常类名、API Key 或内部配置。

## 6. HTTP 状态码

| 状态码 | 使用场景 |
| --- | --- |
| `200 OK` | 查询或 PATCH 更新成功 |
| `201 Created` | 创建 TestCase、TestExecution 或 Defect 成功 |
| `400 Bad Request` | malformed JSON、JSON 根节点不是 object、非法分页或日期查询参数 |
| `404 Not Found` | 资源或关联资源不存在 |
| `409 Conflict` | 唯一约束冲突、非 failed 执行创建 Defect、Defect 状态冲突 |
| `415 Unsupported Media Type` | 写接口不是 `application/json` |
| `422 Unprocessable Entity` | JSON 可解析，但字段、枚举、长度或白名单校验失败 |
| `500 Internal Server Error` | 无法安全恢复的数据库或服务端错误 |

## 7. 分页规则

列表接口支持：

- `page`：默认 `1`，必须是正整数；
- `page_size`：默认 `20`，范围为 `1..100`。

空结果页仍返回真实的 `total` 和 `pages`。所有列表都有稳定的二级排序。

## 8. TestCase API

### `GET /api/v1/test-cases`

支持：

- `page`
- `page_size`
- `project_id`
- `version_id`
- `module`
- `priority`
- `status`
- `keyword`，搜索 `code` 和 `title`

示例响应项：

```json
{
  "id": 1,
  "version_id": 1,
  "version_code": "FW_DEMO_ALPHA",
  "project_id": 1,
  "project_code": "MOCK-AUDIO-01",
  "code": "TC_AUDIO_001",
  "title": "Sample Audio Playback Checklist",
  "module": "Audio",
  "priority": "P1",
  "case_type": "checklist",
  "status": "active",
  "created_at": "2026-07-26T10:00:00Z",
  "updated_at": "2026-07-26T10:00:00Z"
}
```

### `GET /api/v1/test-cases/{id}`

详情额外返回 `precondition`、`steps` 和 `expected_result`。

### `POST /api/v1/test-cases`

```json
{
  "version_id": 1,
  "code": "TC_API_AUDIO_001",
  "title": "Verify sample audio reconnect",
  "module": "Audio",
  "priority": "P1",
  "case_type": "checklist",
  "precondition": "Use mock device state.",
  "steps": "Disconnect and reconnect the sample device.",
  "expected_result": "The sample device reconnects successfully.",
  "status": "draft"
}
```

规则：

- Version 必须存在；
- 必填字符串去除首尾空白后不得为空；
- `priority`、`case_type` 和 `status` 使用严格白名单；
- 同一 Version 下 `code` 唯一，不同 Version 可复用同一 `code`；
- 客户端不能设置 ID、时间戳或其他未知字段。

## 9. TestExecution API

### `GET /api/v1/executions`

支持：

- `page`
- `page_size`
- `project_id`
- `version_id`
- `test_case_id`
- `result`
- `tester`
- `environment`
- `executed_from`
- `executed_to`

日期参数必须是包含时区的 ISO-8601 值，且 `executed_from` 不能晚于 `executed_to`。

### `GET /api/v1/executions/{id}`

详情返回：

- TestCase 历史快照；
- `actual_result`、`notes`、`duration_seconds`；
- `external_case_key` 和 `test_run_id`；
- 关联 Defect 摘要。

API 使用执行记录中的快照字段，不动态读取当前 TestCase 文本。

### `POST /api/v1/executions`

```json
{
  "test_case_id": 1,
  "result": "failed",
  "actual_result": "Sample device did not reconnect.",
  "tester": "API Demo Tester",
  "environment": "Android Sample Env",
  "executed_at": "2026-07-26T10:30:00+00:00",
  "notes": "Created through REST API V1."
}
```

规则：

- TestCase 必须存在；
- `result` 为 `passed`、`failed`、`blocked` 或 `skipped`；
- `failed` 必须填写 `actual_result`；
- `blocked` 必须填写 `actual_result` 或 `notes`；
- `executed_at` 可省略；提供时必须包含时区；
- 创建的是手工记录，因此 `test_run_id`、`external_case_key` 和 `duration_seconds` 均为 `null`；
- 快照与执行记录在同一事务中写入，客户端不能提交快照字段。

## 10. Defect API

### `GET /api/v1/defects`

支持：

- `page`
- `page_size`
- `project_id`
- `version_id`
- `test_execution_id`
- `status`
- `severity`
- `priority`
- `component`
- `assignee`
- `keyword`，搜索 `code`、`title` 和 `description`

### `GET /api/v1/defects/{id}`

详情返回描述、复现步骤、观察结果、解决信息、Execution 快照，以及关联 Execution/TestCase 摘要。

### `POST /api/v1/defects`

```json
{
  "test_execution_id": 1,
  "code": "DEF_API_001",
  "title": "Sample reconnect defect",
  "description": "Reconnect failed in the sample environment.",
  "component": "Bluetooth",
  "severity": "major",
  "priority": "P1",
  "status": "open",
  "reproduction_steps": "Run the sample reconnect scenario.",
  "observed_result": "The mock device remained disconnected.",
  "reporter": "API Demo Tester",
  "assignee": null
}
```

规则：

- TestExecution 必须存在且结果必须为 `failed`；
- `code` 全局唯一；
- 必填字符串和枚举值严格校验；
- Execution 快照与 Defect 在同一事务中写入；
- 客户端不能提交快照字段。

### `PATCH /api/v1/defects/{id}`

只允许：

- `status`
- `severity`
- `priority`
- `assignee`
- `resolution`
- `resolution_note`

工作流约束：

- `fixed` / `closed` 必须有 `resolution`；
- `open` 不能携带 `resolution`；
- `rejected` 必须有 `resolution_note`；
- 空 object、未知字段、身份字段和快照字段返回 `422`；
- 工作流状态冲突返回 `409`。

## 11. curl 示例

健康检查：

```bash
curl http://127.0.0.1:5000/api/v1/health
```

创建 TestCase：

```bash
curl -X POST http://127.0.0.1:5000/api/v1/test-cases \
  -H "Content-Type: application/json" \
  -d '{"version_id":1,"code":"TC_API_AUDIO_001","title":"Sample API TestCase","module":"Audio","priority":"P1","case_type":"checklist","steps":"Run sample steps.","expected_result":"Sample result is recorded.","status":"draft"}'
```

创建 failed Execution：

```bash
curl -X POST http://127.0.0.1:5000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{"test_case_id":1,"result":"failed","actual_result":"Sample reconnect failed.","tester":"API Demo Tester","environment":"Android Sample Env"}'
```

更新 Defect：

```bash
curl -X PATCH http://127.0.0.1:5000/api/v1/defects/1 \
  -H "Content-Type: application/json" \
  -d '{"status":"fixed","resolution":"firmware_update","resolution_note":"Sample fix verified."}'
```

## 12. PowerShell 示例

```powershell
$baseUrl = "http://127.0.0.1:5000/api/v1"

Invoke-RestMethod -Method Get -Uri "$baseUrl/health"

$testCaseBody = @{
    version_id = 1
    code = "TC_API_AUDIO_001"
    title = "Sample API TestCase"
    module = "Audio"
    priority = "P1"
    case_type = "checklist"
    steps = "Run sample steps."
    expected_result = "Sample result is recorded."
    status = "draft"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/test-cases" `
    -ContentType "application/json" `
    -Body $testCaseBody
```

## 13. 安全和认证边界

- REST API V1 是求职展示和本地 demo API；
- 当前没有生产级 API 认证；
- 不应直接部署到公网；
- 后续可扩展基于 Token 的权限控制；
- 现有 Flask 登录页面和 REST API 当前互不作为生产安全边界；
- 本阶段未实现 JWT、OAuth、API Key、RBAC 或删除接口；
- 数据库异常会 rollback，响应不会泄露异常原文；
- 文档和测试只包含 mock / demo / sample 数据。

## 14. 常见错误示例

非 JSON 写请求：

```json
{
  "error": {
    "code": "unsupported_media_type",
    "message": "请求必须使用 application/json。",
    "details": {}
  }
}
```

非法分页：

```json
{
  "error": {
    "code": "bad_request",
    "message": "查询参数格式无效。",
    "details": {
      "page": [
        "page 必须是正整数。"
      ]
    }
  }
}
```

重复 TestCase code：

```json
{
  "error": {
    "code": "conflict",
    "message": "同一版本下测试用例编号已存在。",
    "details": {}
  }
}
```
