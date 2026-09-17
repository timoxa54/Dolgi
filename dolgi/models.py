"""Модели данных: долг, занятие, вариант дня, итоговый план."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

# ----------------------------------------------------------------------
# Оценки и типы задолженностей
# ----------------------------------------------------------------------

GOOD_GRADES = {
    "зачет",
    "зачёт",
    "зачтено",
    "удовл",
    "удовлетворительно",
    "хорошо",
    "отлично",
}

GRADE_OPTIONS = [
    "",
    "Н/я",
    "Неуд",
    "Незачет",
    "Зачет",
    "Удовл",
    "Хорошо",
    "Отлично",
]

DEBT_TYPE_EMPTY = "Оценка отсутствует"
DEBT_TYPE_ABSENT = "Неявка"
DEBT_TYPE_BAD = "Неудовлетворительная оценка"
DEBT_TYPE_FAIL = "Незачёт"

# Типы долгов для тумблеров интерфейса: (ключ, подпись, значение debt_type).
# «Пусто» по умолчанию выключен — пустые оценки часто спорные,
# а в текущем периоде это вообще предстоящая сессия.
DEBT_TYPE_FILTERS = [
    ("nezachet", "Незачет", DEBT_TYPE_FAIL),
    ("nyaa", "Н/я", DEBT_TYPE_ABSENT),
    ("neud", "Неуд", DEBT_TYPE_BAD),
    ("empty", "Пусто", DEBT_TYPE_EMPTY),
]

DEFAULT_DEBT_TYPES = {
    "nezachet": True,
    "nyaa": True,
    "neud": True,
    "empty": False,
}


def normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def debt_type_by_grade(grade: str) -> Optional[str]:
    """Определяет тип задолженности по оценке.

    Возвращает None, если результат положительный (долга нет).
    """
    value = normalize_text(grade).lower()

    if not value:
        return DEBT_TYPE_EMPTY

    if value in {"н/я", "н/а", "неявка", "неяв"}:
        return DEBT_TYPE_ABSENT

    if value in {"неуд", "неудовлетворительно"}:
        return DEBT_TYPE_BAD

    if value in {"незачет", "незачёт", "не зачтено", "незачтено"}:
        return DEBT_TYPE_FAIL

    if value in GOOD_GRADES:
        return None

    if "неуд" in value:
        return DEBT_TYPE_BAD

    if "незач" in value:
        return DEBT_TYPE_FAIL

    if "неяв" in value:
        return DEBT_TYPE_ABSENT

    return f"Проблемный результат: {grade}"


def is_debt_grade(grade: str) -> bool:
    return debt_type_by_grade(grade) is not None


# ----------------------------------------------------------------------
# Долг
# ----------------------------------------------------------------------


@dataclass
class Debt:
    """Академическая задолженность.

    Единственный источник правды по типу долга — поле grade.
    debt_type всегда вычисляется из него.
    """

    subject: str
    teacher: str = ""
    grade: str = ""
    control_type: str = "Неизвестно"
    course: Optional[int] = None
    semester: Optional[int] = None
    year: str = ""
    hours: str = ""
    credits: str = ""
    tracked: bool = True
    source: str = "bspu"
    id: str = ""

    def __post_init__(self) -> None:
        self.subject = normalize_text(self.subject)
        self.teacher = normalize_text(self.teacher)
        self.grade = normalize_text(self.grade)

        if not self.id:
            self.id = make_debt_id(self)

    # ------------------------------------------------------------------
    # Производные свойства
    # ------------------------------------------------------------------

    @property
    def debt_type(self) -> Optional[str]:
        return debt_type_by_grade(self.grade)

    @property
    def is_debt(self) -> bool:
        return self.debt_type is not None

    @property
    def teachers(self) -> list[str]:
        """Список преподавателей (в зачётке они перечисляются через запятую)."""
        return [
            part.strip()
            for part in self.teacher.split(",")
            if part.strip()
        ]

    @property
    def period(self) -> str:
        parts = []

        if self.course:
            parts.append(f"{self.course} курс")

        if self.semester:
            parts.append(f"{self.semester} семестр")

        if self.year:
            parts.append(self.year)

        return ", ".join(parts)

    # ------------------------------------------------------------------
    # Сериализация
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subject": self.subject,
            "teacher": self.teacher,
            "grade": self.grade,
            "control_type": self.control_type,
            "course": self.course,
            "semester": self.semester,
            "year": self.year,
            "hours": self.hours,
            "credits": self.credits,
            "tracked": self.tracked,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Debt":
        return cls(
            subject=data.get("subject", ""),
            teacher=data.get("teacher", ""),
            grade=data.get("grade", ""),
            control_type=data.get("control_type", "Неизвестно"),
            course=data.get("course"),
            semester=data.get("semester"),
            year=data.get("year", ""),
            hours=data.get("hours", ""),
            credits=data.get("credits", ""),
            tracked=data.get("tracked", True),
            source=data.get("source", "bspu"),
            id=data.get("id", ""),
        )


def make_debt_id(debt: Debt) -> str:
    """Стабильный идентификатор долга — чтобы правки не терялись между загрузками."""
    raw = "|".join(
        [
            debt.subject.lower(),
            (debt.teacher or "").lower(),
            str(debt.course or ""),
            str(debt.semester or ""),
            debt.control_type.lower(),
        ]
    )

    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]

    return f"d{digest}"


# ----------------------------------------------------------------------
# Занятие
# ----------------------------------------------------------------------


@dataclass
class Lesson:
    subject: str
    date: str = ""
    day: str = ""
    start_time: str = ""
    end_time: str = ""
    teacher: str = ""
    lesson_type: Optional[str] = None
    group: Optional[str] = None
    classroom: Optional[str] = None
    building: Optional[str] = None
    number: Optional[str] = None
    owner: str = ""

    @property
    def start_minutes(self) -> int:
        return time_to_minutes(self.start_time)

    @property
    def end_minutes(self) -> int:
        return time_to_minutes(self.end_time)

    @property
    def time_range(self) -> str:
        return f"{self.start_time}–{self.end_time}"

    @property
    def location(self) -> str:
        if self.building and self.classroom:
            return f"корпус {self.building}, {self.classroom}"

        if self.classroom:
            return self.classroom

        if self.building:
            return f"корпус {self.building}"

        return "место не определено"

    def overlaps(self, other: "Lesson") -> bool:
        if self.date != other.date:
            return False

        return (
            self.start_minutes < other.end_minutes
            and other.start_minutes < self.end_minutes
        )

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "date": self.date,
            "day": self.day,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "teacher": self.teacher,
            "lesson_type": self.lesson_type,
            "group": self.group,
            "classroom": self.classroom,
            "building": self.building,
            "number": self.number,
            "owner": self.owner,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Lesson":
        return cls(
            subject=data.get("subject", ""),
            date=data.get("date", ""),
            day=data.get("day", ""),
            start_time=data.get("start_time", ""),
            end_time=data.get("end_time", ""),
            teacher=data.get("teacher", ""),
            lesson_type=data.get("lesson_type"),
            group=data.get("group"),
            classroom=data.get("classroom"),
            building=data.get("building"),
            number=data.get("number"),
            owner=data.get("owner", ""),
        )


def time_to_minutes(value: str) -> int:
    """'08:00' -> 480."""
    try:
        hour, minute = value.split(":")[:2]
        return int(hour) * 60 + int(minute)
    except (ValueError, AttributeError):
        return 0


def get_building(classroom: Optional[str]) -> Optional[str]:
    """Определяет номер корпуса по строке аудитории.

    '10-307 (комп.)' -> '10'
    '2-202'          -> '2'
    """
    import re

    if not classroom:
        return None

    match = re.match(r"^(\d+)\s*[-–—]", classroom.strip())

    if match:
        return match.group(1)

    return None


# ----------------------------------------------------------------------
# Результаты сопоставления и оптимизации
# ----------------------------------------------------------------------


@dataclass
class Candidate:
    """Занятие, которое может закрыть конкретный долг."""

    debt_index: int
    debt: Debt
    lesson: Lesson
    match_type: str = ""

    @property
    def date(self) -> str:
        return self.lesson.date

    @property
    def start_minutes(self) -> int:
        return self.lesson.start_minutes

    @property
    def end_minutes(self) -> int:
        return self.lesson.end_minutes


@dataclass
class ScheduleEntry:
    """Расписание одного владельца: преподавателя или группы."""

    owner: str
    actual_name: str = ""
    url: str = ""
    lessons: list[Lesson] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return not self.error

    def to_dict(self) -> dict:
        return {
            "owner": self.owner,
            "actual_name": self.actual_name,
            "url": self.url,
            "error": self.error,
            "lessons": [lesson.to_dict() for lesson in self.lessons],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduleEntry":
        return cls(
            owner=data.get("owner", ""),
            actual_name=data.get("actual_name", ""),
            url=data.get("url", ""),
            error=data.get("error"),
            lessons=[
                Lesson.from_dict(item)
                for item in data.get("lessons", [])
            ],
        )


@dataclass
class ZachetkaInfo:
    """Сведения о студенте, полученные из зачётной книжки."""

    student: str = ""
    group: str = ""
    book_number: str = ""
    average: str = ""
    direction: str = ""
