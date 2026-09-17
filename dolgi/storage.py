"""Чтение и запись данных приложения: долги, расписания, настройки."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import config
from .models import DEFAULT_DEBT_TYPES, Debt, Lesson, ScheduleEntry


class StorageError(Exception):
    """Ошибка чтения или записи данных."""


def _read_json(path: Path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise StorageError(
            f"Файл {path.name} повреждён и не может быть прочитан:\n{error}"
        ) from error


def _write_json(path: Path, data) -> None:
    config.ensure_dirs()

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ----------------------------------------------------------------------
# Долги
# ----------------------------------------------------------------------


def load_debts() -> list[Debt]:
    data = _read_json(config.DEBTS_FILE, [])

    if isinstance(data, dict):
        data = data.get("debts", [])

    return [Debt.from_dict(item) for item in data]


def save_debts(debts: list[Debt]) -> None:
    _write_json(
        config.DEBTS_FILE,
        {
            "debts": [debt.to_dict() for debt in debts],
        },
    )


def merge_debts(
    old_debts: list[Debt],
    new_debts: list[Debt],
) -> list[Debt]:
    """Объединяет заново загруженные долги с уже отредактированными.

    Если долг уже был в списке (совпал id), сохраняются правки
    пользователя, но подтягиваются свежие данные оценки и часов.
    """
    old_by_id = {debt.id: debt for debt in old_debts}

    merged: list[Debt] = []

    for new_debt in new_debts:
        old_debt = old_by_id.get(new_debt.id)

        if old_debt is None:
            merged.append(new_debt)
            continue

        old_debt.teacher = old_debt.teacher or new_debt.teacher
        old_debt.subject = old_debt.subject or new_debt.subject
        old_debt.grade = new_debt.grade
        old_debt.hours = new_debt.hours or old_debt.hours
        old_debt.credits = new_debt.credits or old_debt.credits

        merged.append(old_debt)

    # Долги, которых больше нет в зачётке, но которые пользователь
    # добавил вручную, сохраняем.
    new_ids = {debt.id for debt in new_debts}

    for old_debt in old_debts:
        if old_debt.id in new_ids:
            continue

        if old_debt.source == "manual":
            merged.append(old_debt)

    return merged


# ----------------------------------------------------------------------
# Расписания
# ----------------------------------------------------------------------


def schedule_from_dict(data: dict) -> dict[str, ScheduleEntry]:
    """Разбирает словарь вида {владелец: данные} в расписания."""
    if not isinstance(data, dict):
        return {}

    result: dict[str, ScheduleEntry] = {}

    for key, value in data.items():
        if not isinstance(value, dict):
            continue

        value = dict(value)
        value.setdefault("owner", key)
        result[key] = ScheduleEntry.from_dict(value)

    return result


def load_schedule() -> dict[str, ScheduleEntry]:
    return schedule_from_dict(_read_json(config.SCHEDULE_FILE, {}))


def save_schedule(schedule: dict[str, ScheduleEntry]) -> None:
    _write_json(
        config.SCHEDULE_FILE,
        {
            key: entry.to_dict()
            for key, entry in schedule.items()
        },
    )


def schedule_lessons(
    schedule: dict[str, ScheduleEntry],
    owner: Optional[str] = None,
) -> list[Lesson]:
    """Все занятия расписания (или одного владельца)."""
    if owner is not None:
        entry = schedule.get(owner)
        return list(entry.lessons) if entry else []

    lessons: list[Lesson] = []

    for entry in schedule.values():
        lessons.extend(entry.lessons)

    return lessons


# ----------------------------------------------------------------------
# Настройки
# ----------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "headless": True,
    "remember_password": True,
    "group": "",
    "course_filter": "all",
    # Долги, удалённые из учёта вручную: не возвращаются при повторном парсинге.
    "deleted_ids": [],
    # Какие типы долгов учитывать (тумблеры в интерфейсе).
    "debt_types": dict(DEFAULT_DEBT_TYPES),
}


def load_settings() -> dict:
    data = _read_json(config.SETTINGS_FILE, {})

    settings = dict(DEFAULT_SETTINGS)
    settings.update(data or {})

    # Глубокое слияние для тумблеров типов долгов:
    # добавляет новые ключи, не теряя сохранённые значения.
    debt_types = dict(DEFAULT_DEBT_TYPES)
    debt_types.update(settings.get("debt_types") or {})
    settings["debt_types"] = debt_types

    return settings


def save_settings(settings: dict) -> None:
    _write_json(config.SETTINGS_FILE, settings)
