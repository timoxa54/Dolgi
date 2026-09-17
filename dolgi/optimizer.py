"""Поиск оптимального плана закрытия долгов.

Алгоритм перенесён из рабочей версии без изменений:

1. кандидаты группируются по датам;
2. для каждого дня строятся непересекающиеся варианты
   (динамическое программирование по маске долгов);
3. доминируемые варианты отбрасываются;
4. глобальный перебор дней выбирает лучший план:
   максимум долгов -> минимум дней -> минимум переходов
   между корпусами -> комфортность -> минимум занятий.
"""

from __future__ import annotations

from collections import defaultdict

from .models import get_building

# ----------------------------------------------------------------------
# Настройки оптимизатора
# ----------------------------------------------------------------------

BUILDING_CHANGE_PENALTY = 100
WAITING_MINUTE_PENALTY = 1
LONG_BREAK_THRESHOLD = 90
LONG_BREAK_PENALTY = 50


def time_to_minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


# ----------------------------------------------------------------------
# Кандидаты
# ----------------------------------------------------------------------


def build_candidates(matches_data: dict) -> list[dict]:
    candidates: list[dict] = []

    for debt_index, (debt_id, debt) in enumerate(matches_data.items()):
        for match in debt["matches"]:
            classroom = match.get("classroom")

            candidates.append(
                {
                    "debt_index": debt_index,
                    "debt_id": debt_id,
                    "subject": debt["subject"],
                    "date": match["date"],
                    "start_time": match["start_time"],
                    "end_time": match["end_time"],
                    "teacher": match["teacher"],
                    "classroom": classroom,
                    "building": get_building(classroom),
                    "group": match.get("group"),
                    "match_type": match.get("match_type"),
                }
            )

    return candidates


def group_by_date(candidates: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)

    for candidate in candidates:
        result[candidate["date"]].append(candidate)

    for date in result:
        result[date].sort(
            key=lambda item: (
                time_to_minutes(item["start_time"]),
                time_to_minutes(item["end_time"]),
            )
        )

    return dict(result)


# ----------------------------------------------------------------------
# Статистика и комфортность дня
# ----------------------------------------------------------------------


def calculate_day_stats(lessons: list[dict]) -> dict:
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

    lessons = sorted(lessons, key=lambda lesson: time_to_minutes(lesson["start_time"]))

    buildings = [lesson.get("building") for lesson in lessons]

    known_buildings: list[str] = []

    for building in buildings:
        if building is not None and building not in known_buildings:
            known_buildings.append(building)

    # Переход между корпусами засчитывается только между
    # двумя занятиями подряд с известными корпусами:
    # неизвестная аудитория разрывает цепочку.
    building_changes = 0
    previous_known_building = None
    previous_known_index = None

    for index, building in enumerate(buildings):
        if building is None:
            previous_known_building = None
            previous_known_index = None
            continue

        if (
            previous_known_building is not None
            and previous_known_index is not None
            and index == previous_known_index + 1
            and building != previous_known_building
        ):
            building_changes += 1

        previous_known_building = building
        previous_known_index = index

    waiting_minutes = 0
    long_breaks = 0

    for previous, current in zip(lessons, lessons[1:]):
        gap = time_to_minutes(current["start_time"]) - time_to_minutes(previous["end_time"])

        if gap > 0:
            waiting_minutes += gap

            if gap >= LONG_BREAK_THRESHOLD:
                long_breaks += 1

    span_minutes = time_to_minutes(lessons[-1]["end_time"]) - time_to_minutes(
        lessons[0]["start_time"]
    )

    known_building_lessons = sum(building is not None for building in buildings)

    return {
        "buildings": buildings,
        "known_buildings": known_buildings,
        "building_changes": building_changes,
        "waiting_minutes": waiting_minutes,
        "long_breaks": long_breaks,
        "span_minutes": span_minutes,
        "known_building_lessons": known_building_lessons,
        "unknown_building_lessons": len(lessons) - known_building_lessons,
    }


def calculate_day_score(lessons: list[dict]) -> int:
    """Меньше score = лучше.

    Приоритеты внутри выбранного набора долгов:
    1. меньше переходов между корпусами;
    2. меньше ожидания;
    3. меньше длинных перерывов;
    4. меньше продолжительность дня.
    """
    stats = calculate_day_stats(lessons)

    score = 0
    score += stats["building_changes"] * BUILDING_CHANGE_PENALTY
    score += stats["waiting_minutes"] * WAITING_MINUTE_PENALTY
    score += stats["long_breaks"] * LONG_BREAK_PENALTY
    score += stats["span_minutes"]

    return score


# ----------------------------------------------------------------------
# Варианты одного дня
# ----------------------------------------------------------------------


def generate_day_plans(candidates: list[dict], debt_count: int) -> list[dict]:
    """Строит варианты расписания одного дня.

    В одном варианте занятия не пересекаются
    и один долг не выбирается дважды.
    """
    candidates = sorted(
        candidates,
        key=lambda item: (
            time_to_minutes(item["end_time"]),
            time_to_minutes(item["start_time"]),
        ),
    )

    states: dict[tuple[int, int], list[dict]] = {(0, 0): []}

    for candidate in candidates:
        start = time_to_minutes(candidate["start_time"])
        end = time_to_minutes(candidate["end_time"])
        debt_bit = 1 << candidate["debt_index"]

        for (mask, last_end), selected in list(states.items()):
            if start < last_end:
                continue

            if mask & debt_bit:
                continue

            key = (mask | debt_bit, end)
            new_selected = selected + [candidate]

            if key not in states:
                states[key] = new_selected
            else:
                if calculate_day_score(new_selected) < calculate_day_score(states[key]):
                    states[key] = new_selected

    # Лучший вариант для каждого набора долгов.
    best_by_mask: dict[int, list[dict]] = {}

    for (mask, _end), selected in states.items():
        current = best_by_mask.get(mask)

        if current is None or calculate_day_score(selected) < calculate_day_score(current):
            best_by_mask[mask] = selected

    plans = []

    for mask, selected in best_by_mask.items():
        plans.append(
            {
                "mask": mask,
                "debt_count": mask.bit_count(),
                "lessons": selected,
                "score": calculate_day_score(selected),
                "stats": calculate_day_stats(selected),
            }
        )

    plans.sort(key=lambda plan: (-plan["debt_count"], plan["score"]))

    return plans


def remove_dominated_plans(plans: list[dict]) -> list[dict]:
    """Удаляет варианты, которые заведомо хуже другого."""
    result = []

    for plan in plans:
        dominated = False

        for other in plans:
            if plan is other:
                continue

            covers_all = (other["mask"] | plan["mask"]) == other["mask"]

            if not covers_all:
                continue

            if other["debt_count"] >= plan["debt_count"] and other["score"] <= plan["score"]:
                if other["debt_count"] > plan["debt_count"] or other["score"] < plan["score"]:
                    dominated = True
                    break

        if not dominated:
            result.append(plan)

    return result


# ----------------------------------------------------------------------
# Глобальная оптимизация
# ----------------------------------------------------------------------


def calculate_global_score(days: list[str], lessons: list[dict]) -> int:
    total_score = 0

    for date in days:
        day_lessons = [lesson for lesson in lessons if lesson["date"] == date]
        total_score += calculate_day_score(day_lessons)

    return total_score


def optimize_days(day_plans: dict[str, list[dict]], total_debts: int) -> dict | None:
    dates = sorted(day_plans)
    best: dict | None = None

    def is_better(candidate: dict, current_best: dict | None) -> bool:
        if current_best is None:
            return True

        if candidate["covered_count"] != current_best["covered_count"]:
            return candidate["covered_count"] > current_best["covered_count"]

        if len(candidate["days"]) != len(current_best["days"]):
            return len(candidate["days"]) < len(current_best["days"])

        if candidate["building_changes"] != current_best["building_changes"]:
            return candidate["building_changes"] < current_best["building_changes"]

        if candidate["known_building_lessons"] != current_best["known_building_lessons"]:
            return candidate["known_building_lessons"] > current_best["known_building_lessons"]

        if candidate["global_score"] != current_best["global_score"]:
            return candidate["global_score"] < current_best["global_score"]

        return len(candidate["lessons"]) < len(current_best["lessons"])

    def calculate_global_building_stats(lessons: list[dict]) -> tuple[int, int]:
        building_changes = 0
        known_building_lessons = 0

        for date in sorted({lesson["date"] for lesson in lessons}):
            day_lessons = [lesson for lesson in lessons if lesson["date"] == date]
            stats = calculate_day_stats(day_lessons)

            building_changes += stats["building_changes"]
            known_building_lessons += stats["known_building_lessons"]

        return building_changes, known_building_lessons

    def search(
        index: int,
        covered_mask: int,
        selected_days: list[str],
        selected_lessons: list[dict],
    ) -> None:
        nonlocal best

        covered_count = covered_mask.bit_count()

        if covered_count > 0:
            building_changes, known_building_lessons = calculate_global_building_stats(
                selected_lessons
            )

            candidate = {
                "mask": covered_mask,
                "covered_count": covered_count,
                "days": list(selected_days),
                "lessons": list(selected_lessons),
                "global_score": calculate_global_score(selected_days, selected_lessons),
                "building_changes": building_changes,
                "known_building_lessons": known_building_lessons,
            }

            if is_better(candidate, best):
                best = candidate

        if index >= len(dates):
            return

        # Теоретический максимум по оставшимся дням — отсечение.
        remaining_masks = 0

        for future_index in range(index, len(dates)):
            for plan in day_plans[dates[future_index]]:
                remaining_masks |= plan["mask"]

        theoretical_max = (covered_mask | remaining_masks).bit_count()

        if best is not None and theoretical_max < best["covered_count"]:
            return

        date = dates[index]

        # Вариант 1: пропустить день.
        search(index + 1, covered_mask, selected_days, selected_lessons)

        # Вариант 2: выбрать один из планов дня.
        for plan in day_plans[date]:
            new_mask = covered_mask | plan["mask"]

            if new_mask == covered_mask:
                continue

            search(
                index + 1,
                new_mask,
                selected_days + [date],
                selected_lessons + plan["lessons"],
            )

    search(0, 0, [], [])

    return best


# ----------------------------------------------------------------------
# Непокрытые долги
# ----------------------------------------------------------------------


def get_uncovered_debts(matches_data: dict, mask: int) -> list[dict]:
    result = []

    for index, (debt_id, debt) in enumerate(matches_data.items()):
        bit = 1 << index

        if not mask & bit:
            result.append(
                {
                    "id": debt_id,
                    "subject": debt["subject"],
                    "teacher": debt["teacher"],
                    "debt_type": debt["debt_type"],
                    "has_matches": bool(debt["matches"]),
                }
            )

    return result
