"""Сопоставление долгов с занятиями из расписаний.

Логика совпадений предметов перенесена из рабочей версии
без изменений: exact / normalized / partial.
"""

from __future__ import annotations

import re

from .models import Debt, ScheduleEntry

# ----------------------------------------------------------------------
# Нормализация названий предметов
# ----------------------------------------------------------------------


def normalize_subject(value: str) -> str:
    value = value.lower().strip()

    replacements = {
        "ё": "е",
        "—": "-",
        "–": "-",
        "«": "",
        "»": "",
        '"': "",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = value.replace("...", "")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def subjects_match(debt_subject: str, lesson_subject: str) -> str | None:
    """Возвращает тип совпадения: exact / normalized / partial или None."""
    debt = normalize_subject(debt_subject)
    lesson = normalize_subject(lesson_subject)

    if not debt or not lesson:
        return None

    if debt == lesson:
        return "exact"

    debt_clean = re.sub(r"[^a-zа-я0-9]+", "", debt)
    lesson_clean = re.sub(r"[^a-zа-я0-9]+", "", lesson)

    if debt_clean == lesson_clean:
        return "normalized"

    if len(debt_clean) >= 15 and len(lesson_clean) >= 15:
        if debt_clean in lesson_clean or lesson_clean in debt_clean:
            return "partial"

    return None


# ----------------------------------------------------------------------
# Поиск совпадений
# ----------------------------------------------------------------------


def _lesson_match(lesson, match_type: str) -> dict:
    return {
        "teacher": lesson.teacher,
        "subject": lesson.subject,
        "day": lesson.day,
        "date": lesson.date,
        "start_time": lesson.start_time,
        "end_time": lesson.end_time,
        "lesson_type": lesson.lesson_type,
        "group": lesson.group,
        "classroom": lesson.classroom,
        "building": lesson.building,
        "match_type": match_type,
    }


def find_subject_matches(
    debt: Debt,
    schedule: dict[str, ScheduleEntry],
) -> list[dict]:
    """Ищет занятия для одного долга.

    Если преподаватель указан — ищем только у него,
    иначе — среди всех загруженных расписаний.
    """
    matches: list[dict] = []

    if debt.teachers:
        for teacher in debt.teachers:
            entry = schedule.get(teacher)

            if entry is None or entry.error:
                continue

            for lesson in entry.lessons:
                match_type = subjects_match(debt.subject, lesson.subject)

                if match_type is not None:
                    matches.append(_lesson_match(lesson, match_type))

        return matches

    for entry in schedule.values():
        if entry.error:
            continue

        for lesson in entry.lessons:
            match_type = subjects_match(debt.subject, lesson.subject)

            if match_type is not None:
                matches.append(_lesson_match(lesson, match_type))

    return matches


def remove_duplicate_matches(matches: list[dict]) -> list[dict]:
    unique: dict[tuple, dict] = {}

    for match in matches:
        key = (
            match["teacher"],
            match["date"],
            match["start_time"],
            match["end_time"],
            match["subject"],
            match["classroom"],
        )

        unique[key] = match

    return list(unique.values())


def build_matches(
    debts: list[Debt],
    schedule: dict[str, ScheduleEntry],
) -> dict[str, dict]:
    """Строит словарь долгов с найденными занятиями.

    Структура результата сохранена совместимой с оптимизатором:

        "<номер>. <предмет>": {
            subject, control_type, grade, debt_type, teacher, hours, credits,
            matches: [...]
        }
    """
    result: dict[str, dict] = {}

    for index, debt in enumerate(debts, start=1):
        matches = find_subject_matches(debt, schedule)
        matches = remove_duplicate_matches(matches)

        result[f"{index}. {debt.subject}"] = {
            "subject": debt.subject,
            "control_type": debt.control_type,
            "grade": debt.grade,
            "debt_type": debt.debt_type,
            "teacher": debt.teacher,
            "hours": debt.hours,
            "credits": debt.credits,
            "matches": matches,
        }

    return result
