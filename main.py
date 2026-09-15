from parser import parse_zachetka
from matcher import save_matches
from optimizer import (
    load_matches,
    build_candidates,
    group_by_date,
    generate_day_plans,
    remove_dominated_plans,
    optimize_days,
)
from formatter import print_full_plan, build_full_plan_text
from telegram import send_plan


ZACHETKA_FILE = "Зачётная книжка.html"


def main():

    print("=" * 70)
    print(
        "              ПЛАНИРОВЩИК ЗАКРЫТИЯ ДОЛГОВ"
    )
    print("=" * 70)

    # ============================================================
    # 1. ЧИТАЕМ ЗАЧЁТКУ
    # ============================================================

    try:

        debts = parse_zachetka(
            ZACHETKA_FILE
        )

    except FileNotFoundError as error:

        print(error)
        return

    except Exception as error:

        print(
            "\nОШИБКА ПРИ ОБРАБОТКЕ "
            "ЗАЧЁТНОЙ КНИЖКИ:"
        )
        print(error)
        return

    print(
        f"\nНайдено долгов: "
        f"{len(debts)}"
    )

    if not debts:

        print(
            "Долгов не найдено."
        )

        return

    # ============================================================
    # 2. ПОКАЗЫВАЕМ ДОЛГИ
    # ============================================================

    print(
        "\n"
        + "-" * 70
    )

    for index, debt in enumerate(
        debts,
        start=1,
    ):

        print(
            f"\n{index}. "
            f"{debt.subject}"
        )

        print(
            f"   Контроль:       "
            f"{debt.control_type}"
        )

        if debt.grade:

            print(
                f"   Результат:      "
                f"{debt.grade}"
            )

        else:

            print(
                "   Результат:      "
                "— (оценка отсутствует)"
            )

        print(
            f"   Тип долга:      "
            f"{debt.debt_type}"
        )

        if debt.teacher:

            print(
                f"   Преподаватель:  "
                f"{debt.teacher}"
            )

        else:

            print(
                "   Преподаватель:  "
                "НЕ УКАЗАН"
            )

        if debt.hours:

            print(
                f"   Часы:           "
                f"{debt.hours}"
            )

        if debt.credits:

            print(
                f"   Зачётные ед.:   "
                f"{debt.credits}"
            )

        print(
            "-" * 70
        )

    # ============================================================
    # 3. ЗАГРУЖАЕМ MATCHES
    # ============================================================

    try:

        matches_data = load_matches()

    except Exception as error:

        print(
            "\nОШИБКА ПРИ ЗАГРУЗКЕ "
            "matches.json:"
        )
        print(error)
        return

    print(
        f"\n✓ Загружено долгов для "
        f"оптимизации: "
        f"{len(matches_data)}"
    )

    # ============================================================
    # 4. СОЗДАЁМ КАНДИДАТОВ
    # ============================================================

    candidates = build_candidates(
        matches_data
    )

    print(
        f"✓ Загружено занятий-кандидатов: "
        f"{len(candidates)}"
    )

    # ============================================================
    # 5. ГРУППИРУЕМ ПО ДАТАМ
    # ============================================================

    days = group_by_date(
        candidates
    )

    print(
        f"✓ Найдено дат: "
        f"{len(days)}"
    )

    # ============================================================
    # 6. СТРОИМ ВАРИАНТЫ
    # ============================================================

    print(
        "\nСтрою варианты "
        "для каждого дня..."
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

    # ============================================================
    # 7. ГЛОБАЛЬНАЯ ОПТИМИЗАЦИЯ
    # ============================================================

    print(
        "\nИщу глобально лучший вариант..."
    )

    plan = optimize_days(
        day_plans,
        len(matches_data),
    )

    if not plan:

        print(
            "\n❌ Не удалось "
            "построить план."
        )

        return

    # ============================================================
    # 8. ВЫВОДИМ ГОТОВЫЙ ПЛАН
    # ============================================================

    print_full_plan(
        plan,
        matches_data,
    )

    # ============================================================
    # 9. TELEGRAM
    # ============================================================

    print(
        "\n📨 Отправляю план "
        "в Telegram..."
    )

    try:

        telegram_text = (
            build_full_plan_text(
                plan,
                matches_data,
            )
        )

        send_plan(
            telegram_text
        )

        print(
            "✓ План успешно "
            "отправлен в Telegram."
        )

    except Exception as error:

        print(
            "✗ Не удалось "
            "отправить план в Telegram:"
        )

        print(error)


if __name__ == "__main__":
    main()