import json
import re
from pathlib import Path
from collections import defaultdict


MATCHES_FILE = "matches.json"


# ============================================================
# НАСТРОЙКИ ОПТИМИЗАТОРА
# ============================================================

# Чем больше штраф, тем сильнее оптимизатор старается
# не менять корпус.
BUILDING_CHANGE_PENALTY = 100

# Штраф за ожидание между занятиями.
WAITING_MINUTE_PENALTY = 1

# Дополнительный штраф за очень длинный разрыв.
LONG_BREAK_THRESHOLD = 90
LONG_BREAK_PENALTY = 50


# ============================================================
# ЗАГРУЗКА MATCHES
# ============================================================

def load_matches():
    path = Path(MATCHES_FILE)

    if not path.exists():
        raise FileNotFoundError(
            f"Не найден файл:\n{path.resolve()}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


# ============================================================
# ВРЕМЯ
# ============================================================

def time_to_minutes(value: str) -> int:
    hour, minute = map(
        int,
        value.split(":")
    )

    return hour * 60 + minute


def overlaps(a: dict, b: dict) -> bool:
    a_start = time_to_minutes(
        a["start_time"]
    )

    a_end = time_to_minutes(
        a["end_time"]
    )

    b_start = time_to_minutes(
        b["start_time"]
    )

    b_end = time_to_minutes(
        b["end_time"]
    )

    return (
        a_start < b_end
        and b_start < a_end
    )


# ============================================================
# ОПРЕДЕЛЕНИЕ КОРПУСА
# ============================================================

def get_building(classroom: str | None) -> str | None:
    """
    Определяет корпус по строке аудитории.

    Примеры:

        2-202
        10-307 (комп.)
        5-200 Коворкинг-центр

    Результат:

        2
        10
        5

    Если корпус определить невозможно:

        None
    """

    if not classroom:
        return None

    value = classroom.strip()

    # Убираем лишние пробелы.
    value = re.sub(
        r"\s+",
        " ",
        value
    )

    # Обычный формат:
    #
    # 2-202
    # 10-307
    # 5-200
    #
    match = re.match(
        r"^(\d+)\s*[-–—]",
        value
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# КАНДИДАТЫ
# ============================================================

def build_candidates(matches_data):
    candidates = []

    for debt_index, (
        debt_id,
        debt
    ) in enumerate(
        matches_data.items()
    ):

        for match in debt["matches"]:

            classroom = match.get(
                "classroom"
            )

            candidates.append(
                {
                    "debt_index": debt_index,
                    "debt_id": debt_id,

                    "subject": debt[
                        "subject"
                    ],

                    "date": match[
                        "date"
                    ],

                    "start_time": match[
                        "start_time"
                    ],

                    "end_time": match[
                        "end_time"
                    ],

                    "teacher": match[
                        "teacher"
                    ],

                    "classroom": classroom,

                    "building": get_building(
                        classroom
                    ),

                    "group": match.get(
                        "group"
                    ),

                    "match_type": match.get(
                        "match_type"
                    ),
                }
            )

    return candidates


# ============================================================
# ГРУППИРОВКА ПО ДНЯМ
# ============================================================

def group_by_date(candidates):
    result = defaultdict(list)

    for candidate in candidates:
        result[
            candidate["date"]
        ].append(candidate)

    for date in result:

        result[date].sort(
            key=lambda item: (
                time_to_minutes(
                    item["start_time"]
                ),
                time_to_minutes(
                    item["end_time"]
                ),
            )
        )

    return dict(result)


# ============================================================
# СТАТИСТИКА ДНЯ
# ============================================================

def calculate_day_stats(lessons):
    if not lessons:
        return {
            "buildings": [],
            "known_buildings": [],
            "building_changes": 0,
            "waiting_minutes": 0,
            "long_breaks": 0,
            "span_minutes": 0,
            "known_building_lessons": 0,
            "unknown_building_lessons": 0,
        }

    lessons = sorted(
        lessons,
        key=lambda lesson:
            time_to_minutes(
                lesson["start_time"]
            )
    )

    buildings = [
        lesson.get("building")
        for lesson in lessons
    ]

    known_buildings = []

    for building in buildings:

        if (
            building is not None
            and building not in known_buildings
        ):
            known_buildings.append(
                building
            )

    # --------------------------------------------------------
    # Переходы между корпусами
    # --------------------------------------------------------
    #
    # ВАЖНО:
    #
    # Если у нас:
    #
    # 2 → неизвестно → 10
    #
    # мы НЕ считаем это автоматически
    # переходом 2 → 10.
    #
    # Неизвестная аудитория разрывает цепочку.
    #

    building_changes = 0

    previous_known_building = None
    previous_known_index = None

    for index, building in enumerate(
        buildings
    ):

        if building is None:
            previous_known_building = None
            previous_known_index = None
            continue

        if (
            previous_known_building is not None
            and previous_known_index is not None
        ):

            # Между двумя известными корпусами
            # не должно быть неизвестной аудитории.
            #
            # Если индексы идут подряд,
            # значит можно уверенно считать переход.

            if index == previous_known_index + 1:

                if (
                    building
                    != previous_known_building
                ):
                    building_changes += 1

        previous_known_building = building
        previous_known_index = index

    # --------------------------------------------------------
    # Ожидание
    # --------------------------------------------------------

    waiting_minutes = 0
    long_breaks = 0

    for previous, current in zip(
        lessons,
        lessons[1:]
    ):

        previous_end = time_to_minutes(
            previous["end_time"]
        )

        current_start = time_to_minutes(
            current["start_time"]
        )

        gap = (
            current_start
            - previous_end
        )

        if gap > 0:

            waiting_minutes += gap

            if gap >= LONG_BREAK_THRESHOLD:
                long_breaks += 1

    # --------------------------------------------------------
    # Продолжительность дня
    # --------------------------------------------------------

    first_start = time_to_minutes(
        lessons[0]["start_time"]
    )

    last_end = time_to_minutes(
        lessons[-1]["end_time"]
    )

    span_minutes = (
        last_end
        - first_start
    )

    known_building_lessons = sum(
        building is not None
        for building in buildings
    )

    unknown_building_lessons = (
        len(lessons)
        - known_building_lessons
    )

    return {
        "buildings": buildings,
        "known_buildings": known_buildings,

        "building_changes":
            building_changes,

        "waiting_minutes":
            waiting_minutes,

        "long_breaks":
            long_breaks,

        "span_minutes":
            span_minutes,

        "known_building_lessons":
            known_building_lessons,

        "unknown_building_lessons":
            unknown_building_lessons,
    }


# ============================================================
# ОЦЕНКА КОМФОРТНОСТИ ДНЯ
# ============================================================

def calculate_day_score(lessons):
    """
    Меньше score = лучше.

    Количество долгов здесь НЕ учитывается.

    Приоритеты внутри уже выбранного количества долгов:

    1. меньше переходов между корпусами;
    2. меньше ожидания;
    3. меньше длинных перерывов;
    4. меньше продолжительность дня.
    """

    stats = calculate_day_stats(
        lessons
    )

    score = 0

    # Переходы между корпусами —
    # самый большой штраф.
    score += (
        stats["building_changes"]
        * BUILDING_CHANGE_PENALTY
    )

    # Общее ожидание.
    score += (
        stats["waiting_minutes"]
        * WAITING_MINUTE_PENALTY
    )

    # Дополнительный штраф за очень длинные
    # промежутки внутри учебного дня.
    score += (
        stats["long_breaks"]
        * LONG_BREAK_PENALTY
    )

    # Чем меньше диапазон дня —
    # тем удобнее.
    score += stats[
        "span_minutes"
    ]

    return score


# ============================================================
# ГЕНЕРАЦИЯ ПЛАНОВ ОДНОГО ДНЯ
# ============================================================

def generate_day_plans(
    candidates,
    debt_count,
):
    """
    Строит варианты расписания для одного дня.

    В одном варианте:

    - занятия не пересекаются;
    - один долг не выбирается дважды;
    - можно выбрать разные долги
      с одинаковым временем, но только один
      из конфликтующих занятий.
    """

    candidates = sorted(
        candidates,
        key=lambda item: (
            time_to_minutes(
                item["end_time"]
            ),
            time_to_minutes(
                item["start_time"]
            ),
        )
    )

    states = {
        (0, 0): []
    }

    for candidate in candidates:

        start = time_to_minutes(
            candidate["start_time"]
        )

        end = time_to_minutes(
            candidate["end_time"]
        )

        current_states = list(
            states.items()
        )

        for (
            (mask, last_end),
            selected
        ) in current_states:

            # Пересечение с предыдущим занятием.
            if start < last_end:
                continue

            debt_bit = (
                1
                << candidate["debt_index"]
            )

            # Этот долг уже выбран.
            if mask & debt_bit:
                continue

            new_mask = (
                mask
                | debt_bit
            )

            key = (
                new_mask,
                end
            )

            new_selected = (
                selected
                + [candidate]
            )

            if key not in states:

                states[key] = (
                    new_selected
                )

            else:

                # Если получили тот же mask
                # и тот же end, оставляем
                # более комфортный вариант.
                existing = states[key]

                existing_score = (
                    calculate_day_score(
                        existing
                    )
                )

                new_score = (
                    calculate_day_score(
                        new_selected
                    )
                )

                if new_score < existing_score:
                    states[key] = (
                        new_selected
                    )

    # --------------------------------------------------------
    # Оставляем лучший вариант для каждого набора долгов.
    # --------------------------------------------------------

    best_by_mask = {}

    for (
        mask,
        end_time
    ), selected in states.items():

        current = best_by_mask.get(
            mask
        )

        if current is None:

            best_by_mask[mask] = (
                selected
            )

            continue

        current_score = (
            calculate_day_score(
                current
            )
        )

        selected_score = (
            calculate_day_score(
                selected
            )
        )

        if selected_score < current_score:

            best_by_mask[mask] = (
                selected
            )

    plans = []

    for mask, selected in (
        best_by_mask.items()
    ):

        stats = calculate_day_stats(
            selected
        )

        plans.append(
            {
                "mask": mask,

                "debt_count":
                    mask.bit_count(),

                "lessons":
                    selected,

                "score":
                    calculate_day_score(
                        selected
                    ),

                "stats":
                    stats,
            }
        )

    plans.sort(
        key=lambda plan: (
            -plan["debt_count"],
            plan["score"],
        )
    )

    return plans


# ============================================================
# УДАЛЕНИЕ ДОМИНИРУЕМЫХ ПЛАНОВ
# ============================================================

def remove_dominated_plans(plans):
    """
    Удаляет варианты, которые заведомо хуже другого.

    План A можно удалить, если план B:

    - закрывает все долги A;
    - закрывает не меньше долгов;
    - имеет не худшую комфортность.
    """

    result = []

    for plan in plans:

        dominated = False

        for other in plans:

            if plan is other:
                continue

            covers_all = (
                (
                    other["mask"]
                    | plan["mask"]
                )
                == other["mask"]
            )

            if not covers_all:
                continue

            if (
                other["debt_count"]
                >= plan["debt_count"]
                and
                other["score"]
                <= plan["score"]
            ):

                if (
                    other["debt_count"]
                    > plan["debt_count"]
                    or
                    other["score"]
                    < plan["score"]
                ):

                    dominated = True
                    break

        if not dominated:
            result.append(plan)

    return result


# ============================================================
# ОЦЕНКА ВСЕГО ПЛАНА
# ============================================================

def calculate_global_score(
    days,
    lessons,
):
    total_score = 0

    for date in days:

        day_lessons = [
            lesson
            for lesson in lessons
            if lesson["date"] == date
        ]

        total_score += (
            calculate_day_score(
                day_lessons
            )
        )

    return total_score


# ============================================================
# ГЛОБАЛЬНАЯ ОПТИМИЗАЦИЯ
# ============================================================

def optimize_days(
    day_plans,
    total_debts,
):
    dates = sorted(
        day_plans
    )

    best = None

    def is_better(
        candidate,
        current_best,
    ):
        if current_best is None:
            return True

        # ----------------------------------------------------
        # 1. Максимум долгов
        # ----------------------------------------------------

        if (
            candidate["covered_count"]
            != current_best[
                "covered_count"
            ]
        ):

            return (
                candidate[
                    "covered_count"
                ]
                >
                current_best[
                    "covered_count"
                ]
            )

        # ----------------------------------------------------
        # 2. Минимум учебных дней
        # ----------------------------------------------------

        if (
            len(candidate["days"])
            != len(
                current_best["days"]
            )
        ):

            return (
                len(candidate["days"])
                <
                len(current_best["days"])
            )

        # ----------------------------------------------------
        # 3. Минимум переходов между корпусами
        # ----------------------------------------------------

        if (
            candidate[
                "building_changes"
            ]
            !=
            current_best[
                "building_changes"
            ]
        ):

            return (
                candidate[
                    "building_changes"
                ]
                <
                current_best[
                    "building_changes"
                ]
            )

        # ----------------------------------------------------
        # 4. Больше занятий в известных корпусах
        # ----------------------------------------------------

        if (
            candidate[
                "known_building_lessons"
            ]
            !=
            current_best[
                "known_building_lessons"
            ]
        ):

            return (
                candidate[
                    "known_building_lessons"
                ]
                >
                current_best[
                    "known_building_lessons"
                ]
            )

        # ----------------------------------------------------
        # 5. Общая комфортность
        # ----------------------------------------------------

        if (
            candidate["global_score"]
            !=
            current_best[
                "global_score"
            ]
        ):

            return (
                candidate[
                    "global_score"
                ]
                <
                current_best[
                    "global_score"
                ]
            )

        # ----------------------------------------------------
        # 6. Минимум занятий
        # ----------------------------------------------------

        return (
            len(candidate["lessons"])
            <
            len(current_best["lessons"])
        )

    def calculate_global_building_stats(
        lessons
    ):
        building_changes = 0
        known_building_lessons = 0

        for date in sorted(
            {
                lesson["date"]
                for lesson in lessons
            }
        ):

            day_lessons = [
                lesson
                for lesson in lessons
                if lesson["date"] == date
            ]

            stats = calculate_day_stats(
                day_lessons
            )

            building_changes += (
                stats[
                    "building_changes"
                ]
            )

            known_building_lessons += (
                stats[
                    "known_building_lessons"
                ]
            )

        return (
            building_changes,
            known_building_lessons,
        )

    def search(
        index,
        covered_mask,
        selected_days,
        selected_lessons,
    ):
        nonlocal best

        covered_count = (
            covered_mask.bit_count()
        )

        if covered_count > 0:

            (
                building_changes,
                known_building_lessons,
            ) = calculate_global_building_stats(
                selected_lessons
            )

            global_score = (
                calculate_global_score(
                    selected_days,
                    selected_lessons,
                )
            )

            candidate = {
                "mask":
                    covered_mask,

                "covered_count":
                    covered_count,

                "days":
                    list(selected_days),

                "lessons":
                    list(selected_lessons),

                "global_score":
                    global_score,

                "building_changes":
                    building_changes,

                "known_building_lessons":
                    known_building_lessons,
            }

            if is_better(
                candidate,
                best,
            ):

                best = candidate

        if index >= len(dates):
            return

        # ----------------------------------------------------
        # Теоретический максимум
        # ----------------------------------------------------

        remaining_masks = 0

        for future_index in range(
            index,
            len(dates),
        ):

            for plan in day_plans[
                dates[future_index]
            ]:

                remaining_masks |= (
                    plan["mask"]
                )

        theoretical_max = (
            covered_mask
            | remaining_masks
        ).bit_count()

        if (
            best is not None
            and theoretical_max
            < best["covered_count"]
        ):
            return

        date = dates[index]

        # ----------------------------------------------------
        # Вариант 1:
        # пропустить день.
        # ----------------------------------------------------

        search(
            index + 1,
            covered_mask,
            selected_days,
            selected_lessons,
        )

        # ----------------------------------------------------
        # Вариант 2:
        # выбрать один из планов дня.
        # ----------------------------------------------------

        for plan in day_plans[
            date
        ]:

            new_mask = (
                covered_mask
                | plan["mask"]
            )

            if (
                new_mask
                == covered_mask
            ):
                continue

            search(
                index + 1,
                new_mask,
                selected_days
                + [date],
                selected_lessons
                + plan["lessons"],
            )

    search(
        0,
        0,
        [],
        [],
    )

    return best


# ============================================================
# НЕПОКРЫТЫЕ ДОЛГИ
# ============================================================

def get_uncovered_debts(
    matches_data,
    mask,
):
    result = []

    for index, (
        debt_id,
        debt
    ) in enumerate(
        matches_data.items()
    ):

        bit = (
            1
            << index
        )

        if not mask & bit:

            result.append(
                {
                    "id": debt_id,

                    "subject":
                        debt["subject"],

                    "teacher":
                        debt["teacher"],

                    "debt_type":
                        debt["debt_type"],

                    "has_matches":
                        bool(
                            debt["matches"]
                        ),
                }
            )

    return result


# ============================================================
# ПЕЧАТЬ ПЛАНОВ ПО ДНЯМ
# ============================================================

def print_day_plans(
    day_plans,
    matches_data,
):
    print("\n" + "=" * 70)
    print(
        "ЛУЧШИЕ ВАРИАНТЫ ПО КАЖДОМУ ДНЮ"
    )
    print("=" * 70)

    for date in sorted(
        day_plans
    ):

        plans = day_plans[date]

        if not plans:
            continue

        best = plans[0]

        stats = best["stats"]

        print(
            "\n"
            + "-"
            * 70
        )

        print(
            f"{date} → "
            f"до {best['debt_count']} долгов"
        )

        print(
            "Корпуса: "
            +
            (
                ", ".join(
                    stats[
                        "known_buildings"
                    ]
                )
                if stats[
                    "known_buildings"
                ]
                else "не определены"
            )
        )

        print(
            "Переходов между корпусами: "
            f"{stats['building_changes']}"
        )

        print(
            "Ожидание: "
            f"{stats['waiting_minutes']} мин."
        )

        print(
            "Длинных перерывов: "
            f"{stats['long_breaks']}"
        )

        print(
            "Диапазон дня: "
            f"{stats['span_minutes']} мин."
        )

        for lesson in best[
            "lessons"
        ]:

            building = (
                lesson["building"]
                or "?"
            )

            print(
                f"  "
                f"{lesson['start_time']}"
                f"–"
                f"{lesson['end_time']}"
                f" | корпус {building}"
                f" | {lesson['subject']}"
                f" | {lesson['teacher']}"
            )


# ============================================================
# ПЕЧАТЬ ГЛОБАЛЬНОГО ПЛАНА
# ============================================================

def print_global_plan(
    plan,
    matches_data,
):
    print("\n" + "=" * 70)
    print(
        "ГЛОБАЛЬНО ОПТИМАЛЬНЫЙ ПЛАН"
    )
    print("=" * 70)

    if not plan:

        print(
            "\nНе удалось построить план."
        )

        return

    print(
        f"\nЗакрывается долгов: "
        f"{plan['covered_count']} "
        f"из "
        f"{len(matches_data)}"
    )

    print(
        f"Учебных дней: "
        f"{len(plan['days'])}"
    )

    print(
        f"Занятий в плане: "
        f"{len(plan['lessons'])}"
    )

    print(
        f"Переходов между корпусами: "
        f"{plan['building_changes']}"
    )

    print(
        f"Занятий с определённым корпусом: "
        f"{plan['known_building_lessons']}"
    )

    print(
        f"Итоговая оценка комфортности: "
        f"{plan['global_score']}"
    )

    print("\nДНИ:")

    for date in sorted(
        plan["days"]
    ):

        print(
            f"\n"
            f"{'-' * 70}\n"
            f"{date}"
        )

        lessons = [
            lesson
            for lesson in plan[
                "lessons"
            ]
            if lesson["date"] == date
        ]

        lessons.sort(
            key=lambda lesson:
                time_to_minutes(
                    lesson["start_time"]
                )
        )

        stats = calculate_day_stats(
            lessons
        )

        print(
            f"\n  Корпуса: "
            +
            (
                ", ".join(
                    stats[
                        "known_buildings"
                    ]
                )
                if stats[
                    "known_buildings"
                ]
                else "не определены"
            )
        )

        print(
            f"  Переходов между корпусами: "
            f"{stats['building_changes']}"
        )

        print(
            f"  Ожидание между занятиями: "
            f"{stats['waiting_minutes']} мин."
        )

        print(
            f"  Длинных перерывов: "
            f"{stats['long_breaks']}"
        )

        print(
            f"  Продолжительность дня: "
            f"{stats['span_minutes']} мин."
        )

        for lesson in lessons:

            print(
                f"\n  "
                f"{lesson['start_time']}"
                f"–"
                f"{lesson['end_time']}"
            )

            print(
                f"  Предмет: "
                f"{lesson['subject']}"
            )

            print(
                f"  Преподаватель: "
                f"{lesson['teacher']}"
            )

            print(
                f"  Корпус: "
                f"{lesson['building'] or 'НЕ ОПРЕДЕЛЁН'}"
            )

            if lesson.get(
                "classroom"
            ):

                print(
                    f"  Аудитория: "
                    f"{lesson['classroom']}"
                )

            if lesson.get(
                "group"
            ):

                print(
                    f"  Группа: "
                    f"{lesson['group']}"
                )

            print(
                f"  Совпадение: "
                f"{lesson.get('match_type')}"
            )

    uncovered = get_uncovered_debts(
        matches_data,
        plan["mask"],
    )

    print("\n" + "=" * 70)
    print("ЧТО ОСТАЛОСЬ")
    print("=" * 70)

    if not uncovered:

        print(
            "\n✓ Все долги закрываются."
        )

        return

    for debt in uncovered:

        print(
            f"\n{debt['id']}"
        )

        print(
            f"  {debt['subject']}"
        )

        print(
            f"  Преподаватель: "
            f"{debt['teacher'] or 'НЕ УКАЗАН'}"
        )

        print(
            f"  Тип: "
            f"{debt['debt_type']}"
        )

        if debt[
            "has_matches"
        ]:

            print(
                "  ⚠ Занятия найдены, "
                "но не вошли в оптимальный план."
            )

        else:

            print(
                "  ✗ Подходящее занятие "
                "не найдено."
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print(
        "ОПТИМИЗАТОР АКАДЕМИЧЕСКИХ ДОЛГОВ"
    )
    print("=" * 70)

    matches_data = load_matches()

    print(
        f"\n✓ Загружено долгов: "
        f"{len(matches_data)}"
    )

    candidates = build_candidates(
        matches_data
    )

    print(
        f"✓ Загружено занятий-кандидатов: "
        f"{len(candidates)}"
    )

    days = group_by_date(
        candidates
    )

    print(
        f"✓ Найдено дат: "
        f"{len(days)}"
    )

    print(
        "\nСтрою варианты для каждого дня..."
    )

    day_plans = {}

    for date, date_candidates in (
        days.items()
    ):

        plans = generate_day_plans(
            date_candidates,
            len(matches_data),
        )

        plans = remove_dominated_plans(
            plans
        )

        day_plans[
            date
        ] = plans

        best_count = (
            plans[0]["debt_count"]
            if plans
            else 0
        )

        print(
            f"  {date}: "
            f"{len(plans)} вариантов, "
            f"максимум "
            f"{best_count} долгов"
        )

    print_day_plans(
        day_plans,
        matches_data,
    )

    print(
        "\nИщу глобально лучший вариант..."
    )

    plan = optimize_days(
        day_plans,
        len(matches_data),
    )

    print_global_plan(
        plan,
        matches_data,
    )


if __name__ == "__main__":
    main()