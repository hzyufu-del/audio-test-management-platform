import os
from pathlib import Path
import subprocess
import sys

import pytest

import config


def load_ai_config(values=None):
    return config.load_ai_config({} if values is None else values)


def load_runtime_ai_config(values=None):
    assert hasattr(config, "load_runtime_ai_config")
    return config.load_runtime_ai_config({} if values is None else values)


def test_ai_config_defaults_are_disabled_and_offline():
    assert hasattr(config, "load_ai_config")

    settings = load_ai_config()

    assert settings == {
        "AI_ENABLED": False,
        "AI_PROVIDER": "mock",
        "DEEPSEEK_API_KEY": "",
        "DEEPSEEK_MODEL": "",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "DEEPSEEK_THINKING_ENABLED": False,
        "AI_REQUEST_TIMEOUT_SECONDS": 20,
        "AI_MAX_INPUT_CHARS": 12000,
        "AI_MAX_OUTPUT_TOKENS": 2000,
    }


def test_runtime_ai_config_returns_valid_strict_settings():
    settings = load_runtime_ai_config(
        {
            "AI_ENABLED": "true",
            "AI_PROVIDER": "deepseek",
            "DEEPSEEK_MODEL": "demo-model",
            "AI_REQUEST_TIMEOUT_SECONDS": "30",
        }
    )

    assert settings["AI_ENABLED"] is True
    assert settings["AI_PROVIDER"] == "deepseek"
    assert settings["DEEPSEEK_MODEL"] == "demo-model"
    assert settings["AI_REQUEST_TIMEOUT_SECONDS"] == 30
    assert settings["AI_CONFIG_ERROR"] == ""


@pytest.mark.parametrize(
    ("values", "setting_name", "raw_value"),
    [
        (
            {"AI_PROVIDER": "invalid-provider-sentinel"},
            "AI_PROVIDER",
            "invalid-provider-sentinel",
        ),
        (
            {"AI_REQUEST_TIMEOUT_SECONDS": "invalid-timeout-sentinel"},
            "AI_REQUEST_TIMEOUT_SECONDS",
            "invalid-timeout-sentinel",
        ),
    ],
)
def test_runtime_ai_config_safely_disables_invalid_settings(
    values,
    setting_name,
    raw_value,
):
    settings = load_runtime_ai_config(values)

    assert settings["AI_ENABLED"] is False
    assert settings["AI_PROVIDER"] == "mock"
    assert settings["DEEPSEEK_API_KEY"] == ""
    assert settings["DEEPSEEK_MODEL"] == ""
    assert settings["DEEPSEEK_BASE_URL"] == "https://api.deepseek.com"
    assert settings["DEEPSEEK_THINKING_ENABLED"] is False
    assert settings["AI_REQUEST_TIMEOUT_SECONDS"] == 20
    assert settings["AI_MAX_INPUT_CHARS"] == 12000
    assert settings["AI_MAX_OUTPUT_TOKENS"] == 2000
    assert setting_name in settings["AI_CONFIG_ERROR"]
    assert raw_value not in settings["AI_CONFIG_ERROR"]
    assert "DEEPSEEK_API_KEY" not in settings["AI_CONFIG_ERROR"]


def test_invalid_ai_environment_does_not_block_flask_app_creation(tmp_path):
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("AI_", "DEEPSEEK_"))
    }
    environment.update(
        {
            "AI_PROVIDER": "invalid-provider-sentinel",
            "DATABASE_URI": (
                f"sqlite:///{(tmp_path / 'runtime-config.sqlite').as_posix()}"
            ),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app import create_app; "
                "app = create_app(); "
                "assert app.config['AI_ENABLED'] is False; "
                "assert app.config['AI_PROVIDER'] == 'mock'; "
                "assert app.config['AI_CONFIG_ERROR']; "
                "print('APP_CREATE_OK')"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "APP_CREATE_OK"
    assert "invalid-provider-sentinel" not in result.stdout
    assert "invalid-provider-sentinel" not in result.stderr


def test_deepseek_thinking_defaults_to_disabled():
    assert load_ai_config()["DEEPSEEK_THINKING_ENABLED"] is False


def test_deepseek_thinking_accepts_supported_boolean_values():
    values = {
        "true": True,
        "1": True,
        "yes": True,
        "on": True,
        "false": False,
        "0": False,
        "no": False,
        "off": False,
    }

    for raw_value, expected in values.items():
        settings = load_ai_config({"DEEPSEEK_THINKING_ENABLED": raw_value})
        assert settings["DEEPSEEK_THINKING_ENABLED"] is expected


def test_deepseek_thinking_rejects_unknown_boolean_value():
    with pytest.raises(config.AIConfigError, match="DEEPSEEK_THINKING_ENABLED"):
        load_ai_config({"DEEPSEEK_THINKING_ENABLED": "sometimes"})


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        (" YES ", True),
    ],
)
def test_ai_enabled_accepts_supported_boolean_values(raw_value, expected):
    assert load_ai_config({"AI_ENABLED": raw_value})["AI_ENABLED"] is expected


def test_ai_enabled_rejects_unknown_boolean_value():
    with pytest.raises(config.AIConfigError, match="AI_ENABLED"):
        load_ai_config({"AI_ENABLED": "sometimes"})


@pytest.mark.parametrize("provider", ["mock", "deepseek"])
def test_ai_provider_accepts_supported_values(provider):
    assert load_ai_config({"AI_PROVIDER": provider})["AI_PROVIDER"] == provider


def test_ai_provider_rejects_unknown_value():
    with pytest.raises(config.AIConfigError, match="AI_PROVIDER"):
        load_ai_config({"AI_PROVIDER": "other"})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AI_REQUEST_TIMEOUT_SECONDS", "0"),
        ("AI_REQUEST_TIMEOUT_SECONDS", "121"),
        ("AI_REQUEST_TIMEOUT_SECONDS", "not-a-number"),
        ("AI_MAX_INPUT_CHARS", "999"),
        ("AI_MAX_INPUT_CHARS", "50001"),
        ("AI_MAX_OUTPUT_TOKENS", "99"),
        ("AI_MAX_OUTPUT_TOKENS", "8001"),
    ],
)
def test_ai_numeric_config_rejects_invalid_values(name, value):
    with pytest.raises(config.AIConfigError, match=name):
        load_ai_config({name: value})


def test_ai_environment_values_override_defaults_and_are_stripped():
    settings = load_ai_config(
        {
            "AI_ENABLED": "on",
            "AI_PROVIDER": " deepseek ",
            "DEEPSEEK_API_KEY": " local-only-key ",
            "DEEPSEEK_MODEL": " current-model ",
            "DEEPSEEK_BASE_URL": " https://api.deepseek.com ",
            "DEEPSEEK_THINKING_ENABLED": "yes",
            "AI_REQUEST_TIMEOUT_SECONDS": "30",
            "AI_MAX_INPUT_CHARS": "24000",
            "AI_MAX_OUTPUT_TOKENS": "3000",
        }
    )

    assert settings == {
        "AI_ENABLED": True,
        "AI_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "local-only-key",
        "DEEPSEEK_MODEL": "current-model",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "DEEPSEEK_THINKING_ENABLED": True,
        "AI_REQUEST_TIMEOUT_SECONDS": 30,
        "AI_MAX_INPUT_CHARS": 24000,
        "AI_MAX_OUTPUT_TOKENS": 3000,
    }
