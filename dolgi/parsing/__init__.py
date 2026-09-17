"""Разбор HTML-страниц личного кабинета БГПУ."""

from .schedule import parse_schedule_html
from .zachetka import parse_zachetka_html

__all__ = [
    "parse_schedule_html",
    "parse_zachetka_html",
]
