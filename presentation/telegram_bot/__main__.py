import asyncio
import logging
from os import getenv
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.utils.token import TokenValidationError
from aiohttp import ClientSession, ClientTimeout
from dotenv import load_dotenv

from .handlers import router
from .weather_api import WeatherApi


async def run(token, api_url):
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    dispatcher.include_router(router)
    async with ClientSession(timeout=ClientTimeout(total=7)) as session:
        weather_api = WeatherApi(session, api_url)
        async with Bot(token) as bot:
            await dispatcher.start_polling(bot, weather_api=weather_api, close_bot_session=False)


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    token = getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Укажите TELEGRAM_BOT_TOKEN в файле .env.")
    api_url = getenv("WEATHER_API_URL") or "http://127.0.0.1:8000"
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run(token, api_url))
    except TokenValidationError:
        raise SystemExit("Проверьте TELEGRAM_BOT_TOKEN в файле .env.") from None
    except ValueError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
