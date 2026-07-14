import os
from pathlib import Path
from typing import Mapping


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = (BASE_DIR / "instance" / "audio_test_platform.sqlite").as_posix()

AI_PROVIDER_VALUES = frozenset({"mock", "deepseek"})
TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
FALSE_VALUES = frozenset({"false", "0", "no", "off"})

SAFE_AI_SETTINGS = {
    "AI_ENABLED": False,
    "AI_PROVIDER": "mock",
    "DEEPSEEK_API_KEY": "",
    "DEEPSEEK_MODEL": "",
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_THINKING_ENABLED": False,
    "AI_REQUEST_TIMEOUT_SECONDS": 20,
    "AI_MAX_INPUT_CHARS": 12000,
    "AI_MAX_OUTPUT_TOKENS": 2000,
    "AI_CONFIG_ERROR": "",
}


class AIConfigError(ValueError):
    """Raised when an AI environment setting cannot be validated safely."""


def _get_text(source, name, default):
    value = source.get(name, default)
    return str(value).strip()


def _parse_bool(source, name, default):
    raw_value = _get_text(source, name, "true" if default else "false").lower()
    if raw_value in TRUE_VALUES:
        return True
    if raw_value in FALSE_VALUES:
        return False
    raise AIConfigError(
        f"{name} must be one of true/false, 1/0, yes/no, or on/off."
    )


def _parse_bounded_int(source, name, default, minimum, maximum):
    raw_value = _get_text(source, name, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise AIConfigError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise AIConfigError(
            f"{name} must be between {minimum} and {maximum}."
        )
    return value


def load_ai_config(environ: Mapping[str, object] | None = None):
    source = os.environ if environ is None else environ
    provider = _get_text(source, "AI_PROVIDER", "mock").lower()
    if provider not in AI_PROVIDER_VALUES:
        raise AIConfigError("AI_PROVIDER must be either mock or deepseek.")

    return {
        "AI_ENABLED": _parse_bool(source, "AI_ENABLED", False),
        "AI_PROVIDER": provider,
        "DEEPSEEK_API_KEY": _get_text(source, "DEEPSEEK_API_KEY", ""),
        "DEEPSEEK_MODEL": _get_text(source, "DEEPSEEK_MODEL", ""),
        "DEEPSEEK_BASE_URL": _get_text(
            source,
            "DEEPSEEK_BASE_URL",
            "https://api.deepseek.com",
        ),
        "DEEPSEEK_THINKING_ENABLED": _parse_bool(
            source,
            "DEEPSEEK_THINKING_ENABLED",
            False,
        ),
        "AI_REQUEST_TIMEOUT_SECONDS": _parse_bounded_int(
            source,
            "AI_REQUEST_TIMEOUT_SECONDS",
            20,
            1,
            120,
        ),
        "AI_MAX_INPUT_CHARS": _parse_bounded_int(
            source,
            "AI_MAX_INPUT_CHARS",
            12000,
            1000,
            50000,
        ),
        "AI_MAX_OUTPUT_TOKENS": _parse_bounded_int(
            source,
            "AI_MAX_OUTPUT_TOKENS",
            2000,
            100,
            8000,
        ),
    }


def load_runtime_ai_config(environ: Mapping[str, object] | None = None):
    try:
        return {**load_ai_config(environ), "AI_CONFIG_ERROR": ""}
    except AIConfigError as exc:
        return {**SAFE_AI_SETTINGS, "AI_CONFIG_ERROR": str(exc)}


AI_SETTINGS = load_runtime_ai_config()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "sample-dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URI",
        f"sqlite:///{DEFAULT_SQLITE_PATH}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AI_ENABLED = AI_SETTINGS["AI_ENABLED"]
    AI_PROVIDER = AI_SETTINGS["AI_PROVIDER"]
    DEEPSEEK_API_KEY = AI_SETTINGS["DEEPSEEK_API_KEY"]
    DEEPSEEK_MODEL = AI_SETTINGS["DEEPSEEK_MODEL"]
    DEEPSEEK_BASE_URL = AI_SETTINGS["DEEPSEEK_BASE_URL"]
    DEEPSEEK_THINKING_ENABLED = AI_SETTINGS["DEEPSEEK_THINKING_ENABLED"]
    AI_REQUEST_TIMEOUT_SECONDS = AI_SETTINGS["AI_REQUEST_TIMEOUT_SECONDS"]
    AI_MAX_INPUT_CHARS = AI_SETTINGS["AI_MAX_INPUT_CHARS"]
    AI_MAX_OUTPUT_TOKENS = AI_SETTINGS["AI_MAX_OUTPUT_TOKENS"]
    AI_CONFIG_ERROR = AI_SETTINGS["AI_CONFIG_ERROR"]
