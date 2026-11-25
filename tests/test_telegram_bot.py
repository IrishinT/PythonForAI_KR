import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher
from aiogram.methods import EditMessageText, SendMediaGroup, SendMessage
from aiogram.types import Message

from presentation.telegram_bot.catalog import router as catalog_router
from presentation.telegram_bot.handlers import router as forecast_router
from presentation.telegram_bot.keyboards import ModelChoice, ReleaseChoice, WindChoice
from presentation.telegram_bot.training import TrainingControls
from presentation.weather_input import MEASUREMENTS

RELEASE = {
    "model_version": "1.1.0", "default_model_id": "mlp",
    "models": [{"model_id": "mlp", "model_name": "MLP"}, {"model_id": "knn", "model_name": "KNN"}],
}
BOT_USER = {"id": 123456, "is_bot": True, "first_name": "Test bot"}


class TelegramBotTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.dispatcher = Dispatcher()
        cls.dispatcher.include_routers(catalog_router, forecast_router)

    async def asyncSetUp(self):
        self.bot = Bot("123456:unit-test-token")
        self.addAsyncCleanup(self.bot.session.close)
        self.calls = []
        self.next_id = 1000
        self.last_message = None
        self.api = SimpleNamespace(
            versions=AsyncMock(return_value={"latest_version": "1.1.0", "versions": [RELEASE]}),
            models=AsyncMock(return_value=RELEASE),
            metrics=AsyncMock(return_value={
                "model_version": "1.1.0", "model_id": "knn", "model_name": "KNN",
                "metrics": {"ROC-AUC": 0.8}, "charts": ["roc", "learning-curve"],
            }),
            chart=AsyncMock(return_value=b"chart-bytes"),
            predict=AsyncMock(return_value=(True, 0.75, "1.1.0", "knn")),
            training=AsyncMock(),
        )
        self.training = TrainingControls(self.api, "test-master-key", {222})
        self.addAsyncCleanup(self.training.close)

        async def handle(bot, method, **kwargs):
            self.calls.append(method)
            if isinstance(method, SendMessage):
                self.last_message = self.message(method.chat_id, method.text, sender=BOT_USER)
                return Message.model_validate(self.last_message, context={"bot": bot})
            if isinstance(method, SendMediaGroup):
                return []
            return True

        self.enterContext(patch.object(Bot, "__call__", autospec=True, side_effect=handle))

    def message(self, user_id, text, sender=None):
        self.next_id += 1
        return {
            "message_id": self.next_id, "date": 1700000000, "chat": {"id": user_id, "type": "private"},
            "from": sender or {"id": user_id, "is_bot": False, "first_name": "User"}, "text": text,
        }

    async def update(self, **payload):
        self.next_id += 1
        return await self.dispatcher.feed_raw_update(
            self.bot, {"update_id": self.next_id, **payload}, weather_api=self.api, training=self.training,
        )

    async def send(self, user_id, text):
        await self.update(message=self.message(user_id, text))

    async def click(self, user_id, data, message=None):
        await self.update(callback_query={
            "id": str(self.next_id), "chat_instance": "test", "data": data,
            "from": {"id": user_id, "is_bot": False, "first_name": "User"},
            "message": message or self.last_message,
        })

    async def test_menu_commands_and_admin_access(self):
        await self.send(111, "/start")
        keyboard = self.calls[-1].reply_markup
        self.assertTrue(keyboard.is_persistent)
        buttons = {button.text for row in keyboard.keyboard for button in row}
        self.assertIn("🌦️ Прогноз", buttons)
        self.assertIn("🧩 Модель", buttons)
        self.assertIn("📊 Метрики", buttons)
        self.assertIn("Справка", buttons)
        self.assertIn("О боте", buttons)
        self.assertNotIn("Обучение", buttons)
        self.assertNotIn("⚙️ Обучение", buttons)

        await self.send(111, "/forecast")
        self.assertTrue(self.calls[-1].reply_markup.inline_keyboard)
        await self.send(111, "Справка")
        self.assertIn("/training_status", self.calls[-1].text)
        self.assertIn("сегодняшние наблюдения", self.calls[-1].text)
        await self.send(111, "/help")
        self.assertIn("/about", self.calls[-1].text)
        await self.send(111, "/about")
        about = self.calls[-1].text
        self.assertIn("вероятность дождя на завтра", about)
        await self.send(111, "О боте")
        self.assertEqual(self.calls[-1].text, about)
        await self.send(111, "Sydney")
        self.assertIn(MEASUREMENTS[0][1], self.calls[-1].text)
        await self.send(111, "/train")
        await self.send(111, "/training_status")
        self.api.training.assert_not_awaited()

    async def test_selection_is_used_for_metrics_and_survives_forecast_and_cancel(self):
        await self.send(333, "/model")
        release_message = self.last_message
        await self.click(333, ReleaseChoice(version="1.1.0").pack(), release_message)
        self.assertIn("(рекомендуемая)", self.calls[-1].reply_markup.inline_keyboard[0][0].text)
        await self.click(333, ModelChoice(version="1.1.0", index=1).pack(), release_message)

        await self.send(333, "🌦️ Прогноз")
        await self.send(333, "📊 Метрики")
        self.api.metrics.assert_awaited_once_with(model_version="1.1.0", model_id="knn")
        self.assertEqual(self.api.chart.await_count, 2)
        self.assertIsInstance(self.calls[-1], SendMediaGroup)
        self.assertEqual(len(self.calls[-1].media), 2)
        metrics_message = next(method for method in reversed(self.calls) if isinstance(method, SendMessage))
        self.assertIn("Модель: KNN (v1.1.0)\n\nROC-AUC: <b>0,8000</b>", metrics_message.text)

        await self.send(333, "Sydney")
        for _, _, _, example in MEASUREMENTS:
            await self.send(333, example)
        await self.click(333, WindChoice(code="W").pack())
        self.assertEqual(self.api.predict.await_args.kwargs, {"model_version": "1.1.0", "model_id": "knn"})
        forecast = self.calls[-1]
        self.assertEqual(forecast.parse_mode, "HTML")
        self.assertIn("\n\nСтанция: Sydney\nВероятность дождя: <b>75%</b>\n\nМодель: knn (v1.1.0)", forecast.text)

        await self.send(333, "/cancel")
        await self.send(333, "Метрики")
        self.api.metrics.assert_awaited_with(model_version="1.1.0", model_id="knn")
        await self.send(333, "🧩 Модель")
        await self.click(333, "model_auto")
        await self.send(333, "/metrics")
        self.api.metrics.assert_awaited_with()

    async def test_training_confirmation_starts_once_and_reports_release(self):
        self.api.training.side_effect = [
            {"status": "idle"}, {"status": "running", "stage": "searching", "model_name": "MLP"},
            {"status": "succeeded", "model_version": "1.1.1", "best_model_name": "MLP", "best_roc_auc": 0.8848},
        ]
        with patch("presentation.telegram_bot.training.STATUS_INTERVAL", 0.05):
            await self.send(222, "⚙️ Обучение")
            self.assertFalse(self.api.training.await_args.kwargs["start"])
            prompt = self.last_message
            await self.click(222, "train_start", prompt)
            await self.click(222, "train_start", prompt)
            if watcher := self.training.watchers.get(222):
                await asyncio.wait_for(watcher, timeout=3)

        starts = [call for call in self.api.training.await_args_list if call.kwargs["start"]]
        self.assertEqual(len(starts), 1)
        updates = [method.text for method in self.calls if isinstance(method, EditMessageText)]
        self.assertTrue(any("1.1.1" in text and "ROC-AUC: <b>0,8848</b>" in text for text in updates))
