import asyncio
import logging
from html import escape

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from .weather_api import WeatherApiError

logger = logging.getLogger(__name__)
STATUS_INTERVAL = 3
STAGES = {
    "preparing": "Подготовка данных", "searching": "Подбор гиперпараметров",
    "fitting": "Обучение", "evaluating": "Оценка на тестовой выборке",
    "charting": "Подготовка графиков", "publishing": "Публикация выпуска",
}


def parse_admin_ids(value):
    try:
        ids = {int(part) for part in value.split(",")} if value.strip() else set()
        if any(user_id <= 0 for user_id in ids):
            raise ValueError
    except ValueError:
        raise ValueError("Укажите положительные Telegram ID через запятую в TELEGRAM_ADMIN_IDS.") from None
    return ids


def describe_training(data):
    status = data.get("status")
    if status == "idle":
        return "Обучение ещё не запускалось."
    stage = STAGES.get(data.get("stage"), "Обучение")
    if model := data.get("model_name"):
        stage = f"{stage} ({escape(model)})"
    if status == "running":
        lines = ["<b>⏳ Обучение моделей</b>", "", stage]
    elif status == "failed":
        lines = ["<b>⚠️ Обучение прервано</b>", "", f"Этап: {stage}. Повторить запуск можно через /train."]
    elif status == "succeeded":
        lines = [f"<b>✅ Выпуск {escape(data['model_version'])} опубликован</b>"]
        model, score = data.get("best_model_name"), data.get("best_roc_auc")
        if model and type(score) in (int, float):
            formatted = f"{score:.4f}".replace(".", ",")
            lines.extend(("", f"Лучшая модель: {escape(model)}", f"ROC-AUC: <b>{formatted}</b>"))
    else:
        return "Сервис вернул неизвестный статус обучения."

    completed, total = data.get("completed_models"), data.get("total_models")
    elapsed = data.get("elapsed_seconds")
    progress = []
    if type(completed) is int and type(total) is int and total > 0:
        progress.append(f"Готово {completed} из {total} моделей")
    if type(elapsed) is int:
        minutes, seconds = divmod(elapsed, 60)
        progress.append(f"Прошло {minutes} мин {seconds:02d} с" if minutes else f"Прошло {seconds} с")
    if progress:
        lines.extend(("", *progress))
    return "\n".join(lines)


class TrainingControls:
    def __init__(self, api, master_key, admin_ids):
        self.api = api
        self.master_key = master_key
        self.admin_ids = admin_ids
        self.watchers = {}

    def can_manage(self, user_id):
        return user_id in self.admin_ids and bool(self.master_key)

    async def request(self, user_id, *, start=False):
        if user_id not in self.admin_ids:
            raise WeatherApiError("Обучение доступно администраторам бота. Ваш Telegram ID можно узнать через /id.")
        if not self.master_key:
            raise WeatherApiError("На сервере бота не задан мастер-ключ для обучения.")
        try:
            return await self.api.training(self.master_key, start=start)
        except WeatherApiError as error:
            if start and error.status == 409:
                return await self.api.training(self.master_key)
            raise

    async def show(self, message, user_id, *, start=False):
        try:
            data = await self.request(user_id, start=start)
        except WeatherApiError as error:
            await message.answer(str(error))
            return
        await self.present(message, user_id, data)

    async def present(self, message, user_id, data):
        text = describe_training(data)
        status_message = await message.answer(text, parse_mode=ParseMode.HTML)
        if data.get("status") == "running":
            chat = status_message.chat.id
            task = self.watchers.get(chat)
            if task is None or task.done():
                self.watchers[chat] = asyncio.create_task(self.watch(status_message, user_id, text))

    async def watch(self, message, user_id, last_text):
        failures = 0
        try:
            while True:
                await asyncio.sleep(STATUS_INTERVAL)
                try:
                    data = await self.request(user_id)
                except WeatherApiError as error:
                    failures += 1
                    if error.status in (401, 503) or failures == 3:
                        await message.edit_text(f"{error}\nПроверьте статус через /training_status.")
                        return
                    continue
                failures = 0
                text = describe_training(data)
                if text != last_text:
                    await message.edit_text(text, parse_mode=ParseMode.HTML)
                    last_text = text
                if data.get("status") != "running":
                    return
        except TelegramAPIError:
            logger.warning("Could not update Telegram training status for chat %s", message.chat.id)
        finally:
            self.watchers.pop(message.chat.id, None)

    async def close(self):
        tasks = list(self.watchers.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
