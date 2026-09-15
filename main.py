from parser import parse_zachetka


ZACHETKA_FILE = "Зачётная книжка.html"


def main():
    print("=" * 70)
    print("              ПЛАНИРОВЩИК ЗАКРЫТИЯ ДОЛГОВ")
    print("=" * 70)

    try:
        debts = parse_zachetka(ZACHETKA_FILE)

    except FileNotFoundError as error:
        print(error)
        return

    except Exception as error:
        print("\nОШИБКА ПРИ ОБРАБОТКЕ ЗАЧЁТНОЙ КНИЖКИ:")
        print(error)
        return

    print(f"\nНайдено долгов: {len(debts)}\n")

    if not debts:
        print("Долгов не найдено.")
        return

    print("-" * 70)

    for index, debt in enumerate(debts, start=1):

        print(f"\n{index}. {debt.subject}")

        print(f"   Контроль:       {debt.control_type}")

        # Показываем исходный результат
        if debt.grade:
            print(f"   Результат:      {debt.grade}")
        else:
            print("   Результат:      — (оценка отсутствует)")

        # Показываем человеческое описание проблемы
        print(f"   Тип долга:      {debt.debt_type}")

        if debt.teacher:
            print(f"   Преподаватель:  {debt.teacher}")
        else:
            print("   Преподаватель:  НЕ УКАЗАН")

        if debt.hours:
            print(f"   Часы:           {debt.hours}")

        if debt.credits:
            print(f"   Зачётные ед.:   {debt.credits}")

        print("-" * 70)


if __name__ == "__main__":
    main()