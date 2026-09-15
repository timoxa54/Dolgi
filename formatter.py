from optimizer import (
    calculate_day_stats,
    get_uncovered_debts,
    time_to_minutes,
)


MONTHS = {
    "01": "января",
    "02": "февраля",
    "03": "марта",
    "04": "апреля",
    "05": "мая",
    "06": "июня",
    "07": "июля",
    "08": "августа",
    "09": "сентября",
    "10": "октября",
    "11": "ноября",
    "12": "декабря",
}


WEEKDAYS = {
    0: "понедельник",
    1: "вторник",
    2: "среда",
    3: "четверг",
    4: "пятница",
    5: "суббота",
    6: "воскресенье",
}


def format_date(date: str) -> str:
    """
    16.09.2026 -> 16 сентября 2026
    """

    try:
        day, month, year = date.split(".")

        return (
            f"{day} {MONTHS.get(month, month)} "
            f"{year}"
        )

    except (ValueError, AttributeError):
        return date


def get_weekday(date: str) -> str:
    """
    Возвращает день недели.
    """

    try:
        from datetime import datetime

        value = datetime.strptime(
            date,
            "%d.%m.%Y",
        )

        return WEEKDAYS[
            value.weekday()
        ]

    except (ValueError, TypeError):
        return ""


def get_location(lesson: dict) -> str:
    """
    Формирует красивое описание места занятия.
    """

    building = lesson.get("building")
    classroom = lesson.get("classroom")

    if building and classroom:
        return (
            f"корпус {building}, "
            f"{classroom}"
        )

    if classroom:
        return classroom

    if building:
        return f"корпус {building}"

    return "место не определено"


def build_full_plan_text(
    plan,
    matches_data,
):
    """
    Формирует единый текст оптимального плана.

    Используется одновременно:
    - для консоли;
    - для Telegram.

    Структура plan соответствует optimizer.py:
        plan["days"]    -> список дат
        plan["lessons"] -> список занятий
    """

    if not plan:
        return (
            "❌ Не удалось построить "
            "оптимальный план."
        )

    lines = []

    total_debts = len(matches_data)
    covered_count = plan["covered_count"]
    days = sorted(plan["days"])

    lessons_by_date = {}

    for lesson in plan["lessons"]:

        date = lesson.get("date")

        if not date:
            continue

        lessons_by_date.setdefault(
            date,
            [],
        ).append(lesson)

    # ============================================================
    # ЗАГОЛОВОК
    # ============================================================

    lines.append(
        "📚 ПЛАН ЗАКРЫТИЯ АКАДЕМИЧЕСКИХ ДОЛГОВ"
    )
    lines.append(
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    lines.append("")

    lines.append(
        f"🎯 Закрывается долгов: "
        f"{covered_count} из {total_debts}"
    )

    lines.append(
        f"📅 Учебных дней: {len(days)}"
    )

    lines.append(
        f"📖 Занятий: {len(plan['lessons'])}"
    )

    lines.append(
        f"🏢 Переходов между корпусами: "
        f"{plan['building_changes']}"
    )

    lines.append(
        f"📍 Занятий с определённым корпусом: "
        f"{plan['known_building_lessons']}"
    )

    lines.append(
        f"⭐ Комфортность: "
        f"{plan['global_score']}"
    )

    # ============================================================
    # ДНИ
    # ============================================================

    for date in days:

        day_lessons = lessons_by_date.get(
            date,
            [],
        )

        day_lessons.sort(
            key=lambda lesson:
                time_to_minutes(
                    lesson["start_time"]
                )
        )

        lines.append("")
        lines.append(
            "━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        weekday = get_weekday(date)

        if weekday:
            lines.append(
                f"📅 {format_date(date)} "
                f"({weekday})"
            )
        else:
            lines.append(
                f"📅 {date}"
            )

        if not day_lessons:
            lines.append(
                "Нет занятий."
            )
            continue

        # --------------------------------------------------------
        # Статистика дня
        # --------------------------------------------------------

        stats = calculate_day_stats(
            day_lessons
        )

        lines.append("")

        if stats["known_buildings"]:
            buildings = ", ".join(
                stats["known_buildings"]
            )
        else:
            buildings = "не определены"

        lines.append(
            f"🏢 Корпуса: {buildings}"
        )

        lines.append(
            f"🚶 Переходов: "
            f"{stats['building_changes']}"
        )

        lines.append(
            f"⏳ Ожидание: "
            f"{stats['waiting_minutes']} мин."
        )

        lines.append(
            f"☕ Длинных перерывов: "
            f"{stats['long_breaks']}"
        )

        lines.append(
            f"⏱ Продолжительность: "
            f"{stats['span_minutes']} мин."
        )

        # --------------------------------------------------------
        # Занятия
        # --------------------------------------------------------

        for number, lesson in enumerate(
            day_lessons,
            start=1,
        ):

            lines.append("")
            lines.append(
                f"{number}. "
                f"🕐 {lesson['start_time']}"
                f"–{lesson['end_time']}"
            )

            subject = lesson.get(
                "subject"
            )

            if subject:
                lines.append(
                    f"   📘 {subject}"
                )

            teacher = lesson.get(
                "teacher"
            )

            if teacher:
                lines.append(
                    f"   👨‍🏫 {teacher}"
                )

            location = get_location(
                lesson
            )

            lines.append(
                f"   📍 {location}"
            )

            group = lesson.get(
                "group"
            )

            if group:
                lines.append(
                    f"   👥 {group}"
                )

            match_type = lesson.get(
                "match_type"
            )

            if match_type:
                lines.append(
                    f"   🔎 {match_type}"
                )

            # ----------------------------------------------------
            # Какой долг закрывает
            # ----------------------------------------------------

            debt_index = lesson.get(
                "debt_index"
            )

            if debt_index is not None:

                matches_items = list(
                    matches_data.items()
                )

                if (
                    0 <= debt_index
                    < len(matches_items)
                ):

                    debt = (
                        matches_items[
                            debt_index
                        ][1]
                    )

                    debt_subject = debt.get(
                        "subject",
                        "Неизвестный предмет",
                    )

                    lines.append(
                        f"   🎯 Долг: "
                        f"{debt_subject}"
                    )

    # ============================================================
    # ОСТАВШИЕСЯ ДОЛГИ
    # ============================================================

    uncovered = get_uncovered_debts(
        matches_data,
        plan["mask"],
    )

    lines.append("")
    lines.append(
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    lines.append(
        "📌 ЧТО ОСТАЛОСЬ"
    )
    lines.append(
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    if not uncovered:

        lines.append("")
        lines.append(
            "🎉 Все долги закрываются!"
        )

    else:

        for index, debt in enumerate(
            uncovered,
            start=1,
        ):

            lines.append("")
            lines.append(
                f"{index}. "
                f"{debt['subject']}"
            )

            teacher = (
                debt["teacher"]
                or "НЕ УКАЗАН"
            )

            lines.append(
                f"   👨‍🏫 {teacher}"
            )

            lines.append(
                f"   📝 {debt['debt_type']}"
            )

            if debt["has_matches"]:

                lines.append(
                    "   ⚠ Подходящие занятия "
                    "найдены, но не вошли "
                    "в оптимальный план."
                )

            else:

                lines.append(
                    "   ❌ Подходящее занятие "
                    "не найдено."
                )

    # ============================================================
    # ФИНАЛ
    # ============================================================

    lines.append("")
    lines.append(
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    lines.append(
        "🤖 План сформирован автоматически."
    )

    return "\n".join(lines)


def print_full_plan(
    plan,
    matches_data,
):
    """
    Печатает тот же текст,
    который отправляется в Telegram.
    """

    print(
        "\n"
        + build_full_plan_text(
            plan,
            matches_data,
        )
    )