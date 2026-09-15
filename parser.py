from pathlib import Path
from bs4 import BeautifulSoup

from models import Debt


GOOD_GRADES = {
    "зачет",
    "зачёт",
    "удовл",
    "удовлетворительно",
    "хорошо",
    "отлично",
}


def normalize(text: str) -> str:
    return " ".join(text.split()).strip()


def parse_grade(text: str) -> str:
    return normalize(text).lower()


def get_debt_type(grade: str) -> str | None:
    value = parse_grade(grade)

    if not value:
        return "Оценка отсутствует"

    if value in {"н/я", "неявка", "неяв"}:
        return "Неявка"

    if value in {"неуд", "неудовлетворительно"}:
        return "Неудовлетворительная оценка"

    if value in {"незачет", "незачёт"}:
        return "Незачёт"

    if value in GOOD_GRADES:
        return None

    if "неуд" in value:
        return "Неудовлетворительная оценка"

    if "незач" in value:
        return "Незачёт"

    if "неяв" in value:
        return "Неявка"

    return f"Проблемный результат: {grade}"


def find_block_text(table) -> str:
    """
    Ищет ближайший контейнер учебного блока.

    Возвращает небольшой фрагмент текста вокруг таблицы,
    чтобы определить курс и тип контроля.
    """

    parent = table.parent

    for _ in range(8):
        if parent is None:
            break

        text = normalize(parent.get_text(" ", strip=True))

        # Нас интересуют контейнеры, где явно написан курс
        if "курс" in text.lower():
            return text

        parent = parent.parent

    return ""


def get_course_from_text(text: str) -> int | None:
    """
    Определяет курс из текста заголовка.
    """

    text = text.lower()

    import re

    patterns = [
        r"(\d+)\s*-\s*й\s+курс",
        r"(\d+)\s*й\s+курс",
        r"(\d+)\s+курс",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return int(match.group(1))

    return None


def get_control_type_from_text(text: str) -> str:
    """
    Определяет тип контроля по тексту блока.
    """

    text = text.lower()

    if "экзамен" in text:
        return "Экзамен"

    if "зачет" in text or "зачёт" in text:
        return "Зачёт"

    return "Неизвестно"


def parse_zachetka(file_path: str) -> list[Debt]:

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"\nФайл зачётной книжки не найден:\n"
            f"{path.resolve()}\n\n"
            f"Положи файл 'Зачётная книжка.html' "
            f"в папку с main.py."
        )

    html = path.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    soup = BeautifulSoup(html, "html.parser")

    debts: list[Debt] = []

    print("\nАнализ учебных блоков:")

    table_number = 0

    for table in soup.find_all("table"):

        table_number += 1

        # ---------------------------------------------------------
        # Определяем родительский учебный блок
        # ---------------------------------------------------------

        block_text = find_block_text(table)

        course = get_course_from_text(block_text)
        control_type = get_control_type_from_text(block_text)

        print(
            f"  Таблица {table_number}: "
            f"курс={course}, "
            f"контроль={control_type}"
        )

        # ---------------------------------------------------------
        # БЕРЁМ ТОЛЬКО ВТОРОЙ КУРС
        # ---------------------------------------------------------

        if course != 2:
            continue

        # ---------------------------------------------------------
        # Обрабатываем строки
        # ---------------------------------------------------------

        for row in table.find_all("tr"):

            cells = row.find_all("td")

            if len(cells) < 5:
                continue

            subject = normalize(
                cells[0].get_text(" ", strip=True)
            )

            hours = normalize(
                cells[1].get_text(" ", strip=True)
            )

            credits = normalize(
                cells[2].get_text(" ", strip=True)
            )

            grade = normalize(
                cells[3].get_text(" ", strip=True)
            )

            teacher = normalize(
                cells[4].get_text(" ", strip=True)
            )

            if not subject:
                continue

            debt_type = get_debt_type(grade)

            # Положительная оценка
            if debt_type is None:
                continue

            debt = Debt(
                subject=subject,
                control_type=control_type,
                grade=grade,
                teacher=teacher or None,
                course=2,
                debt_type=debt_type,
                hours=hours,
                credits=credits,
            )

            debts.append(debt)

    return debts