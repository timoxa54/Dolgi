import json
import re
from pathlib import Path

from parser import parse_zachetka


ZACHETKA_FILE = "Зачётная книжка.html"
SCHEDULE_FILE = "schedule.json"
MATCHES_FILE = "matches.json"


def normalize_subject(value: str) -> str:
    """
    Нормализация названия предмета.
    """

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

    # Убираем многоточие.
    value = value.replace("...", "")

    # Убираем лишние символы по краям.
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def subjects_match(
    debt_subject: str,
    lesson_subject: str,
) -> str | None:
    """
    Возвращает тип совпадения:

    exact
        Полное совпадение после нормализации.

    normalized
        Совпадение после удаления несущественных
        различий.

    partial
        Одно название содержит другое.

    None
        Совпадения нет.
    """

    debt = normalize_subject(
        debt_subject
    )

    lesson = normalize_subject(
        lesson_subject
    )

    if not debt or not lesson:
        return None

    if debt == lesson:
        return "exact"

    # Убираем оставшиеся различия в пунктуации.
    debt_clean = re.sub(
        r"[^a-zа-я0-9]+",
        "",
        debt,
    )

    lesson_clean = re.sub(
        r"[^a-zа-я0-9]+",
        "",
        lesson,
    )

    if debt_clean == lesson_clean:
        return "normalized"

    # Защищённое частичное совпадение.
    # Не используем его для очень коротких названий.
    if len(debt_clean) >= 15 and len(lesson_clean) >= 15:

        if (
            debt_clean in lesson_clean
            or lesson_clean in debt_clean
        ):
            return "partial"

    return None


def load_schedule():
    path = Path(SCHEDULE_FILE)

    if not path.exists():
        raise FileNotFoundError(
            f"Не найден файл:\n"
            f"{path.resolve()}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def split_teachers(
    teacher_value: str | None,
) -> list[str]:

    if not teacher_value:
        return []

    return [
        teacher.strip()
        for teacher in teacher_value.split(",")
        if teacher.strip()
    ]


def create_match(
    lesson: dict,
    match_type: str,
) -> dict:

    return {
        "teacher": lesson.get("teacher"),
        "subject": lesson.get("subject"),
        "day": lesson.get("day"),
        "date": lesson.get("date"),
        "start_time": lesson.get("start_time"),
        "end_time": lesson.get("end_time"),
        "lesson_type": lesson.get("lesson_type"),
        "group": lesson.get("group"),
        "classroom": lesson.get("classroom"),
        "building": lesson.get("building"),
        "match_type": match_type,
    }


def find_subject_matches(
    debt,
    schedule_data,
):
    """
    Ищет занятия для одного долга.

    Если преподаватель указан:
        ищем только у него.

    Если преподаватель отсутствует:
        ищем предмет среди всех загруженных
        преподавателей.
    """

    debt_subject = debt.subject

    requested_teachers = split_teachers(
        debt.teacher
    )

    matches = []

    # -------------------------------------------------
    # 1. Преподаватель указан
    # -------------------------------------------------

    if requested_teachers:

        for teacher in requested_teachers:

            teacher_schedule = schedule_data.get(
                teacher
            )

            if not teacher_schedule:
                continue

            if teacher_schedule.get("error"):
                continue

            for lesson in teacher_schedule.get(
                "lessons",
                [],
            ):

                match_type = subjects_match(
                    debt_subject,
                    lesson.get("subject", ""),
                )

                if match_type is None:
                    continue

                matches.append(
                    create_match(
                        lesson,
                        match_type,
                    )
                )

        return matches

    # -------------------------------------------------
    # 2. Преподаватель не указан
    # -------------------------------------------------

    for teacher_key, teacher_schedule in schedule_data.items():

        if not teacher_schedule:
            continue

        if teacher_schedule.get("error"):
            continue

        for lesson in teacher_schedule.get(
            "lessons",
            [],
        ):

            match_type = subjects_match(
                debt_subject,
                lesson.get("subject", ""),
            )

            if match_type is None:
                continue

            matches.append(
                create_match(
                    lesson,
                    match_type,
                )
            )

    return matches


def remove_duplicate_matches(
    matches: list[dict],
) -> list[dict]:

    unique = {}

    for match in matches:

        key = (
            match.get("teacher"),
            match.get("date"),
            match.get("start_time"),
            match.get("end_time"),
            match.get("subject"),
            match.get("classroom"),
        )

        unique[key] = match

    return list(unique.values())


def build_matches(
    debts,
    schedule_data,
):

    result = {}

    for index, debt in enumerate(
        debts,
        start=1,
    ):

        matches = find_subject_matches(
            debt,
            schedule_data,
        )

        matches = remove_duplicate_matches(
            matches
        )

        key = f"{index}. {debt.subject}"

        result[key] = {
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


def save_matches(data):

    path = Path(MATCHES_FILE)

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"\n✓ Результат сохранён:\n"
        f"  {path.resolve()}"
    )


def print_matches(data):

    print("\n" + "=" * 70)
    print("СОПОСТАВЛЕНИЕ ДОЛГОВ С РАСПИСАНИЕМ")
    print("=" * 70)

    total_debts = len(data)
    debts_with_matches = 0
    debts_without_matches = 0
    total_matches = 0

    for key, debt in data.items():

        matches = debt["matches"]

        print("\n" + "-" * 70)

        print(key)

        print(
            f"  Предмет: "
            f"{debt['subject']}"
        )

        print(
            f"  Контроль: "
            f"{debt['control_type']}"
        )

        print(
            f"  Результат: "
            f"{debt['grade'] or 'пусто'}"
        )

        print(
            f"  Тип долга: "
            f"{debt['debt_type']}"
        )

        print(
            f"  Преподаватель: "
            f"{debt['teacher'] or 'НЕ УКАЗАН'}"
        )

        print(
            f"  Совпадений: "
            f"{len(matches)}"
        )

        if not matches:

            print(
                "  ⚠ Подходящих занятий "
                "не найдено."
            )

            debts_without_matches += 1

            continue

        debts_with_matches += 1
        total_matches += len(matches)

        # Группируем для красивого вывода.
        match_types = {}

        for match in matches:

            match_type = match["match_type"]

            match_types[match_type] = (
                match_types.get(match_type, 0) + 1
            )

        print(
            "  Типы совпадений: "
            + ", ".join(
                f"{key}={value}"
                for key, value
                in match_types.items()
            )
        )

        for match in matches:

            print(
                f"\n    {match['date']} "
                f"({match['day']})"
            )

            print(
                f"    {match['start_time']}–"
                f"{match['end_time']}"
            )

            print(
                f"    {match['subject']}"
            )

            print(
                f"    Совпадение: "
                f"{match['match_type']}"
            )

            print(
                f"    Преподаватель: "
                f"{match['teacher']}"
            )

            if match["group"]:
                print(
                    f"    Группа: "
                    f"{match['group']}"
                )

            if match["classroom"]:
                print(
                    f"    Аудитория: "
                    f"{match['classroom']}"
                )

    print("\n" + "=" * 70)
    print("ИТОГ")
    print("=" * 70)

    print(
        f"\nВсего долгов: "
        f"{total_debts}"
    )

    print(
        f"С расписанием: "
        f"{debts_with_matches}"
    )

    print(
        f"Без совпадений: "
        f"{debts_without_matches}"
    )

    print(
        f"Всего найдено совпадений: "
        f"{total_matches}"
    )


def main():

    print("=" * 70)
    print("АНАЛИЗ ДОЛГОВ И РАСПИСАНИЯ")
    print("=" * 70)

    print(
        "\nЗагружаю зачётную книжку..."
    )

    debts = parse_zachetka(
        ZACHETKA_FILE
    )

    print(
        f"✓ Загружено долгов: "
        f"{len(debts)}"
    )

    print(
        "\nЗагружаю schedule.json..."
    )

    schedule_data = load_schedule()

    print(
        f"✓ Загружено преподавателей: "
        f"{len(schedule_data)}"
    )

    print(
        "\nСопоставляю предметы..."
    )

    matches = build_matches(
        debts,
        schedule_data,
    )

    save_matches(matches)

    print_matches(matches)


if __name__ == "__main__":
    main()