import asyncio
import os

from aiogram import Bot
from dotenv import load_dotenv


load_dotenv()


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")


def split_message(text: str, max_length: int = 4000) -> list[str]:
    """
    Разбивает длинный текст на части для Telegram.
    Старается не разрывать строки.
    """

    if len(text) <= max_length:
        return [text]

    parts = []
    current = ""

    for line in text.splitlines(keepends=True):

        if len(current) + len(line) <= max_length:
            current += line
            continue

        if current:
            parts.append(current.rstrip())

        # Если одна строка сама длиннее лимита Telegram,
        # режем её принудительно.
        if len(line) > max_length:
            for i in range(0, len(line), max_length):
                chunk = line[i:i + max_length]

                if len(chunk) == max_length:
                    parts.append(chunk.rstrip())
                else:
                    current = chunk

        else:
            current = line

    if current:
        parts.append(current.rstrip())

    return parts


async def send_message(text: str):
    """
    Отправляет текст администратору Telegram-бота.
    """

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError(
            "Не найден TELEGRAM_BOT_TOKEN в файле .env"
        )

    if not TELEGRAM_ADMIN_ID:
        raise ValueError(
            "Не найден TELEGRAM_ADMIN_ID в файле .env"
        )

    try:
        admin_id = int(TELEGRAM_ADMIN_ID)
    except ValueError:
        raise ValueError(
            "TELEGRAM_ADMIN_ID должен быть числом"
        )

    parts = split_message(text)

    async with Bot(
        token=TELEGRAM_BOT_TOKEN
    ) as bot:

        for part in parts:
            await bot.send_message(
                chat_id=admin_id,
                text=part,
            )


def send_plan(text: str):
    """
    Синхронная функция для вызова из main.py.
    """

    asyncio.run(
        send_message(text)
    )