"""Проверка разбора страниц БГПУ на сохранённых копиях.

Запуск:

    python tests/test_parsing.py

Скрипт не требует интернета и не использует pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(BASE_DIR))

# Чтобы русский текст читался в любой консоли.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from dolgi.models import Debt  # noqa: E402
from dolgi.parsing import parse_schedule_html, parse_zachetka_html  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  [ok]   {message}")
    else:
        print(f"  [FAIL] {message}")
        failures.append(message)


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8", errors="ignore")


# ----------------------------------------------------------------------
# Зачётная книжка
# ----------------------------------------------------------------------


def test_zachetka() -> None:
    print("\nЗачётная книжка:")

    info, debts = parse_zachetka_html(read("zachetka.html"))

    check(info.student == "Железнов Тимофей Константинович", f"ФИО: {info.student}")
    check(info.group == "ПИНФ_ПИЦЭ_И-33-24(28)", f"группа: {info.group}")
    check(info.book_number == "224116БО", f"номер книжки: {info.book_number}")
    check(info.average == "2.67", f"средний балл: {info.average}")
    check(len(debts) == 20, f"долгов найдено: {len(debts)}")

    courses = {debt.course for debt in debts}

    check(
        courses == {2},
        f"предстоящая сессия (3 курс) не попала в долги: курсы {sorted(courses)}",
    )

    subjects = [debt.subject for debt in debts]

    check(
        "Эконометрика" in subjects and "Операционные системы" in subjects,
        "долги с оценками «Неуд»/«Незачет» попали в список",
    )

    check(
        "Базы данных" not in subjects and "Акмулловедение" not in subjects,
        "положительные оценки не считаются долгами",
    )

    check(
        "Разработка мобильных приложений" not in subjects,
        "предстоящие экзамены текущей сессии — не долги",
    )

    econometrics = next(
        debt for debt in debts if debt.subject == "Эконометрика"
    )

    check(econometrics.teacher == "Дяминова Э.И.", f"преподаватель: {econometrics.teacher}")
    check(econometrics.control_type == "Экзамен", f"вид контроля: {econometrics.control_type}")
    check(econometrics.course == 2, f"курс: {econometrics.course}")
    check(
        econometrics.debt_type == "Неудовлетворительная оценка",
        f"тип долга: {econometrics.debt_type}",
    )

    empty_grade = next(
        debt for debt in debts if debt.subject == "Дискретная математика"
    )

    check(
        empty_grade.debt_type == "Оценка отсутствует",
        f"пустая оценка в завершённом семестре: {empty_grade.debt_type}",
    )
    check(
        empty_grade.grade == "",
        "у пустой оценки нет значения",
    )

    empty_debts = [debt for debt in debts if debt.debt_type == "Оценка отсутствует"]

    check(
        len(empty_debts) == 9,
        f"долгов с пустой оценкой: {len(empty_debts)}",
    )

    multi_teacher = Debt(
        subject="Методы исследовательской и проектной деятельности",
        teacher="Филиппова А.С., Курбангалеева К.Р.",
    )

    check(
        multi_teacher.teachers
        == ["Филиппова А.С.", "Курбангалеева К.Р."],
        f"несколько преподавателей: {multi_teacher.teachers}",
    )


# ----------------------------------------------------------------------
# Расписание преподавателя
# ----------------------------------------------------------------------


def test_teacher_schedule() -> None:
    print("\nРасписание преподавателя:")

    entry = parse_schedule_html(
        read("teacher_schedule.html"),
        owner="Старцева О.Г.",
        kind="teacher",
    )

    check(entry.actual_name == "Старцева О. Г.", f"имя: {entry.actual_name}")
    check(len(entry.lessons) == 10, f"занятий: {len(entry.lessons)}")

    if not entry.lessons:
        return

    first = entry.lessons[0]

    check(first.date == "15.09.2026", f"дата первого занятия: {first.date}")
    check(first.day == "Вторник", f"день недели: {first.day}")
    check(first.start_time == "08:00", f"начало: {first.start_time}")
    check(first.end_time == "09:30", f"конец: {first.end_time}")
    check(first.lesson_type == "лаб", f"тип занятия: {first.lesson_type}")
    check(
        first.subject == "Управление IT-проектами, п/г 2",
        f"предмет: {first.subject}",
    )
    check(first.group == "ИСИТ-41-23", f"группа: {first.group}")
    check(first.classroom == "10-307 (комп.)", f"аудитория: {first.classroom}")
    check(first.building == "10", f"корпус: {first.building}")
    check(first.teacher == "Старцева О.Г.", f"преподаватель: {first.teacher}")

    dates = {lesson.date for lesson in entry.lessons}

    check(
        dates == {"15.09.2026", "18.09.2026"},
        f"даты занятий: {sorted(dates)}",
    )

    no_classroom = [
        lesson for lesson in entry.lessons if not lesson.classroom
    ]

    check(not no_classroom, "у всех занятий определена аудитория")


def test_group_schedule() -> None:
    print("\nРасписание группы:")

    entry = parse_schedule_html(
        read("group_schedule.html"),
        owner="ПИНФ_ПИЦЭ-31-24",
        kind="group",
    )

    check(entry.actual_name == "ПИНФ_ПИЦЭ-31-24", f"имя: {entry.actual_name}")
    check(len(entry.lessons) == 6, f"занятий: {len(entry.lessons)}")

    if not entry.lessons:
        return

    first = entry.lessons[0]

    check(first.date == "16.09.2026", f"дата первого занятия: {first.date}")
    check(first.day == "Среда", f"день недели: {first.day}")
    check(first.start_time == "12:20", f"начало: {first.start_time}")
    check(first.end_time == "13:50", f"конец: {first.end_time}")
    check(first.lesson_type == "лек", f"тип занятия: {first.lesson_type}")
    check(
        first.subject == "Разработка мобильных приложений",
        f"предмет: {first.subject}",
    )
    check(first.teacher == "Богданов М.Р.", f"преподаватель: {first.teacher}")
    check(first.classroom == "10-307 (комп.)", f"аудитория: {first.classroom}")
    check(first.building == "10", f"корпус: {first.building}")

    with_type = [
        lesson for lesson in entry.lessons if lesson.lesson_type == "пр"
    ]

    check(
        any(
            lesson.subject == "Общая физическая подготовка"
            for lesson in with_type
        ),
        "тип «пр.» распознаётся и отделяется от предмета",
    )

    teachers = {lesson.teacher for lesson in entry.lessons}

    check(
        "" not in teachers,
        f"у всех занятий группы указан преподаватель: {sorted(teachers)}",
    )


def main() -> int:
    test_zachetka()
    test_teacher_schedule()
    test_group_schedule()

    print()

    if failures:
        print(f"Провалено проверок: {len(failures)}")

        for failure in failures:
            print(f"  - {failure}")

        return 1

    print("Все проверки пройдены.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
