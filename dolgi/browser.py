"""Автоматизация сайта БГПУ через Playwright.

Логика авторизации, поиска преподавателей и сбора расписаний
перенесена из рабочей версии без изменений. Добавлен сбор
расписания собственной группы.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

import playwright
from playwright.sync_api import Page, sync_playwright

from . import config, storage
from .models import Debt, ScheduleEntry, ZachetkaInfo
from .parsing import parse_schedule_html, parse_zachetka_html

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[Optional[float]], None]


def _browsers_dir() -> Path:
    """Стандартное хранилище браузеров Playwright."""
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")

    if env and env != "0":
        return Path(env)

    local_app_data = os.getenv("LOCALAPPDATA")

    if local_app_data:
        return Path(local_app_data) / "ms-playwright"

    return Path.home() / "AppData" / "Local" / "ms-playwright"


def _ensure_browsers_path() -> None:
    """Направляет playwright в стандартное хранилище браузеров.

    В собранном exe playwright выставляет PLAYWRIGHT_BROWSERS_PATH=0
    и ищет браузеры во временной папке распаковки, где их нет.
    Задаём стандартный путь заранее — тогда переопределения не будет.
    """
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")

    if env and env != "0":
        return

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_dir())


def _browsers_ready() -> bool:
    """Установлены ли браузеры Chromium (обычный и headless-shell)."""
    browsers = _browsers_dir()

    if not browsers.exists():
        return False

    has_chromium = any(browsers.glob("chromium-*/**/chrome.exe"))
    has_headless = any(
        browsers.glob("chromium_headless_shell-*/**/chrome-headless-shell.exe")
    )

    return has_chromium and has_headless


def _install_browsers(on_log: Optional[LogCallback] = None) -> None:
    """Скачивает Chromium через драйвер Playwright (один раз).

    Драйвер уже упакован в приложение, поэтому пользователю
    не нужен ни Python, ни установка чего-либо вручную.
    Вывод скачивания пишется в журнал.
    """
    driver_dir = Path(playwright.__file__).parent / "driver"
    node = driver_dir / ("node.exe" if os.name == "nt" else "node")
    cli = driver_dir / "package" / "cli.js"

    if not node.exists() or not cli.exists():
        raise RuntimeError(
            "Драйвер Playwright не найден — не могу скачать браузер."
        )

    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_dir())

    process = subprocess.Popen(
        [str(node), str(cli), "install", "chromium"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    for line in process.stdout:  # type: ignore[union-attr]
        line = line.strip()

        if line:
            _log(on_log, f"  {line}")

    process.wait()

    if process.returncode != 0:
        raise RuntimeError(
            f"Не удалось скачать браузер Chromium (код {process.returncode}). "
            "Проверь интернет и попробуй ещё раз."
        )

    if not _browsers_ready():
        raise RuntimeError("Браузер скачался, но не найден на диске.")


def _log(on_log: Optional[LogCallback], message: str) -> None:
    if on_log is not None:
        on_log(message)


# ----------------------------------------------------------------------
# Вход в личный кабинет
# ----------------------------------------------------------------------


def login_to_bspu(page: Page, on_log: Optional[LogCallback] = None) -> Page:
    _log(on_log, "Открываю сайт БГПУ...")

    page.goto(
        config.SITE_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    _log(on_log, "Сайт открыт. Ищу «Личный кабинет»...")

    cabinet = page.get_by_text("Личный кабинет", exact=True)

    if cabinet.count() == 0:
        raise RuntimeError("Не удалось найти «Личный кабинет».")

    cabinet.first.click()

    page.wait_for_url("**/WebApp/**", timeout=15000)

    _log(on_log, "Личный кабинет открыт. Жду форму авторизации...")

    login_input = page.locator('input[name="login"]')
    password_input = page.locator('input[name="password"]')
    checkbox = page.locator("#input-51")
    login_button = page.get_by_role("button", name="ВОЙТИ")

    login_input.wait_for(state="visible", timeout=15000)
    password_input.wait_for(state="visible", timeout=15000)
    checkbox.wait_for(state="attached", timeout=15000)
    login_button.wait_for(state="visible", timeout=15000)

    login, password = config.get_credentials()

    if not login:
        raise RuntimeError("Не найден BSPU_LOGIN в файле .env")

    if not password:
        raise RuntimeError("Не найден BSPU_PASSWORD в файле .env")

    login_input.fill(login)
    password_input.fill(password)

    if not checkbox.is_checked():
        checkbox.locator("xpath=..").click(force=True, timeout=5000)

    page.wait_for_timeout(500)

    if not checkbox.is_checked():
        raise RuntimeError("Не удалось установить галочку согласия.")

    login_button.click(timeout=5000, force=True)

    page.wait_for_timeout(4000)

    _log(on_log, "Авторизация выполнена.")

    return page


# ----------------------------------------------------------------------
# Зачётная книжка
# ----------------------------------------------------------------------


def fetch_zachetka_html(page: Page, on_log: Optional[LogCallback] = None) -> str:
    """Открывает страницу «Зачётная книжка» и возвращает её HTML.

    Сайт по умолчанию показывает только текущий семестр,
    поэтому сбрасываем фильтры — иначе долги прошлых
    семестров на страницу не попадают.
    """
    _log(on_log, "Открываю зачётную книжку...")

    page.goto(
        config.ZACHETKA_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    # Ждём отрисовки таблиц учебного плана.
    try:
        page.wait_for_selector("table", state="visible", timeout=20000)
    except Exception:
        page.wait_for_timeout(3000)

    page.wait_for_timeout(1000)

    # Сбрасываем фильтры периода: «Семестр», «Курс», «Вид контроля».
    clear_buttons = page.locator('button[aria-label^="Clear"]')

    if clear_buttons.count():
        for index in range(clear_buttons.count()):
            try:
                label = clear_buttons.nth(index).get_attribute("aria-label")
                clear_buttons.nth(index).click(timeout=5000)
                page.wait_for_timeout(1500)
                _log(on_log, f"Сброшен фильтр: {label}")
            except Exception:
                continue

        page.wait_for_timeout(2000)

    html = page.content()

    _log(on_log, f"Зачётная книжка загружена ({len(html)} символов).")

    return html


def _ensure_browsers_installed(on_log: Optional[LogCallback] = None) -> None:
    """Проверяет браузер и при необходимости один раз его скачивает."""
    _ensure_browsers_path()

    if _browsers_ready():
        return

    _log(on_log, "Браузер Chromium не найден. Один раз скачиваю (~250 МБ)...")
    _install_browsers(on_log)
    _log(on_log, "Браузер Chromium готов.")


def fetch_debts(
    headless: bool = True,
    on_log: Optional[LogCallback] = None,
) -> tuple[ZachetkaInfo, list[Debt]]:
    """Авторизуется, загружает зачётную книжку и разбирает долги."""
    config.load_env()
    _ensure_browsers_installed(on_log)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)

        page = browser.new_page(
            viewport={"width": 1400, "height": 900},
        )

        try:
            login_to_bspu(page, on_log)
            html = fetch_zachetka_html(page, on_log)
            info, debts = parse_zachetka_html(html)
        finally:
            browser.close()

    _log(on_log, f"Найдено долгов: {len(debts)}.")

    return info, debts


# ----------------------------------------------------------------------
# Расписание: общие шаги
# ----------------------------------------------------------------------


def open_schedule(page: Page, on_log: Optional[LogCallback] = None) -> Page:
    """Открывает раздел «Расписание»."""
    schedule_link = page.get_by_text("Расписание", exact=True)

    if schedule_link.count() == 0:
        raise RuntimeError("Не удалось найти пункт «Расписание».")

    schedule_link.first.click(force=True)
    page.wait_for_timeout(2500)

    _log(on_log, "Раздел «Расписание» открыт.")

    return page


def open_teacher_mode(page: Page, on_log: Optional[LogCallback] = None) -> Page:
    """Переключает страницу расписания в режим «ПО ПРЕПОДАВАТЕЛЯМ»."""
    teacher_button = page.get_by_role("button", name="ПО ПРЕПОДАВАТЕЛЯМ")

    if teacher_button.count() == 0:
        teacher_button = page.get_by_text("ПО ПРЕПОДАВАТЕЛЯМ", exact=True)

    if teacher_button.count() == 0:
        raise RuntimeError("Не удалось найти кнопку «ПО ПРЕПОДАВАТЕЛЯМ».")

    teacher_button.first.click(force=True)
    page.wait_for_timeout(1200)

    return page


def open_group_mode(page: Page, on_log: Optional[LogCallback] = None) -> Page:
    """Переключает страницу расписания в режим «ПО ГРУППАМ»."""
    group_button = page.get_by_role("button", name="ПО ГРУППАМ")

    if group_button.count() == 0:
        group_button = page.get_by_text("ПО ГРУППАМ", exact=True)

    if group_button.count() == 0:
        raise RuntimeError("Не удалось найти кнопку «ПО ГРУППАМ».")

    group_button.first.click(force=True)
    page.wait_for_timeout(1200)

    return page


# ----------------------------------------------------------------------
# Поиск преподавателя
# ----------------------------------------------------------------------


def get_teacher_search_query(teacher_name: str) -> str:
    """Фамилия для поиска.

    Дяминова Э.И. -> Дяминова
    А.И. Чигрина -> Чигрина
    """
    parts = teacher_name.split()

    if not parts:
        return ""

    first_part = parts[0]

    if "." in first_part:
        return parts[-1]

    return first_part


def normalize_initials(value: str) -> str:
    """'Л.И.' -> 'ЛИ', 'Лилия Ивановна' -> ''."""
    return "".join(
        char.upper()
        for char in value
        if char.isalpha() and char.isupper()
    )


def get_teacher_initials(teacher_name: str) -> str:
    """Васильева Л.И. -> ЛИ, А.И. Чигрина -> АИ."""
    parts = teacher_name.split()

    for part in parts:
        if "." in part:
            initials = normalize_initials(part)

            if initials:
                return initials

    return ""


def get_full_name_initials(full_name: str) -> str:
    """'Васильева Лилия Ивановна' -> 'ЛИ'."""
    parts = full_name.split()

    if len(parts) < 3:
        return ""

    first_name = parts[1]
    patronymic = parts[2]

    if not first_name or not patronymic:
        return ""

    return first_name[0].upper() + patronymic[0].upper()


def find_teacher_link(page: Page, teacher_name: str) -> dict:
    """Ищет преподавателя в списке и возвращает (имя, ссылку).

    Точное совпадение по инициалам приоритетнее,
    единственный найденный кандидат выбирается автоматически.
    """
    query = get_teacher_search_query(teacher_name)
    requested_initials = get_teacher_initials(teacher_name)

    search = page.locator(
        'div.v-card.v-sheet.v-sheet--outlined:has(i.fas.fa-search) input[type="text"]'
    )

    if search.count() == 0:
        raise RuntimeError("Не найдено поле поиска преподавателей.")

    search = search.first
    search.wait_for(state="visible", timeout=15000)

    search.fill("")
    page.wait_for_timeout(300)
    search.fill(query)

    actual_value = search.input_value()

    if actual_value.strip().lower() != query.strip().lower():
        raise RuntimeError(
            "Фамилия попала не в тот input.\n"
            f"Ожидалось: {query!r}\n"
            f"Получено: {actual_value!r}"
        )

    page.wait_for_timeout(1200)

    teacher_links = page.locator('a[href^="#/Rasp/Teacher/"]').filter(has_text=query)

    count = teacher_links.count()

    if count == 0:
        raise RuntimeError(f"Преподаватель «{teacher_name}» не найден.")

    candidates = []

    for index in range(count):
        link = teacher_links.nth(index)
        actual_name = link.inner_text().strip()

        candidates.append(
            {
                "name": actual_name,
                "href": link.get_attribute("href"),
                "initials": get_full_name_initials(actual_name),
            }
        )

    if requested_initials:
        matches = [
            candidate
            for candidate in candidates
            if candidate["initials"] == requested_initials
        ]

        if len(matches) == 1:
            return {
                "name": matches[0]["name"],
                "href": matches[0]["href"],
            }

        if len(matches) > 1:
            raise RuntimeError(
                f"Найдено несколько преподавателей с одинаковыми "
                f"инициалами для «{teacher_name}»:\n"
                + "\n".join(f"  - {item['name']}" for item in matches)
            )

    if count == 1:
        return {
            "name": candidates[0]["name"],
            "href": candidates[0]["href"],
        }

    candidates_text = "\n".join(
        f"  {index}. {candidate['name']} ({candidate['initials']})"
        for index, candidate in enumerate(candidates, start=1)
    )

    raise RuntimeError(
        f"Не удалось однозначно определить преподавателя «{teacher_name}».\n\n"
        f"Кандидаты:\n{candidates_text}\n\n"
        f"Ожидаемые инициалы: {requested_initials or 'не указаны'}"
    )


# ----------------------------------------------------------------------
# Сбор расписаний
# ----------------------------------------------------------------------


def _page_html(page: Page) -> str:
    body = page.locator("body")
    body.wait_for(state="visible", timeout=15000)
    return page.content()


def collect_teacher_schedule(page: Page, teacher_name: str) -> dict:
    """Открывает страницу преподавателя и возвращает её HTML."""
    teacher = find_teacher_link(page, teacher_name)

    teacher_url = config.APP_URL + teacher["href"]

    page.goto(
        teacher_url,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1800)

    return {
        "query": get_teacher_search_query(teacher_name),
        "requested_name": teacher_name,
        "actual_name": teacher["name"],
        "url": page.url,
        "html": _page_html(page),
    }


def return_to_teacher_list(page: Page, on_log: Optional[LogCallback] = None) -> None:
    """Возвращается к списку расписаний (без page.go_back())."""
    page.goto(
        config.SCHEDULE_LIST_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1500)
    open_teacher_mode(page, on_log)


def collect_teacher_schedules(
    page: Page,
    teachers: list[str],
    on_log: Optional[LogCallback] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, ScheduleEntry]:
    """Собирает расписания всех преподавателей.

    Ошибка по одному преподавателю не останавливает сбор.
    После каждого преподавателя данные сохраняются на диск.
    """
    page.goto(
        config.SCHEDULE_LIST_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1500)
    open_teacher_mode(page, on_log)

    schedule: dict[str, ScheduleEntry] = {}

    for index, teacher in enumerate(teachers, start=1):
        _log(on_log, f"[{index}/{len(teachers)}] {teacher}")

        if on_progress is not None:
            on_progress((index - 1) / len(teachers))

        try:
            result = collect_teacher_schedule(page, teacher)

            entry = parse_schedule_html(
                result["html"],
                owner=teacher,
                kind="teacher",
            )

            entry.actual_name = result["actual_name"]
            entry.url = result["url"]

            _log(on_log, f"  Занятий найдено: {len(entry.lessons)}")

        except Exception as error:
            entry = ScheduleEntry(owner=teacher, actual_name=None, error=str(error))
            _log(on_log, f"  Ошибка: {error}")

        schedule[teacher] = entry
        storage.save_schedule(schedule)

        if index < len(teachers):
            try:
                return_to_teacher_list(page, on_log)
            except Exception as recovery_error:
                _log(on_log, f"Не удалось вернуться к списку: {recovery_error}")

                page.goto(
                    config.SCHEDULE_LIST_URL,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                page.wait_for_timeout(1500)
                open_teacher_mode(page, on_log)

    if on_progress is not None:
        on_progress(1.0)

    return schedule


def collect_group_schedule(
    page: Page,
    group: str,
    on_log: Optional[LogCallback] = None,
) -> ScheduleEntry:
    """Собирает расписание собственной группы."""
    _log(on_log, f"Открываю расписание группы {group}...")

    page.goto(
        config.SCHEDULE_LIST_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1500)
    open_schedule(page, on_log)
    open_group_mode(page, on_log)

    query = group.split("(")[0].strip()

    search = page.locator(
        'div.v-card.v-sheet.v-sheet--outlined:has(i.fas.fa-search) input[type="text"]'
    )

    if search.count() == 0:
        raise RuntimeError("Не найдено поле поиска групп.")

    search = search.first
    search.wait_for(state="visible", timeout=15000)
    search.fill("")
    page.wait_for_timeout(300)
    search.fill(query)
    page.wait_for_timeout(1200)

    group_links = page.locator('a[href^="#/Rasp/Group/"]').filter(has_text=query)

    if group_links.count() == 0:
        raise RuntimeError(f"Группа «{group}» не найдена.")

    link = group_links.first

    group_url = config.APP_URL + link.get_attribute("href")

    page.goto(
        group_url,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1800)

    entry = parse_schedule_html(
        _page_html(page),
        owner=group,
        kind="group",
    )

    entry.url = page.url

    _log(on_log, f"  Занятий группы найдено: {len(entry.lessons)}")

    return entry


def fetch_schedules(
    teachers: list[str],
    group: str = "",
    headless: bool = True,
    on_log: Optional[LogCallback] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, ScheduleEntry]:
    """Собирает расписания преподавателей и (опционально) своей группы."""
    config.load_env()
    _ensure_browsers_installed(on_log)

    schedule: dict[str, ScheduleEntry] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)

        page = browser.new_page(
            viewport={"width": 1400, "height": 900},
        )

        try:
            login_to_bspu(page, on_log)

            if teachers:
                schedule.update(
                    collect_teacher_schedules(
                        page,
                        teachers,
                        on_log,
                        on_progress,
                    )
                )

            if group:
                try:
                    entry = collect_group_schedule(page, group, on_log)
                    schedule[group] = entry
                    storage.save_schedule(schedule)
                except Exception as error:
                    schedule[group] = ScheduleEntry(owner=group, error=str(error))
                    storage.save_schedule(schedule)
                    _log(on_log, f"Расписание группы: ошибка — {error}")

        finally:
            browser.close()

    return schedule
