import asyncio
import logging
from os import getenv
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats
from aiogram.utils.token import TokenValidationError
from aiohttp import ClientSession, ClientTimeout
from dotenv import load_dotenv

from .catalog import router as catalog_router
from .handlers import COMMANDS, router
from .training import TrainingControls, parse_admin_ids
from .weather_api import WeatherApi


async def run(token, api_url, master_key, admin_ids, proxy_url=None):
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    dispatcher.include_routers(catalog_router, router)
    async with ClientSession(timeout=ClientTimeout(total=7)) as session:
        weather_api = WeatherApi(session, api_url)
        training = TrainingControls(weather_api, master_key, admin_ids)
        async with Bot(token, session=AiohttpSession(proxy=proxy_url)) as bot:
            await bot.set_my_commands(
                [BotCommand(command=command, description=description) for command, description in COMMANDS.items()],
                scope=BotCommandScopeAllPrivateChats(),
            )
            try:
                await dispatcher.start_polling(bot, weather_api=weather_api, training=training, close_bot_session=False)
            finally:
                await training.close()


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    token = getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Укажите TELEGRAM_BOT_TOKEN в файле .env.")
    api_url = getenv("WEATHER_API_URL") or "http://127.0.0.1:8000"
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        admin_ids = parse_admin_ids(getenv("TELEGRAM_ADMIN_IDS", ""))
        proxy_url = getenv("TELEGRAM_PROXY_URL", "").strip() or None
        asyncio.run(run(token, api_url, getenv("WEATHER_MASTER_KEY", ""), admin_ids, proxy_url=proxy_url))
    except TokenValidationError:
        raise SystemExit("Проверьте TELEGRAM_BOT_TOKEN в файле .env.") from None
    except ValueError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
