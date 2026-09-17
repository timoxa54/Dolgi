"""Пути, адреса сайта БГПУ и работа с файлом .env."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key

# ----------------------------------------------------------------------
# Пути проекта
# ----------------------------------------------------------------------

if getattr(sys, "frozen", False):
    # Приложение собрано в exe: .env и data/ лежат рядом с exe.
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
DEBTS_FILE = DATA_DIR / "debts.json"
SCHEDULE_FILE = DATA_DIR / "schedule.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

ENV_FILE = BASE_DIR / ".env"

# ----------------------------------------------------------------------
# Сайт БГПУ
# ----------------------------------------------------------------------

SITE_URL = "https://asu.bspu.ru/"
APP_URL = "https://asu.bspu.ru/WebApp/"
ZACHETKA_URL = APP_URL + "#/EducationalActivity/ZachBook"
SCHEDULE_LIST_URL = APP_URL + "#/Rasp/List"
TEACHER_URL_TEMPLATE = APP_URL + "#/Rasp/Teacher/{teacher_id}"
GROUP_URL_TEMPLATE = APP_URL + "#/Rasp/Group/{group_id}"

# ----------------------------------------------------------------------
# Переменные окружения
# ----------------------------------------------------------------------

ENV_LOGIN = "BSPU_LOGIN"
ENV_PASSWORD = "BSPU_PASSWORD"


def load_env() -> None:
    """Загружает .env в переменные окружения процесса."""
    load_dotenv(ENV_FILE)


def get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default) or default


def get_credentials() -> tuple[str, str]:
    """Возвращает (логин, пароль) из .env."""
    return get_env(ENV_LOGIN), get_env(ENV_PASSWORD)


def save_credentials(login: str, password: str) -> None:
    """Сохраняет логин и пароль в .env, не трогая остальные строки файла."""
    ENV_FILE.touch(exist_ok=True)

    set_key(str(ENV_FILE), ENV_LOGIN, login)
    set_key(str(ENV_FILE), ENV_PASSWORD, password)

    os.environ[ENV_LOGIN] = login
    os.environ[ENV_PASSWORD] = password


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
