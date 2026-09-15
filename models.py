from dataclasses import dataclass
from typing import Optional


@dataclass
class Debt:
    subject: str
    control_type: str
    grade: str
    teacher: Optional[str] = None
    course: Optional[int] = None
    semester: Optional[int] = None
    year: Optional[str] = None

    debt_type: Optional[str] = None
    hours: Optional[str] = None
    credits: Optional[str] = None


@dataclass
class Lesson:
    teacher: str
    subject: str
    day: str
    date: str
    start_time: str
    end_time: str

    lesson_type: Optional[str] = None
    group: Optional[str] = None
    classroom: Optional[str] = None
    building: Optional[str] = None

    @property
    def start_minutes(self) -> int:
        hour, minute = map(int, self.start_time.split(":"))
        return hour * 60 + minute

    @property
    def end_minutes(self) -> int:
        hour, minute = map(int, self.end_time.split(":"))
        return hour * 60 + minute


@dataclass
class ScheduleOption:
    day: str
    lessons: list[Lesson]
    debt_count: int
    score: float = 0.0