"""Разбор страницы «Зачётная книжка» личного кабинета БГПУ.

Страница состоит из блоков вида:

    <header><div class="v-toolbar__title">
        2-й курс 4-й семестр 2025-2026 (Экзамен)
    </div></header>
    <div class="v-data-table"><table>...</table></div>

В таблице ровно пять колонок:
    Дисциплина | Кол-во часов | З. ед. | Оценка | Преподаватель
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Debt, ZachetkaInfo, is_debt_grade, normalize_text

# ----------------------------------------------------------------------
# Регулярные выражения
# ----------------------------------------------------------------------

BLOCK_PATTERN = re.compile(
    r"(?P<course>\d+)\s*-\s*й\s+курс\s+"
    r"(?P<semester>\d+)\s*-\s*й\s+семестр\s+"
    r"(?P<year>[\d/\-–]+)\s*"
    r"\((?P<control>[^)]+)\)"
)

BOOK_PATTERN = re.compile(r"Зачётная книжка\s*№\s*(?P<number>[^\s]+)")

AVERAGE_PATTERN = re.compile(r"Средний балл:\s*(?P<value>[\d.,]+)")

AVERAGE_MARKER = re.compile(r"Средний балл")

GROUP_PATTERN = re.compile(r"^[А-ЯЁA-Z0-9][А-ЯЁA-Z0-9_\-.()]*_[А-ЯЁA-Z0-9_\-.()]+$")


def parse_zachetka_html(html: str) -> tuple[ZachetkaInfo, list[Debt]]:
    """Возвращает сведения о студенте и список задолженностей."""
    soup = BeautifulSoup(html, "html.parser")

    info = parse_student_info(soup)
    debts = parse_debt_blocks(soup)

    return info, debts


def period_key(year: str, semester: int) -> tuple[int, int]:
    """Ключ периода для сравнения: (год окончания, семестр).

    '2025-2026', 4 -> (2026, 4)
    """
    years = re.findall(r"\d{4}", year or "")
    end_year = int(years[-1]) if years else 0

    return end_year, semester


# ----------------------------------------------------------------------
# Сведения о студенте
# ----------------------------------------------------------------------


def parse_student_info(soup: BeautifulSoup) -> ZachetkaInfo:
    info = ZachetkaInfo()

    book_match = BOOK_PATTERN.search(soup.get_text(" ", strip=True))

    if book_match:
        info.book_number = book_match.group("number")

    for node in soup.find_all(string=AVERAGE_MARKER):
        if node.parent is not None:
            text = normalize_text(node.parent.get_text(" "))
            value_match = AVERAGE_PATTERN.search(text)

            if value_match:
                info.average = value_match.group("value")
                break

    _parse_student_card(soup, info)

    return info


def _parse_student_card(soup: BeautifulSoup, info: ZachetkaInfo) -> None:
    """Разбирает карточку со ФИО, направлением и группой."""
    card = None

    for header in soup.find_all("header"):
        if "Зачётная книжка" not in header.get_text():
            continue

        if header.parent is None:
            continue

        card = header.parent.find("div", class_="v-card")

        if card is not None:
            break

    if card is not None:
        layouts = card.find_all("div", class_="layout")

        if layouts:
            values = [
                normalize_text(span.get_text())
                for span in layouts[0].find_all("span")
                if normalize_text(span.get_text())
            ]

            if values:
                info.student = values[0]

            if len(values) > 1:
                info.direction = values[1]

        if len(layouts) > 1:
            group_values = [
                normalize_text(span.get_text())
                for span in layouts[1].find_all("span")
                if normalize_text(span.get_text())
            ]

            if group_values:
                info.group = group_values[0]

    if not info.group:
        info.group = _guess_group(soup)


def _guess_group(soup: BeautifulSoup) -> str:
    """Запасной поиск названия группы по всей странице."""
    for span in soup.find_all("span"):
        text = normalize_text(span.get_text())

        if text and GROUP_PATTERN.match(text):
            return text

    return ""


# ----------------------------------------------------------------------
# Долги
# ----------------------------------------------------------------------


def parse_debt_blocks(soup: BeautifulSoup) -> list[Debt]:
    """Собирает долги по всем учебным блокам страницы.

    Зачётная книжка содержит не только долги, но и предстоящую
    (текущую) сессию, где оценки ещё не выставлены. Поэтому:

    * пустая оценка в завершённом периоде — это долг
      «Оценка отсутствует» (учитывается по тумблеру «пусто»);
    * пустая оценка в текущем периоде — предстоящая сессия,
      долгом не считается никогда.
    """
    blocks = list(_iter_blocks(soup))

    if not blocks:
        return []

    current_key = max(
        period_key(block["year"], block["semester"])
        for block in blocks
    )

    debts: list[Debt] = []

    for block in blocks:
        block["is_current"] = period_key(block["year"], block["semester"]) == current_key
        debts.extend(parse_debt_table(block))

    return debts


def _iter_blocks(soup: BeautifulSoup):
    """Отдаёт учебные блоки страницы: курс, семестр, год, вид контроля, таблица."""
    for header in soup.find_all("header"):
        title = header.select_one(".v-toolbar__title")

        if title is None or header.parent is None:
            continue

        match = BLOCK_PATTERN.search(normalize_text(title.get_text()))

        if match is None:
            continue

        table = header.parent.find("table")

        if table is None:
            continue

        yield {
            "table": table,
            "course": int(match.group("course")),
            "semester": int(match.group("semester")),
            "year": match.group("year"),
            "control_type": normalize_text(match.group("control")),
        }


def parse_debt_table(block: dict) -> list[Debt]:
    table = block["table"]

    debts: list[Debt] = []

    for row in table.select("tbody tr"):
        cells = row.find_all("td")

        if len(cells) < 5:
            continue

        subject = normalize_text(cells[0].get_text(" "))
        grade = normalize_text(cells[3].get_text(" "))

        if not subject:
            continue

        # Положительный результат — это не долг.
        if not is_debt_grade(grade):
            continue

        # Пустая оценка в текущем периоде — предстоящая сессия.
        if not grade and block["is_current"]:
            continue

        debts.append(
            Debt(
                subject=subject,
                teacher=normalize_text(cells[4].get_text(" ")),
                grade=grade,
                control_type=block["control_type"],
                course=block["course"],
                semester=block["semester"],
                year=block["year"],
                hours=normalize_text(cells[1].get_text(" ")),
                credits=normalize_text(cells[2].get_text(" ")),
            )
        )

    return debts
