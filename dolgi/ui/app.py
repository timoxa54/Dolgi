"""Главное окно приложения Dolgi на CustomTkinter.

Слева: авторизация, кнопки действий, карточки долгов.
Справа: вкладки «План» и «Журнал».

Долгие операции (браузер, оптимизация) выполняются в отдельном потоке,
обновление интерфейса — через очередь сообщений.
"""

from __future__ import annotations

import queue
import threading
from typing import Optional

import customtkinter as ctk

from .. import browser, config, matcher, optimizer, planner, storage
from ..models import (
    DEBT_TYPE_FILTERS,
    GRADE_OPTIONS,
    Debt,
    ScheduleEntry,
    ZachetkaInfo,
)

META_FONT_SIZE = 11

GRADE_CHOICES = [value if value else "— оценка —" for value in GRADE_OPTIONS]

DEBT_TYPE_TO_KEY = {value: key for key, _label, value in DEBT_TYPE_FILTERS}


def bind_text_shortcuts(widget) -> None:
    """Включает Ctrl+C / Ctrl+V / Ctrl+X / Ctrl+A в любой раскладке.

    tkinter привязывает горячие клавиши к символу текущей раскладки:
    в русской раскладке Ctrl+V даёт «м», и стандартная вставка
    не срабатывает. Поэтому ловим клавиши по keycode,
    который не зависит от раскладки.
    """

    def on_key(event):
        if not event.state & 0x0004:  # Control
            return None

        keycode = event.keycode

        if keycode == 86:  # V — вставить
            event.widget.event_generate("<<Paste>>")
        elif keycode == 67:  # C — копировать
            event.widget.event_generate("<<Copy>>")
        elif keycode == 88:  # X — вырезать
            event.widget.event_generate("<<Cut>>")
        elif keycode == 65:  # A — выделить всё
            if hasattr(event.widget, "tag_add"):
                event.widget.tag_add("sel", "1.0", "end")
            elif hasattr(event.widget, "select_range"):
                event.widget.select_range(0, "end")
                event.widget.icursor("end")
        else:
            return None

        return "break"

    widget.bind("<KeyPress>", on_key)


def set_entry_value(entry, value: str) -> None:
    """Записывает значение в поле, не убивая подсказку для пустых значений."""
    if value:
        entry.insert(0, value)


class DebtCard(ctk.CTkFrame):
    """Карточка долга: предмет, преподаватель, оценка, флаг учёта."""

    def __init__(self, master, app: "DolgiApp", debt: Debt):
        super().__init__(master, fg_color=("gray86", "gray17"), corner_radius=8)

        self.app = app
        self.debt = debt

        self.grid_columnconfigure(0, weight=1)

        # --------------------------------------------------------------
        # Ряд 1: предмет + удаление
        # --------------------------------------------------------------

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        top.grid_columnconfigure(0, weight=1)

        self.subject_entry = ctk.CTkEntry(top, placeholder_text="Предмет")
        self.subject_entry.grid(row=0, column=0, sticky="ew")
        set_entry_value(self.subject_entry, debt.subject)
        self.subject_entry.bind("<FocusOut>", self._on_subject_changed)
        self.subject_entry.bind("<Return>", self._on_subject_changed)
        bind_text_shortcuts(self.subject_entry)

        delete_button = ctk.CTkButton(
            top,
            text="✕",
            width=36,
            fg_color="#8b3a3a",
            hover_color="#a04444",
            command=self._on_delete,
        )
        delete_button.grid(row=0, column=1, padx=(6, 0))

        # --------------------------------------------------------------
        # Ряд 2: преподаватель + оценка
        # --------------------------------------------------------------

        middle = ctk.CTkFrame(self, fg_color="transparent")
        middle.grid(row=1, column=0, sticky="ew", padx=8, pady=2)
        middle.grid_columnconfigure(0, weight=1)

        self.teacher_entry = ctk.CTkEntry(middle, placeholder_text="Преподаватель")
        self.teacher_entry.grid(row=0, column=0, sticky="ew")
        set_entry_value(self.teacher_entry, debt.teacher)
        self.teacher_entry.bind("<FocusOut>", self._on_teacher_changed)
        self.teacher_entry.bind("<Return>", self._on_teacher_changed)
        bind_text_shortcuts(self.teacher_entry)

        self.grade_menu = ctk.CTkOptionMenu(
            middle,
            values=GRADE_CHOICES,
            width=120,
            command=self._on_grade_changed,
        )
        self.grade_menu.grid(row=0, column=1, padx=(6, 0))
        self.grade_menu.set(debt.grade if debt.grade else "— оценка —")

        # --------------------------------------------------------------
        # Ряд 3: описание + переключатель учёта
        # --------------------------------------------------------------

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 8))
        bottom.grid_columnconfigure(0, weight=1)

        self.meta_label = ctk.CTkLabel(
            bottom,
            text="",
            anchor="w",
            font=ctk.CTkFont(size=META_FONT_SIZE),
            text_color=("gray40", "gray60"),
        )
        self.meta_label.grid(row=0, column=0, sticky="ew")

        self.tracked_switch = ctk.CTkSwitch(
            bottom,
            text="учитывать",
            width=90,
            command=self._on_tracked_changed,
        )
        self.tracked_switch.grid(row=0, column=1, padx=(6, 0))

        if debt.tracked:
            self.tracked_switch.select()

        self._refresh_meta()

    # ------------------------------------------------------------------
    # Обработчики
    # ------------------------------------------------------------------

    def _on_subject_changed(self, _event=None) -> None:
        value = self.subject_entry.get().strip()

        if value and value != self.debt.subject:
            self.debt.subject = value
            self.app.on_debt_changed()

    def _on_teacher_changed(self, _event=None) -> None:
        value = self.teacher_entry.get().strip()

        if value != self.debt.teacher:
            self.debt.teacher = value
            self.app.on_debt_changed()

    def _on_grade_changed(self, value: str) -> None:
        self.debt.grade = "" if value == "— оценка —" else value
        self._refresh_meta()
        self.app.on_debt_changed()

    def _on_tracked_changed(self) -> None:
        self.debt.tracked = bool(self.tracked_switch.get())
        self.app.on_debt_changed()

    def _on_delete(self) -> None:
        self.app.on_debt_deleted(self.debt, self)

    def _refresh_meta(self) -> None:
        debt_type = self.debt.debt_type or "—"
        self.meta_label.configure(
            text=(
                f"{self.debt.control_type} · "
                f"{self.debt.period or 'период неизвестен'} · "
                f"{debt_type}"
            )
        )


class DolgiApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        config.load_env()
        self.settings = storage.load_settings()
        self.debts: list[Debt] = []
        self.info: Optional[ZachetkaInfo] = None
        self.schedule: dict[str, ScheduleEntry] = {}

        self.messages: queue.Queue = queue.Queue()
        self.busy = False

        self.title("Dolgi — планировщик закрытия долгов")
        self.geometry("1280x760")
        self.minsize(1080, 640)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()
        self._load_local_data()

        self.after(100, self._poll_messages)

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _build_left_panel(self) -> None:
        left = ctk.CTkFrame(self, width=430, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsw")
        left.grid_propagate(False)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(5, weight=1)

        # --------------------------------------------------------------
        # Авторизация
        # --------------------------------------------------------------

        auth = ctk.CTkFrame(left)
        auth.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        auth.grid_columnconfigure(0, weight=1)
        auth.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            auth,
            text="Аккаунт БГПУ",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 2))

        login, password = config.get_credentials()

        self.login_entry = ctk.CTkEntry(auth, placeholder_text="Логин")
        self.login_entry.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        set_entry_value(self.login_entry, login)
        bind_text_shortcuts(self.login_entry)

        self.password_entry = ctk.CTkEntry(auth, placeholder_text="Пароль", show="•")
        self.password_entry.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=4)
        set_entry_value(self.password_entry, password)
        bind_text_shortcuts(self.password_entry)

        self.group_entry = ctk.CTkEntry(
            auth,
            placeholder_text="Твоя группа (например, ПИНФ_ПИЦЭ-31-24)",
        )
        self.group_entry.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=4)
        set_entry_value(self.group_entry, self.settings.get("group", ""))
        bind_text_shortcuts(self.group_entry)

        self.show_browser_switch = ctk.CTkSwitch(auth, text="показывать браузер")
        self.show_browser_switch.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 8))

        if not self.settings.get("headless", True):
            self.show_browser_switch.select()

        # --------------------------------------------------------------
        # Кнопки действий
        # --------------------------------------------------------------

        actions = ctk.CTkFrame(left, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)

        self.debts_button = ctk.CTkButton(
            actions,
            text="Загрузить долги",
            command=self.on_fetch_debts,
        )
        self.debts_button.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self.schedule_button = ctk.CTkButton(
            actions,
            text="Загрузить расписания",
            command=self.on_fetch_schedules,
        )
        self.schedule_button.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        self.plan_button = ctk.CTkButton(
            actions,
            text="Построить план",
            command=self.on_build_plan,
        )
        self.plan_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        # --------------------------------------------------------------
        # Тумблеры типов долгов
        # --------------------------------------------------------------

        types_frame = ctk.CTkFrame(left, fg_color="transparent")
        types_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 0))
        types_frame.grid_columnconfigure(0, weight=1)
        types_frame.grid_columnconfigure(1, weight=1)
        types_frame.grid_columnconfigure(2, weight=1)
        types_frame.grid_columnconfigure(3, weight=1)

        self.type_switches: dict[str, ctk.CTkSwitch] = {}

        for index, (key, label, _value) in enumerate(DEBT_TYPE_FILTERS):
            switch = ctk.CTkSwitch(
                types_frame,
                text=label,
                command=lambda k=key: self.on_type_toggled(k),
            )
            switch.grid(row=0, column=index, sticky="w", padx=(0, 6), pady=2)

            if self.settings.get("debt_types", {}).get(key, False):
                switch.select()

            self.type_switches[key] = switch

        # --------------------------------------------------------------
        # Прогресс и статус
        # --------------------------------------------------------------

        self.progress = ctk.CTkProgressBar(left)
        self.progress.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 0))
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(
            left,
            text="Готово к работе.",
            anchor="w",
            justify="left",
            wraplength=400,
            font=ctk.CTkFont(size=META_FONT_SIZE),
            text_color=("gray30", "gray65"),
        )
        self.status_label.grid(row=4, column=0, sticky="ew", padx=14, pady=(2, 4))

        # --------------------------------------------------------------
        # Карточки долгов
        # --------------------------------------------------------------

        self.cards_frame = ctk.CTkScrollableFrame(
            left,
            label_text="Долги",
            label_font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.cards_frame.grid(row=5, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.cards_frame.grid_columnconfigure(0, weight=1)

    def _build_right_panel(self) -> None:
        right = ctk.CTkFrame(self, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(right)
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.plan_tab = self.tabs.add("План")
        self.log_tab = self.tabs.add("Журнал")

        self.plan_tab.grid_columnconfigure(0, weight=1)
        self.plan_tab.grid_rowconfigure(0, weight=1)

        self.log_tab.grid_columnconfigure(0, weight=1)
        self.log_tab.grid_rowconfigure(0, weight=1)

        self.plan_text = ctk.CTkTextbox(
            self.plan_tab,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="word",
        )
        self.plan_text.grid(row=0, column=0, sticky="nsew")
        self.plan_text.insert("1.0", "Здесь появится план закрытия долгов.\n")
        self.plan_text.configure(state="disabled")

        self.log_text = ctk.CTkTextbox(
            self.log_tab,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")
        bind_text_shortcuts(self.log_text)

    # ------------------------------------------------------------------
    # Локальные данные
    # ------------------------------------------------------------------

    def _type_enabled(self, debt: Debt) -> bool:
        """Долг проходит через тумблеры типов долгов."""
        key = DEBT_TYPE_TO_KEY.get(debt.debt_type or "")
        return bool(self.settings.get("debt_types", {}).get(key, False))

    def _active_debts(self) -> list[Debt]:
        """Долги, прошедшие фильтр типов (для карточек и плана)."""
        return [debt for debt in self.debts if self._type_enabled(debt)]

    def _load_local_data(self) -> None:
        deleted = set(self.settings.get("deleted_ids", []))

        self.debts = [
            debt
            for debt in storage.load_debts()
            if debt.id not in deleted
        ]
        self.schedule = storage.load_schedule()

        self._render_cards()
        self._set_status(
            f"Загружено из локальных данных: долгов {len(self.debts)}, "
            f"расписаний {len(self.schedule)}."
        )

    def _render_cards(self) -> None:
        for widget in self.cards_frame.winfo_children():
            widget.destroy()

        if not self.debts:
            ctk.CTkLabel(
                self.cards_frame,
                text="Долгов нет.\nНажмите «Загрузить долги».",
                text_color=("gray40", "gray60"),
            ).grid(row=0, column=0, pady=20)

            return

        active = self._active_debts()

        if not active:
            ctk.CTkLabel(
                self.cards_frame,
                text="Все типы долгов выключены.\nВключите нужные тумблеры сверху.",
                text_color=("gray40", "gray60"),
            ).grid(row=0, column=0, pady=20)

            return

        for index, debt in enumerate(active):
            card = DebtCard(self.cards_frame, self, debt)
            card.grid(row=index, column=0, sticky="ew", padx=4, pady=4)

    # ------------------------------------------------------------------
    # Очередь сообщений из рабочих потоков
    # ------------------------------------------------------------------

    def _poll_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                self._handle_message(kind, payload)

        except queue.Empty:
            pass

        self.after(100, self._poll_messages)

    def _handle_message(self, kind: str, payload) -> None:
        if kind == "log":
            self._append_log(payload)

        elif kind == "status":
            self._set_status(payload)

        elif kind == "progress":
            self.progress.set(payload if payload is not None else 0)

        elif kind == "debts":
            self._on_debts_loaded(payload)

        elif kind == "schedule":
            self._on_schedule_loaded()

        elif kind == "plan":
            self._show_plan(payload)

        elif kind == "done":
            self._finish_job(payload)

        elif kind == "error":
            self._fail_job(payload)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_status(self, message: str) -> None:
        self.status_label.configure(text=message)

    def _show_plan(self, text: str) -> None:
        self.plan_text.configure(state="normal")
        self.plan_text.delete("1.0", "end")
        self.plan_text.insert("1.0", text)
        self.plan_text.configure(state="disabled")
        self.tabs.set("План")

    # ------------------------------------------------------------------
    # Запуск фоновых задач
    # ------------------------------------------------------------------

    def _start_job(self, name: str, target) -> None:
        if self.busy:
            self._set_status("Дождитесь завершения текущей операции.")
            return

        self.busy = True
        self._set_buttons_state("disabled")
        self._set_status(f"{name}...")

        def worker():
            try:
                target()
                self.messages.put(("done", name))
            except Exception as error:
                self.messages.put(("error", f"{type(error).__name__}: {error}"))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_job(self, name: str) -> None:
        self.busy = False
        self._set_buttons_state("normal")
        self.progress.set(0)
        self._set_status(f"{name} — готово.")

    def _fail_job(self, message: str) -> None:
        self.busy = False
        self._set_buttons_state("normal")
        self.progress.set(0)
        self._set_status(f"Ошибка: {message}")
        self._append_log(f"ОШИБКА: {message}")

    def _set_buttons_state(self, state: str) -> None:
        for button in (self.debts_button, self.schedule_button, self.plan_button):
            button.configure(state=state)

    def _log_callback(self, message: str) -> None:
        self.messages.put(("log", message))

    def _progress_callback(self, value: Optional[float]) -> None:
        self.messages.put(("progress", value))

    # ------------------------------------------------------------------
    # Действия
    # ------------------------------------------------------------------

    def _apply_credentials(self) -> None:
        login = self.login_entry.get().strip()
        password = self.password_entry.get()

        if login and password:
            config.save_credentials(login, password)

        self.settings["group"] = self.group_entry.get().strip()
        self.settings["headless"] = not bool(self.show_browser_switch.get())
        storage.save_settings(self.settings)

    def on_fetch_debts(self) -> None:
        self._apply_credentials()
        headless = self.settings.get("headless", True)

        def job():
            info, debts = browser.fetch_debts(
                headless=headless,
                on_log=self._log_callback,
            )

            self.messages.put(("debts", (info, debts)))

        self._start_job("Загружаю долги с сайта", job)

    def on_fetch_schedules(self) -> None:
        self._apply_credentials()
        headless = self.settings.get("headless", True)

        teachers: list[str] = []

        for debt in self._active_debts():
            if not debt.tracked:
                continue

            for teacher in debt.teachers:
                if teacher not in teachers:
                    teachers.append(teacher)

        group = self.group_entry.get().strip()

        if not teachers and not group:
            self._set_status("Нет долгов или группы: сначала загрузите долги.")
            return

        def job():
            browser.fetch_schedules(
                teachers=teachers,
                group=group,
                headless=headless,
                on_log=self._log_callback,
                on_progress=self._progress_callback,
            )

            self.messages.put(("schedule", None))

        self._start_job("Собираю расписания", job)

    def on_build_plan(self) -> None:
        def job():
            tracked = [
                debt
                for debt in self._active_debts()
                if debt.tracked
            ]

            if not tracked:
                raise RuntimeError("Нет долгов для планирования (проверь тумблеры типов и «учитывать»).")

            schedule = storage.load_schedule()

            if not schedule:
                raise RuntimeError("Расписания не загружены.")

            self.messages.put(
                ("log", f"Сопоставляю {len(tracked)} долгов с расписаниями...")
            )

            matches_data = matcher.build_matches(tracked, schedule)

            candidates = optimizer.build_candidates(matches_data)
            days = optimizer.group_by_date(candidates)

            day_plans: dict[str, list[dict]] = {}

            for date, date_candidates in days.items():
                plans = optimizer.generate_day_plans(date_candidates, len(matches_data))
                plans = optimizer.remove_dominated_plans(plans)
                day_plans[date] = plans

            plan = optimizer.optimize_days(day_plans, len(matches_data))
            text = planner.build_full_plan_text(plan, matches_data)

            self.messages.put(("plan", text))

        self._start_job("Строю план", job)

    # ------------------------------------------------------------------
    # Обновления от задач
    # ------------------------------------------------------------------

    def on_debt_changed(self) -> None:
        storage.save_debts(self.debts)
        self._set_status("Изменения сохранены.")

    def on_type_toggled(self, key: str) -> None:
        """Тумблер типа долга: сохранить и перерисовать карточки."""
        enabled = bool(self.type_switches[key].get())
        self.settings.setdefault("debt_types", {})[key] = enabled
        storage.save_settings(self.settings)

        active = self._active_debts()
        self._render_cards()
        self._set_status(
            f"Типов долгов учтено: {len(active)} из {len(self.debts)}."
        )

    def on_debt_deleted(self, debt: Debt, card: DebtCard) -> None:
        self.debts = [item for item in self.debts if item.id != debt.id]

        deleted: list[str] = list(self.settings.get("deleted_ids", []))

        if debt.id not in deleted:
            deleted.append(debt.id)

        self.settings["deleted_ids"] = deleted
        storage.save_settings(self.settings)
        storage.save_debts(self.debts)

        card.destroy()
        self._set_status("Долг удалён из учёта.")

    # ------------------------------------------------------------------
    # Результаты фоновых задач
    # ------------------------------------------------------------------

    def _on_debts_loaded(self, payload: tuple[ZachetkaInfo, list[Debt]]) -> None:
        info, debts = payload
        self.info = info

        # Группа из зачётки — только как стартовое значение:
        # код группы в зачётке может отличаться от учебной группы
        # с расписанием, поэтому значение пользователь правит сам.
        if not self.group_entry.get().strip() and info.group:
            self.group_entry.delete(0, "end")
            self.group_entry.insert(0, info.group)
            self.settings["group"] = info.group
            storage.save_settings(self.settings)

        deleted = set(self.settings.get("deleted_ids", []))

        merged = storage.merge_debts(
            self.debts,
            [debt for debt in debts if debt.id not in deleted],
        )

        self.debts = merged
        storage.save_debts(self.debts)
        self._render_cards()

        self._set_status(f"Долги обновлены: {len(self.debts)}.")
        self._append_log(f"Студент: {info.student or '—'}, группа: {info.group or '—'}")

    def _on_schedule_loaded(self) -> None:
        self.schedule = storage.load_schedule()

        total_lessons = sum(len(entry.lessons) for entry in self.schedule.values())
        errors = sum(1 for entry in self.schedule.values() if entry.error)

        self._set_status(
            f"Расписания обновлены: {len(self.schedule)} владельцев, "
            f"{total_lessons} занятий, ошибок: {errors}."
        )


def run_app() -> None:
    app = DolgiApp()
    app.mainloop()
