import json
import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from parser import parse_zachetka
from schedule_parser import (
    parse_teacher_schedule,
    lessons_to_dict,
)


SITE_URL = "https://asu.bspu.ru/"
SCHEDULE_LIST_URL = "https://asu.bspu.ru/WebApp/#/Rasp/List"
ZACHETKA_FILE = "Зачётная книжка.html"


def save_schedule_data(schedule_data):
    """
    Сохраняет уже обработанные расписания
    в schedule.json.
    """

    output_path = (
        Path(__file__).parent
        / "schedule.json"
    )

    output_path.write_text(
        json.dumps(
            schedule_data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "\n✓ Расписание сохранено:"
        f"\n  {output_path}"
    )


def login_to_bspu(page):
    print("=" * 70)
    print("АВТОМАТИЧЕСКИЙ ВХОД В ЛИЧНЫЙ КАБИНЕТ БГПУ")
    print("=" * 70)

    print("\nОткрываю сайт БГПУ...")

    page.goto(
        SITE_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    print("Сайт открыт.")
    print("URL:", page.url)

    print("\nИщу «Личный кабинет»...")

    cabinet = page.get_by_text(
        "Личный кабинет",
        exact=True,
    )

    print(
        f"Найдено «Личный кабинет»: "
        f"{cabinet.count()}"
    )

    if cabinet.count() == 0:
        raise RuntimeError(
            "Не удалось найти «Личный кабинет»."
        )

    print("Открываю личный кабинет...")

    cabinet.first.click()

    page.wait_for_url(
        "**/WebApp/**",
        timeout=15000,
    )

    print("Личный кабинет открыт.")
    print("URL:", page.url)

    print(
        "\nЖду загрузки формы авторизации..."
    )

    login_input = page.locator(
        'input[name="login"]'
    )

    password_input = page.locator(
        'input[name="password"]'
    )

    checkbox = page.locator(
        "#input-51"
    )

    login_button = page.get_by_role(
        "button",
        name="ВОЙТИ",
    )

    login_input.wait_for(
        state="visible",
        timeout=15000,
    )

    password_input.wait_for(
        state="visible",
        timeout=15000,
    )

    checkbox.wait_for(
        state="attached",
        timeout=15000,
    )

    login_button.wait_for(
        state="visible",
        timeout=15000,
    )

    login = os.getenv("BSPU_LOGIN")
    password = os.getenv("BSPU_PASSWORD")

    if not login:
        raise RuntimeError(
            "Не найден BSPU_LOGIN в файле .env"
        )

    if not password:
        raise RuntimeError(
            "Не найден BSPU_PASSWORD в файле .env"
        )

    print(
        "Форма авторизации загружена."
    )

    print("\nВвожу логин...")
    login_input.fill(login)

    print("Ввожу пароль...")
    password_input.fill(password)

    print(
        "\nСтавлю галочку согласия..."
    )

    if not checkbox.is_checked():

        checkbox_container = checkbox.locator(
            "xpath=.."
        )

        checkbox_container.click(
            force=True,
            timeout=5000,
        )

    page.wait_for_timeout(500)

    print(
        "Галочка установлена:",
        checkbox.is_checked(),
    )

    if not checkbox.is_checked():
        raise RuntimeError(
            "Не удалось установить "
            "галочку согласия."
        )

    print(
        "\nНажимаю «ВОЙТИ»..."
    )

    login_button.click(
        timeout=5000,
        force=True,
    )

    print("Кнопка нажата!")

    print(
        "\nЖду результат авторизации..."
    )

    page.wait_for_timeout(4000)

    print(
        "\nАвторизация завершена."
    )

    print(
        "URL:",
        page.url,
    )

    print(
        "TITLE:",
        page.title(),
    )

    return page


def get_debt_teachers():
    """
    Получает долги и список уникальных
    преподавателей из зачётной книжки.
    """

    debts = parse_zachetka(
        ZACHETKA_FILE
    )

    teachers = []

    for debt in debts:

        if not debt.teacher:
            continue

        parts = [
            teacher.strip()
            for teacher in debt.teacher.split(",")
        ]

        for teacher in parts:

            if (
                teacher
                and teacher not in teachers
            ):
                teachers.append(teacher)

    return debts, teachers


def open_schedule(page):
    """
    Открывает раздел «Расписание».
    """

    print("\n" + "=" * 70)
    print("ОТКРЫВАЮ РАСПИСАНИЕ")
    print("=" * 70)

    schedule_link = page.get_by_text(
        "Расписание",
        exact=True,
    )

    print(
        f"\nНайдено элементов «Расписание»: "
        f"{schedule_link.count()}"
    )

    if schedule_link.count() == 0:
        raise RuntimeError(
            "Не удалось найти пункт "
            "«Расписание»."
        )

    print(
        "Открываю расписание..."
    )

    schedule_link.first.click(
        force=True
    )

    page.wait_for_timeout(2500)

    print(
        "Расписание открыто:",
        page.url,
    )

    return page


def open_teacher_mode(page):
    """
    Переключает страницу расписания
    в режим «ПО ПРЕПОДАВАТЕЛЯМ».
    """

    print(
        "\nИщу кнопку "
        "«ПО ПРЕПОДАВАТЕЛЯМ»..."
    )

    teacher_button = page.get_by_role(
        "button",
        name="ПО ПРЕПОДАВАТЕЛЯМ",
    )

    if teacher_button.count() == 0:

        teacher_button = page.get_by_text(
            "ПО ПРЕПОДАВАТЕЛЯМ",
            exact=True,
        )

    print(
        "Найдено:",
        teacher_button.count(),
    )

    if teacher_button.count() == 0:
        raise RuntimeError(
            "Не удалось найти кнопку "
            "«ПО ПРЕПОДАВАТЕЛЯМ»."
        )

    print(
        "Переключаюсь "
        "на расписание преподавателей..."
    )

    teacher_button.first.click(
        force=True,
    )

    page.wait_for_timeout(1200)

    return page


def get_teacher_search_query(
    teacher_name,
):
    """
    Получает фамилию преподавателя
    для поиска.

    Примеры:

    Дяминова Э.И. -> Дяминова
    Жилко Е.П. -> Жилко
    Филиппова А.С. -> Филиппова
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
    """
    Извлекает инициалы из строки.

    Примеры:
        'Л.И.' -> 'ЛИ'
        'Л. И.' -> 'ЛИ'
        'Лилия Ивановна' -> ''
    """

    return "".join(
        char.upper()
        for char in value
        if char.isalpha() and char.isupper()
    )


def get_teacher_initials(teacher_name: str) -> str:
    """
    Получает инициалы из записи зачётной книжки.

    Примеры:

        Васильева Л.И. -> ЛИ
        Курбангалеева К.Р. -> КР
        А.И. Чигрина -> АИ
    """

    parts = teacher_name.split()

    for part in parts:
        if "." in part:
            initials = normalize_initials(part)

            if initials:
                return initials

    return ""


def get_full_name_initials(full_name: str) -> str:
    """
    Получает инициалы из полного ФИО.

    Пример:

        Васильева Лилия Ивановна
        -> ЛИ
    """

    parts = full_name.split()

    if len(parts) < 3:
        return ""

    first_name = parts[1]
    patronymic = parts[2]

    if not first_name or not patronymic:
        return ""

    return (
        first_name[0].upper()
        + patronymic[0].upper()
    )
def find_teacher_link(
    page,
    teacher_name,
):
    query = get_teacher_search_query(
        teacher_name
    )

    requested_initials = (
        get_teacher_initials(
            teacher_name
        )
    )

    print(
        f"\nИщу преподавателя: "
        f"«{query}»"
    )

    print(
        f"Инициалы: "
        f"{requested_initials or 'не указаны'}"
    )

    search = page.locator(
        'div.v-card.v-sheet.v-sheet--outlined:has(i.fas.fa-search) input[type="text"]'
    )

    if search.count() == 0:
        raise RuntimeError(
            "Не найдено поле поиска "
            "преподавателей."
        )

    search = search.first

    search.wait_for(
        state="visible",
        timeout=15000,
    )

    print(
        "✓ Найден именно input "
        "поиска преподавателей."
    )

    print(
        "ID input:",
        search.get_attribute("id"),
    )

    search.fill("")

    page.wait_for_timeout(300)

    print(
        f"Ввожу фамилию: {query}"
    )

    search.fill(query)

    actual_value = search.input_value()

    print(
        "Значение поля:",
        actual_value,
    )

    if (
        actual_value.strip().lower()
        != query.strip().lower()
    ):
        raise RuntimeError(
            "Фамилия попала не в тот input.\n"
            f"Ожидалось: {query!r}\n"
            f"Получено: {actual_value!r}"
        )

    page.wait_for_timeout(1200)

    teacher_links = page.locator(
        'a[href^="#/Rasp/Teacher/"]'
    ).filter(
        has_text=query
    )

    count = teacher_links.count()

    print(
        f"Найдено преподавателей: {count}"
    )

    if count == 0:
        raise RuntimeError(
            f"Преподаватель "
            f"«{teacher_name}» "
            f"не найден."
        )

    candidates = []

    for index in range(count):

        link = teacher_links.nth(index)

        actual_name = (
            link
            .inner_text()
            .strip()
        )

        href = link.get_attribute(
            "href"
        )

        actual_initials = (
            get_full_name_initials(
                actual_name
            )
        )

        candidates.append(
            {
                "name": actual_name,
                "href": href,
                "initials": actual_initials,
            }
        )

        print(
            f"  Кандидат {index + 1}: "
            f"{actual_name} "
            f"({actual_initials})"
        )

    # -------------------------------------------------
    # 1. Ищем точное совпадение по инициалам
    # -------------------------------------------------

    if requested_initials:

        matches = [
            candidate
            for candidate in candidates
            if candidate["initials"]
            == requested_initials
        ]

        if len(matches) == 1:

            teacher = matches[0]

            print(
                f"✓ Найдено точное совпадение "
                f"по инициалам: "
                f"{teacher['name']}"
            )

            print(
                f"✓ Ссылка: "
                f"{teacher['href']}"
            )

            return {
                "name": teacher["name"],
                "href": teacher["href"],
            }

        if len(matches) > 1:

            raise RuntimeError(
                f"Найдено несколько преподавателей "
                f"с одинаковыми инициалами "
                f"для «{teacher_name}»:\n"
                + "\n".join(
                    f"  - {item['name']}"
                    for item in matches
                )
            )

    # -------------------------------------------------
    # 2. Если преподаватель только один —
    #    можно безопасно выбрать его
    # -------------------------------------------------

    if count == 1:

        teacher = candidates[0]

        print(
            f"✓ Единственный найденный "
            f"преподаватель: "
            f"{teacher['name']}"
        )

        print(
            f"✓ Ссылка: "
            f"{teacher['href']}"
        )

        return {
            "name": teacher["name"],
            "href": teacher["href"],
        }

    # -------------------------------------------------
    # 3. Несколько кандидатов,
    #    но определить нужного нельзя
    # -------------------------------------------------

    candidates_text = "\n".join(
        f"  {index}. "
        f"{candidate['name']} "
        f"({candidate['initials']})"
        for index, candidate
        in enumerate(
            candidates,
            start=1,
        )
    )

    raise RuntimeError(
        f"Не удалось однозначно определить "
        f"преподавателя «{teacher_name}».\n\n"
        f"Кандидаты:\n"
        f"{candidates_text}\n\n"
        f"Ожидаемые инициалы: "
        f"{requested_initials or 'не указаны'}"
    )

def collect_teacher_schedule(
    page,
    teacher_name,
):
    """
    Собирает сырое расписание одного
    преподавателя.

    Возвращает:

    query
    requested_name
    actual_name
    url
    text
    error
    """

    teacher = find_teacher_link(
        page,
        teacher_name,
    )

    href = teacher["href"]

    teacher_url = (
        "https://asu.bspu.ru/WebApp/"
        + href
    )

    print(
        "\nПереход к расписанию:"
    )

    print(
        teacher_url
    )

    page.goto(
        teacher_url,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1800)

    print(
        "\n✓ Страница преподавателя "
        "открыта."
    )

    print(
        "URL:",
        page.url,
    )

    body = page.locator(
        "body"
    )

    body.wait_for(
        state="visible",
        timeout=15000,
    )

    page_text = body.inner_text(
        timeout=10000
    )

    print(
        f"✓ Получено текста: "
        f"{len(page_text)} символов"
    )

    return {
        "query": get_teacher_search_query(
            teacher_name
        ),
        "requested_name": teacher_name,
        "actual_name": teacher["name"],
        "url": page.url,
        "text": page_text,
        "error": None,
    }


def return_to_teacher_list(page):
    """
    Возвращает браузер на список
    расписаний.

    Важно:
    НЕ используем page.go_back().
    """

    print(
        "\nВозвращаюсь "
        "к списку преподавателей..."
    )

    page.goto(
        SCHEDULE_LIST_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1500)

    print(
        "✓ Список расписаний открыт:"
    )

    print(
        page.url
    )

    open_teacher_mode(page)

    print(
        "✓ Режим "
        "«ПО ПРЕПОДАВАТЕЛЯМ» готов."
    )


def collect_teacher_schedules(
    page,
    teachers,
):
    """
    Собирает расписания всех преподавателей.

    Для каждого преподавателя:

    1. Ищет преподавателя.
    2. Открывает его расписание.
    3. Получает сырой текст.
    4. Парсит его в Lesson.
    5. Сохраняет структурированные данные.
    6. Записывает schedule.json.

    Если преподаватель не найден,
    это не останавливает программу.
    """

    print("\n" + "=" * 70)
    print("СБОР РАСПИСАНИЙ ПРЕПОДАВАТЕЛЕЙ")
    print("=" * 70)

    page.goto(
        SCHEDULE_LIST_URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1500)

    open_teacher_mode(page)

    schedule_data = {}

    for index, teacher in enumerate(
        teachers,
        start=1,
    ):
        print("\n" + "-" * 70)

        print(
            f"[{index}/{len(teachers)}] "
            f"{teacher}"
        )

        try:

            result = collect_teacher_schedule(
                page,
                teacher,
            )

            # -----------------------------------------
            # Парсим расписание
            # -----------------------------------------

            lessons = parse_teacher_schedule(
                result["actual_name"],
                result["text"],
            )

            print(
                f"✓ Найдено занятий: "
                f"{len(lessons)}"
            )

            # -----------------------------------------
            # Сохраняем структурированные данные
            # -----------------------------------------

            schedule_data[teacher] = {
                "query": result["query"],
                "requested_name": (
                    result["requested_name"]
                ),
                "actual_name": (
                    result["actual_name"]
                ),
                "url": result["url"],
                "error": result["error"],
                "lessons": lessons_to_dict(
                    lessons
                ),
            }

        except Exception as error:

            print(
                f"✗ Ошибка: {error}"
            )

            schedule_data[teacher] = {
                "query": get_teacher_search_query(
                    teacher
                ),
                "requested_name": teacher,
                "actual_name": None,
                "url": None,
                "error": str(error),
                "lessons": [],
            }

        # -----------------------------------------
        # Сохраняем сразу после каждого
        # преподавателя.
        # -----------------------------------------

        save_schedule_data(
            schedule_data
        )

        # -----------------------------------------
        # Возвращаемся к списку.
        # -----------------------------------------

        if index < len(teachers):

            try:

                return_to_teacher_list(
                    page
                )

            except Exception as recovery_error:

                print(
                    "\n⚠ Не удалось "
                    "вернуться к списку:"
                )

                print(
                    recovery_error
                )

                print(
                    "\nПробую открыть список "
                    "расписаний заново..."
                )

                page.goto(
                    SCHEDULE_LIST_URL,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                page.wait_for_timeout(1500)

                open_teacher_mode(page)

    return schedule_data


def print_collection_result(
    schedules,
    teachers,
):
    """
    Выводит итог сбора расписаний.
    """

    print("\n" + "=" * 70)
    print("РЕЗУЛЬТАТ СБОРА РАСПИСАНИЙ")
    print("=" * 70)

    found = 0
    errors = 0
    total_lessons = 0

    for teacher_name in teachers:

        schedule = schedules.get(
            teacher_name
        )

        if not schedule:

            print(
                f"\n✗ {teacher_name}"
            )

            print(
                "  Результат отсутствует."
            )

            errors += 1
            continue

        lessons = schedule.get(
            "lessons",
            [],
        )

        error = schedule.get(
            "error"
        )

        if error:

            print(
                f"\n⚠ {teacher_name}"
            )

            print(
                f"  Ошибка: {error}"
            )

            print(
                "  Занятий: 0"
            )

            errors += 1

            continue

        print(
            f"\n✓ {teacher_name}"
        )

        print(
            f"  Фактическое имя: "
            f"{schedule.get('actual_name')}"
        )

        print(
            f"  Занятий: "
            f"{len(lessons)}"
        )

        print(
            f"  URL: "
            f"{schedule.get('url')}"
        )

        found += 1
        total_lessons += len(lessons)

    print("\n" + "-" * 70)

    print(
        f"Преподавателей с расписанием: "
        f"{found}"
    )

    print(
        f"Преподавателей без расписания: "
        f"{errors}"
    )

    print(
        f"Всего найдено занятий: "
        f"{total_lessons}"
    )

    print(
        "\n✓ Структурированные данные:"
        "\n  schedule.json"
    )


def main():

    load_dotenv()

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=False,
        )

        page = browser.new_page(
            viewport={
                "width": 1400,
                "height": 900,
            }
        )

        try:

            # =================================================
            # 1. Авторизация
            # =================================================

            login_to_bspu(page)

            # =================================================
            # 2. Получаем долги
            # =================================================

            print("\n" + "=" * 70)
            print("ЗАГРУЖАЮ ДОЛГИ")
            print("=" * 70)

            debts, teachers = (
                get_debt_teachers()
            )

            print(
                f"\nВсего долгов: "
                f"{len(debts)}"
            )

            print(
                f"Уникальных преподавателей: "
                f"{len(teachers)}"
            )

            print(
                "\nПреподаватели:"
            )

            for index, teacher in enumerate(
                teachers,
                start=1,
            ):

                print(
                    f"  {index}. {teacher}"
                )

            # =================================================
            # 3. Открываем расписание
            # =================================================

            open_schedule(page)

            # =================================================
            # 4. Собираем расписания
            # =================================================

            schedules = (
                collect_teacher_schedules(
                    page,
                    teachers,
                )
            )

            # =================================================
            # 5. Итог
            # =================================================

            print_collection_result(
                schedules,
                teachers,
            )

            print("\n" + "=" * 70)
            print("ЭТАП СБОРА ЗАВЕРШЁН")
            print("=" * 70)

            print(
                "\nБраузер оставлен открытым."
            )

            input(
                "\nНажми Enter "
                "для закрытия браузера..."
            )

        except Exception as error:

            print("\n" + "=" * 70)
            print("ОШИБКА")
            print("=" * 70)

            print(
                f"\n{type(error).__name__}: "
                f"{error}"
            )

            input(
                "\nБраузер оставлен открытым "
                "для диагностики.\n"
                "Нажми Enter для закрытия..."
            )

        finally:

            browser.close()


if __name__ == "__main__":
    main()