"""Разбор страницы расписания личного кабинета БГПУ.

Страница расписания (по преподавателям или по группам) состоит из
блоков по дням:

    <header>            Вторник        15.09.2026
    <div class="rasp-square">
        <div class="time-square-text"> 08:00 <hr> 09:30 </div>
        <span style="font-weight: bold">лаб Управление IT-проектами, п/г 2</span>
        <span class="v-chip__content">1-е занятие</span>
        <span class="text--secondary"><i class="fas fa-users"></i> ИСИТ-41-23</span>
        <span class="text--secondary"><i class="fas fa-building"></i> Аудитория: 10-307</span>
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import (
    Lesson,
    ScheduleEntry,
    get_building,
    normalize_text,
)

DAY_NAMES = {
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
}

DATE_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

TIME_PATTERN = re.compile(r"\b\d{1,2}:\d{2}\b")

LESSON_TYPES = {
    "лек",
    "лек.",
    "лаб",
    "лаб.",
    "пра",
    "пра.",
    "пр",
    "пр.",
    "сем",
    "сем.",
    "конс",
    "конс.",
    "экз",
    "экз.",
    "зач",
    "зач.",
    "кп",
    "кп.",
    "кр",
    "кр.",
}


def parse_schedule_html(
    html: str,
    owner: str = "",
    kind: str = "teacher",
) -> ScheduleEntry:
    """Разбирает HTML страницы расписания.

    kind = "teacher" — страница преподавателя;
    kind = "group"   — страница группы.
    """
    soup = BeautifulSoup(html, "html.parser")

    entry = ScheduleEntry(owner=owner, actual_name=owner)
    entry.actual_name = _page_title(soup) or owner

    for header, day, date in _iter_day_headers(soup):
        container = _day_container(header)

        for card in container.select("div.rasp-square"):
            lesson = parse_lesson_card(card, day, date, owner, kind)

            if lesson is not None:
                entry.lessons.append(lesson)

    return entry


# ----------------------------------------------------------------------
# Дни
# ----------------------------------------------------------------------


def _iter_day_headers(soup: BeautifulSoup):
    """Отдаёт (header, день недели, дата) для всех дней расписания."""
    for header in soup.find_all("header"):
        titles = [
            normalize_text(item.get_text())
            for item in header.select(".v-toolbar__title")
        ]

        if len(titles) < 2:
            continue

        day, date = titles[0], titles[1]

        if not DATE_PATTERN.match(date):
            continue

        yield header, day, date


def _day_container(header):
    """Поднимается от заголовка дня до контейнера с занятиями этого дня."""
    container = header

    while container.parent is not None:
        parent = container.parent

        if len(parent.find_all("header")) > 1:
            break

        container = parent

    return container


# ----------------------------------------------------------------------
# Занятие
# ----------------------------------------------------------------------


def parse_lesson_card(
    card,
    day: str,
    date: str,
    owner: str,
    kind: str,
) -> Lesson | None:
    start_time, end_time = _card_times(card)

    raw_subject = _card_subject(card)

    if not raw_subject or not start_time:
        return None

    lesson_type, subject = split_lesson_type(raw_subject)

    group = None
    classroom = None
    teacher = ""

    for span in card.select("span.text--secondary"):
        text = normalize_text(span.get_text(" "))
        icon = span.select_one("i")
        icon_class = " ".join(icon.get("class", [])) if icon else ""

        if "fa-users" in icon_class:
            group = text

        elif "fa-user" in icon_class or "fa-id-card" in icon_class:
            # fa-user — карточка преподавателя на странице преподавателя,
            # fa-id-card — преподаватель в карточке занятия на странице группы.
            teacher = text

        elif "fa-building" in icon_class:
            classroom = re.sub(r"^Аудитория:\s*", "", text)

    if not teacher:
        teacher = owner if kind == "teacher" else ""

    return Lesson(
        subject=subject,
        date=date,
        day=day,
        start_time=start_time,
        end_time=end_time,
        teacher=teacher,
        lesson_type=lesson_type,
        group=group,
        classroom=classroom or None,
        building=get_building(classroom),
        number=_card_number(card),
        owner=owner,
    )


def _card_times(card) -> tuple[str, str]:
    """Время занятия хранится в соседнем блоке time-square."""
    container = card.parent

    if container is None:
        return "", ""

    time_block = container.select_one(".time-square-text")

    if time_block is None:
        return "", ""

    times = TIME_PATTERN.findall(time_block.get_text(" ", strip=True))

    if len(times) >= 2:
        return times[0], times[1]

    if len(times) == 1:
        return times[0], ""

    return "", ""


def _card_subject(card) -> str:
    subject_span = card.select_one("span[style*='font-weight']")

    if subject_span is None:
        subject_span = card.find("span")

    if subject_span is None:
        return ""

    return normalize_text(subject_span.get_text(" "))


def _card_number(card) -> str | None:
    chip = card.select_one(".v-chip__content")

    if chip is None:
        return None

    text = normalize_text(chip.get_text(" "))

    return text or None


def split_lesson_type(value: str) -> tuple[str | None, str]:
    """'лаб Управление IT-проектами, п/г 2' -> ('лаб', 'Управление IT-проектами, п/г 2')."""
    value = normalize_text(value)

    if not value:
        return None, ""

    parts = value.split(maxsplit=1)

    if len(parts) == 1:
        return None, parts[0]

    word = parts[0].lower()

    if word in LESSON_TYPES:
        return word.rstrip("."), parts[1]

    return None, value


def _page_title(soup: BeautifulSoup) -> str:
    if soup.title is None:
        return ""

    title = normalize_text(soup.title.get_text())

    if title.endswith(" - Расписание"):
        title = title[: -len(" - Расписание")]

    if title == "Расписание":
        return ""

    return title
