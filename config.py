import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = (BASE_DIR / "instance" / "audio_test_platform.sqlite").as_posix()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "sample-dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URI",
        f"sqlite:///{DEFAULT_SQLITE_PATH}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
