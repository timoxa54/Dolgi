import re
from datetime import datetime

from models import Lesson


DAY_NAMES = {
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
}


TIME_PATTERN = re.compile(
    r"^\d{2}:\d{2}$"
)


DATE_PATTERN = re.compile(
    r"^\d{2}\.\d{2}\.\d{4}$"
)


def is_time(value: str) -> bool:
    return bool(TIME_PATTERN.match(value.strip()))


def is_date(value: str) -> bool:
    value = value.strip()

    if not DATE_PATTERN.match(value):
        return False

    try:
        datetime.strptime(value, "%d.%m.%Y")
        return True
    except ValueError:
        return False


def clean(value: str) -> str:
    return " ".join(value.split()).strip()


def parse_lesson_type_and_subject(
    value: str,
) -> tuple[str | None, str]:
    """
    Пример:

        'лек Проектирование информационных систем'

    превращается в:

        ('лек', 'Проектирование информационных систем')
    """

    value = clean(value)

    if not value:
        return None, ""

    parts = value.split(maxsplit=1)

    if len(parts) == 1:
        return None, parts[0]

    first = parts[0].lower()

    lesson_types = {
        "лек",
        "лаб",
        "пра",
        "сем",
        "конс",
        "экз",
        "зач",
    }

    if first in lesson_types:
        return first, parts[1].strip()

    return None, value


def parse_classroom(value: str) -> tuple[str | None, str | None]:
    """
    Из:

        Аудитория: 10-307 (комп.)

    получаем:

        ('10-307 (комп.)', None)

    Если позже сайт будет явно показывать корпус,
    сюда можно добавить отдельный разбор.
    """

    value = clean(value)

    if not value.lower().startswith("аудитория:"):
        return None, None

    classroom = value.split(":", 1)[1].strip()

    return classroom or None, None


def is_ignored_line(value: str) -> bool:
    value = clean(value).lower()

    if not value:
        return True

    ignored = {
        "расписание",
        "преподаватель",
        "учебный год",
        "семестр",
        "текущая неделя",
        "выберите дату",
        "тип недели",
        "всё расписание",
        "печать",
        "экспорт",
        "календарь",
        "1-е занятие",
        "2-е занятие",
        "3-е занятие",
        "4-е занятие",
        "5-е занятие",
        "6-е занятие",
        "7-е занятие",
        "8-е занятие",
        "9-е занятие",
        "свободное время между занятиями",
    }

    return value in ignored


def parse_teacher_schedule(
    teacher_name: str,
    text: str,
) -> list[Lesson]:

    lines = [
        clean(line)
        for line in text.splitlines()
    ]

    lines = [
        line
        for line in lines
        if line
    ]

    lessons: list[Lesson] = []

    current_day: str | None = None
    current_date: str | None = None

    current_start: str | None = None
    current_end: str | None = None

    current_lesson_type: str | None = None
    current_subject: str | None = None
    current_group: str | None = None
    current_classroom: str | None = None

    def save_current_lesson():
        nonlocal current_start
        nonlocal current_end
        nonlocal current_lesson_type
        nonlocal current_subject
        nonlocal current_group
        nonlocal current_classroom

        if (
            not current_day
            or not current_date
            or not current_start
            or not current_end
            or not current_subject
        ):
            return

        lessons.append(
            Lesson(
                teacher=teacher_name,
                subject=current_subject,
                day=current_day,
                date=current_date,
                start_time=current_start,
                end_time=current_end,
                lesson_type=current_lesson_type,
                group=current_group,
                classroom=current_classroom,
            )
        )

        current_start = None
        current_end = None
        current_lesson_type = None
        current_subject = None
        current_group = None
        current_classroom = None

    i = 0

    while i < len(lines):
        line = lines[i]

        # -------------------------------------------------
        # День недели
        # -------------------------------------------------

        if line in DAY_NAMES:
            save_current_lesson()

            current_day = line
            current_date = None

            i += 1
            continue

        # -------------------------------------------------
        # Дата
        # -------------------------------------------------

        if is_date(line):
            current_date = line

            i += 1
            continue

        # -------------------------------------------------
        # Время
        #
        # На странице оно идёт парами:
        #
        # 08:00
        # 09:30
        # предмет
        # -------------------------------------------------

        if is_time(line):

            if i + 1 < len(lines) and is_time(lines[i + 1]):

                save_current_lesson()

                current_start = line
                current_end = lines[i + 1]

                i += 2
                continue

        # -------------------------------------------------
        # Всё остальное относится к текущей паре
        # -------------------------------------------------

        if current_start and current_end:

            if is_ignored_line(line):
                i += 1
                continue

            # Предмет
            if current_subject is None:

                current_lesson_type, current_subject = (
                    parse_lesson_type_and_subject(line)
                )

                i += 1
                continue

            # Аудитория
            if line.lower().startswith("аудитория:"):

                (
                    current_classroom,
                    _
                ) = parse_classroom(line)

                i += 1
                continue

            # Группа
            if current_group is None:

                current_group = line

                i += 1
                continue

        i += 1

    # Не забываем последнюю пару
    save_current_lesson()

    return lessons


def lessons_to_dict(
    lessons: list[Lesson],
) -> list[dict]:

    return [
        {
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
        }
        for lesson in lessons
    ]