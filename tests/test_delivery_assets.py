import importlib.util
import io
import json
import re
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit

import yaml
import pytest


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path):
    path = ROOT / relative_path
    assert path.is_file(), f"{relative_path} is missing"
    return path.read_text(encoding="utf-8")


def load_smoke_module():
    path = ROOT / "scripts" / "api_smoke.py"
    assert path.is_file(), "scripts/api_smoke.py is missing"
    spec = importlib.util.spec_from_file_location("api_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_powershell():
    for executable in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        resolved = shutil.which(executable)
        if resolved:
            return resolved
    return None


def run_powershell_smoke(base_url, timeout_sec=2):
    executable = find_powershell()
    if executable is None:
        pytest.skip("PowerShell is not available")

    return subprocess.run(
        [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts" / "api_smoke.ps1"),
            "-BaseUrl",
            base_url,
            "-TimeoutSec",
            str(timeout_sec),
        ],
        capture_output=True,
        text=True,
        timeout=max(timeout_sec + 10, 15),
        check=False,
    )


def test_runtime_and_development_dependencies_are_separated():
    runtime = read_text("requirements.txt").lower()
    development = read_text("requirements-dev.txt").lower()

    assert "gunicorn" in runtime
    assert "pytest" not in runtime
    assert "ruff" not in runtime
    assert "pytest" in development
    assert "pytest-cov" in development
    assert "ruff" in development
    assert "pyyaml" in development


def test_dockerfile_uses_python_312_and_a_non_root_runtime_user():
    dockerfile = read_text("Dockerfile")
    lines = [
        line.strip()
        for line in dockerfile.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert lines[0].startswith("FROM python:3.12-")
    assert not lines[0].endswith(":latest")
    assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile
    assert "PYTHONUNBUFFERED=1" in dockerfile
    assert "EXPOSE 5000" in dockerfile
    assert "COPY .env" not in dockerfile
    assert "requirements-dev.txt" not in dockerfile
    assert any(line.startswith("USER ") and line != "USER root" for line in lines)
    assert '"run:app"' in dockerfile
    assert "gunicorn" in dockerfile


def test_compose_configures_persistent_demo_service_and_healthcheck():
    compose = yaml.safe_load(read_text("compose.yaml"))
    web = compose["services"]["web"]
    environment = web["environment"]
    healthcheck = " ".join(web["healthcheck"]["test"])

    assert web["build"]["context"] == "."
    assert web["ports"] == ["127.0.0.1:5000:5000"]
    assert "5000:5000" not in web["ports"]
    assert "0.0.0.0:5000:5000" not in web["ports"]
    assert environment["AI_ENABLED"] == "false"
    assert environment["AI_PROVIDER"] == "mock"
    assert environment["DATABASE_URI"] == (
        "sqlite:////app/instance/audio_test_platform.sqlite"
    )
    assert "SECRET_KEY" in environment
    assert "SEED_DEMO_DATA" in environment
    assert web["volumes"] == ["app_instance:/app/instance"]
    assert "/api/v1/health" in healthcheck
    assert "curl" not in healthcheck
    assert web["restart"] == "unless-stopped"
    assert "app_instance" in compose["volumes"]


def test_entrypoint_migrates_seeds_conditionally_and_executes_command():
    entrypoint_path = ROOT / "docker" / "entrypoint.sh"
    content = read_text("docker/entrypoint.sh")

    assert entrypoint_path.read_bytes().find(b"\r\n") == -1
    assert content.startswith("#!/bin/sh\nset -eu\n")
    assert "flask --app run.py db upgrade" in content
    assert "SEED_DEMO_DATA" in content
    assert "flask --app run.py init-db" in content
    assert 'exec "$@"' in content
    assert "SECRET_KEY" not in content
    assert "DATABASE_URI" not in content


def test_dockerignore_excludes_local_and_sensitive_artifacts():
    patterns = {
        line.strip()
        for line in read_text(".dockerignore").splitlines()
        if line.strip() and not line.startswith("#")
    }
    required = {
        ".git",
        ".github",
        ".venv",
        "venv",
        "__pycache__",
        "*.pyc",
        ".pytest_cache",
        ".ruff_cache",
        ".coverage",
        "coverage.xml",
        "htmlcov",
        "instance",
        "*.sqlite",
        "*.sqlite3",
        ".env",
        ".env.*",
        "!.env.example",
        "docs/images",
    }

    assert required <= patterns
    assert "migrations" not in patterns
    assert "app/templates" not in patterns
    assert "app/static" not in patterns
    assert "docs/api" not in patterns


def flatten_postman_items(items):
    for item in items:
        if "item" in item:
            yield from flatten_postman_items(item["item"])
        else:
            yield item


def test_postman_collection_is_v21_complete_and_credential_free():
    path = (
        ROOT
        / "docs"
        / "api"
        / "audio_test_platform_rest_api_v1.postman_collection.json"
    )
    assert path.is_file()
    raw = path.read_text(encoding="utf-8")
    collection = json.loads(raw)
    items = list(flatten_postman_items(collection["item"]))
    names = {item["name"] for item in items}
    variables = {item["key"] for item in collection["variable"]}

    assert collection["info"]["schema"].endswith(
        "/collection/v2.1.0/collection.json"
    )
    assert {
        "Health",
        "List TestCases",
        "Create TestCase",
        "Get TestCase",
        "Create failed Execution",
        "Get Execution",
        "Create Defect",
        "Patch Defect",
        "Get Defect",
        "415 Unsupported Media Type",
        "422 Validation Error",
        "409 Duplicate TestCase",
    } <= names
    assert {
        "base_url",
        "version_id",
        "test_case_id",
        "execution_id",
        "defect_id",
    } <= variables
    assert "access_token" not in raw.lower()
    assert "secret_key" not in raw.lower()
    assert "deepseek_api_key" not in raw.lower()

    for item in items:
        headers = {
            header["key"].lower()
            for header in item["request"].get("header", [])
        }
        assert "authorization" not in headers
        assert "cookie" not in headers

    scripts = "\n".join(
        line
        for item in items
        for event in item.get("event", [])
        for line in event["script"].get("exec", [])
    )
    assert "pm.response.code" in scripts
    assert "Content-Type" in scripts
    assert "Location" in scripts
    assert 'collectionVariables.set("test_case_id"' in scripts
    assert 'collectionVariables.set("execution_id"' in scripts
    assert 'collectionVariables.set("defect_id"' in scripts


def test_powershell_smoke_script_exposes_demo_only_http_workflow():
    content = read_text("scripts/api_smoke.ps1")

    assert '[string]$BaseUrl = "http://127.0.0.1:5000"' in content
    assert "[int]$TimeoutSec = 15" in content
    assert "Invoke-WebRequest" in content
    assert "Invoke-RestMethod" not in content
    assert re.search(r"\[int\]\$response\.StatusCode", content)
    assert re.search(r"\$actualStatus\s+-ne\s+\$ExpectedStatus", content)
    assert "TimeoutSec = $TimeoutSec" in content
    assert content.count("-ExpectedStatus 201") == 3
    assert "-ExpectedStatus 415" in content
    assert "-ExpectedStatus 422" in content
    assert "-ExpectedStatus 409" in content
    assert "-RequireLocation" in content
    assert "Get-Random" in content
    assert '$apiUrl = "$rootUrl/api/v1"' in content
    assert '"$apiUrl/health"' in content
    assert '"$apiUrl/test-cases' in content
    assert '"$apiUrl/executions"' in content
    assert '"$apiUrl/defects' in content
    assert "exit 1" in content
    assert "C:\\Users\\" not in content


def test_readme_delivery_commands_match_repository_assets():
    readme = read_text("README.md")

    assert "## Docker 快速启动" in readme
    assert "docker compose up --build" in readme
    assert "docker compose down -v" in readme
    assert "python scripts/api_smoke.py" in readme
    assert (
        "powershell -ExecutionPolicy Bypass -File scripts/api_smoke.ps1"
        in readme
    )
    assert (
        "docs/api/audio_test_platform_rest_api_v1.postman_collection.json"
        in readme
    )
    assert "http://127.0.0.1:5000/api/v1/health" in readme
    assert "当前 API 没有生产级认证" in readme
    assert "默认关闭外部 AI Provider" in readme
    assert "Compose 默认将服务绑定到 `127.0.0.1:5000`" in readme
    assert "pytest 自动验证" in readme
    assert "本地人工实际验证" in readme
    assert "当前工作流不执行 Docker build" in readme
    assert "SECRET_KEY=replace-with-local-secret" in readme
    assert "SECRET_KEY=sample-local-dev-secret-key" not in readme


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        return


@contextmanager
def demo_api_server(scenario="success"):
    requests = []
    created_test_case_codes = set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format_, *args):
            return

        def send_json(self, status, payload, headers=None):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            with suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(body)

        def read_json(self):
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self):
            path = urlsplit(self.path).path
            requests.append(("GET", path))
            if path == "/api/v1/health":
                if scenario == "timeout":
                    time.sleep(0.2)
                if scenario == "non_json":
                    body = b"temporary gateway response"
                    self.send_response(502)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_json(
                    200,
                    {
                        "status": "ok",
                        "service": "audio-test-management-platform",
                        "api_version": "v1",
                    },
                )
                return
            if path == "/api/v1/test-cases":
                self.send_json(
                    200,
                    {
                        "items": [
                            {
                                "id": 7,
                                "version_id": 9,
                                "code": "TC_DEMO_EXISTING",
                            }
                        ],
                        "pagination": {
                            "page": 1,
                            "page_size": 1,
                            "total": 1,
                            "pages": 1,
                        },
                    },
                )
                return
            resources = {
                "/api/v1/test-cases/101": {
                    "id": 101,
                    "version_id": 9,
                    "code": "TC_SMOKE_SAMPLE",
                },
                "/api/v1/executions/202": {
                    "id": 202,
                    "test_case_id": 101,
                    "result": "failed",
                },
                "/api/v1/defects/303": {
                    "id": 303,
                    "test_execution_id": 202,
                    "status": "fixed",
                },
            }
            if path in resources:
                self.send_json(200, resources[path])
                return
            self.send_json(
                404,
                {
                    "error": {
                        "code": "not_found",
                        "message": "资源不存在。",
                        "details": {},
                    }
                },
            )

        def do_POST(self):
            path = urlsplit(self.path).path
            requests.append(("POST", path))
            if (
                path == "/api/v1/test-cases"
                and self.headers.get_content_type() != "application/json"
            ):
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                self.send_json(
                    415,
                    {
                        "error": {
                            "code": "unsupported_media_type",
                            "message": "请求必须使用 application/json。",
                            "details": {},
                        }
                    },
                )
                return

            payload = self.read_json()
            if path == "/api/v1/test-cases":
                if not payload:
                    self.send_json(
                        422,
                        {
                            "error": {
                                "code": "validation_error",
                                "message": "请求参数校验失败。",
                                "details": {},
                            }
                        },
                    )
                    return
                if scenario == "conflict":
                    self.send_json(
                        409,
                        {
                            "error": {
                                "code": "conflict",
                                "message": "示例资源冲突。",
                                "details": {},
                            }
                        },
                    )
                    return
                if payload["code"] in created_test_case_codes:
                    self.send_json(
                        409,
                        {
                            "error": {
                                "code": "conflict",
                                "message": "示例资源冲突。",
                                "details": {},
                            }
                        },
                    )
                    return
                created_test_case_codes.add(payload["code"])
                self.send_json(
                    200 if scenario == "wrong_create_status" else 201,
                    {
                        "id": 101,
                        "version_id": payload["version_id"],
                        "code": payload["code"],
                    },
                    (
                        {}
                        if scenario == "missing_location"
                        else {"Location": "/api/v1/test-cases/101"}
                    ),
                )
                return
            if path == "/api/v1/executions":
                self.send_json(
                    201,
                    {
                        "id": 202,
                        "test_case_id": payload["test_case_id"],
                        "result": "failed",
                    },
                    {"Location": "/api/v1/executions/202"},
                )
                return
            if path == "/api/v1/defects":
                self.send_json(
                    201,
                    {
                        "id": 303,
                        "test_execution_id": payload["test_execution_id"],
                        "code": payload["code"],
                        "status": "open",
                    },
                    {"Location": "/api/v1/defects/303"},
                )
                return
            self.send_json(404, {})

        def do_PATCH(self):
            path = urlsplit(self.path).path
            requests.append(("PATCH", path))
            self.read_json()
            if path == "/api/v1/defects/303":
                self.send_json(
                    200,
                    {
                        "id": 303,
                        "test_execution_id": 202,
                        "status": "fixed",
                        "resolution": "sample_smoke_fix",
                    },
                )
                return
            self.send_json(404, {})

    server = QuietThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_python_smoke_parser_has_safe_local_defaults():
    module = load_smoke_module()
    args = module.build_parser().parse_args([])

    assert args.base_url == "http://127.0.0.1:5000"
    assert args.timeout > 0


def test_python_smoke_runs_complete_http_only_workflow():
    module = load_smoke_module()
    output = io.StringIO()

    with demo_api_server() as (base_url, requests):
        result = module.run_smoke(base_url, timeout=1, stream=output)

    assert result == {
        "version_id": 9,
        "test_case_id": 101,
        "execution_id": 202,
        "defect_id": 303,
    }
    assert ("POST", "/api/v1/test-cases") in requests
    assert ("POST", "/api/v1/executions") in requests
    assert ("POST", "/api/v1/defects") in requests
    assert ("PATCH", "/api/v1/defects/303") in requests
    assert output.getvalue().count("[200]") >= 5
    assert output.getvalue().count("[201]") == 3


def test_powershell_smoke_runs_complete_http_workflow_when_available():
    with demo_api_server() as (base_url, requests):
        result = run_powershell_smoke(base_url)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert output.count("[201]") == 3
    assert "[415]" in output
    assert "[422]" in output
    assert "[409]" in output
    assert ("POST", "/api/v1/test-cases") in requests
    assert ("POST", "/api/v1/executions") in requests
    assert ("POST", "/api/v1/defects") in requests
    assert ("PATCH", "/api/v1/defects/303") in requests


def test_powershell_smoke_rejects_wrong_success_status_when_available():
    with demo_api_server("wrong_create_status") as (base_url, _):
        result = run_powershell_smoke(base_url)

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "expected status 201 but received 200" in output
    assert "workflow passed" not in output
    assert "stack trace" not in output.lower()
    assert "CategoryInfo" not in output
    assert "FullyQualifiedErrorId" not in output
    assert not re.search(r"api_smoke\.ps1:\d+ char:", output)


def test_powershell_smoke_rejects_missing_location_when_available():
    with demo_api_server("missing_location") as (base_url, _):
        result = run_powershell_smoke(base_url)

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "returned status 201 without Location" in output
    assert "workflow passed" not in output


def test_powershell_smoke_ast_parses_when_available():
    executable = find_powershell()
    if executable is None:
        pytest.skip("PowerShell is not available")

    script_path = str(ROOT / "scripts" / "api_smoke.ps1").replace("'", "''")
    command = (
        "$tokens = $null; $errors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{script_path}', [ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { "
        "$errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_python_smoke_reports_unavailable_service_without_traceback(
    capsys, monkeypatch
):
    module = load_smoke_module()

    def refuse_connection(*args, **kwargs):
        raise URLError(ConnectionRefusedError())

    monkeypatch.setattr(module, "urlopen", refuse_connection)

    exit_code = module.main(
        ["--base-url", "http://127.0.0.1:1", "--timeout", "0.1"]
    )
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "unavailable" in output.lower()
    assert "traceback" not in output.lower()


def test_python_smoke_reports_non_json_error_without_response_body(capsys):
    module = load_smoke_module()
    with demo_api_server("non_json") as (base_url, _):
        exit_code = module.main(
            ["--base-url", base_url, "--timeout", "1"]
        )
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "non-json" in output.lower()
    assert "temporary gateway response" not in output
    assert "traceback" not in output.lower()


def test_python_smoke_reports_timeout_without_traceback(capsys):
    module = load_smoke_module()
    with demo_api_server("timeout") as (base_url, _):
        exit_code = module.main(
            ["--base-url", base_url, "--timeout", "0.05"]
        )
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "timed out" in output.lower()
    assert "traceback" not in output.lower()


def test_python_smoke_parses_api_conflict_safely(capsys):
    module = load_smoke_module()
    with demo_api_server("conflict") as (base_url, _):
        exit_code = module.main(
            ["--base-url", base_url, "--timeout", "1"]
        )
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "409" in output
    assert "conflict" in output
    assert "traceback" not in output.lower()
