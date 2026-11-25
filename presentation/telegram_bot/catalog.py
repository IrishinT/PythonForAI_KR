import asyncio
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InputMediaPhoto, Message

from .keyboards import (
    MENU_METRICS, MENU_MODEL, VERSIONS_PER_PAGE, ModelChoice, ReleaseChoice, ReleasePage,
    menu_text, models_keyboard, releases_keyboard,
)
from .weather_api import WeatherApi, WeatherApiError

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

METRIC_NAMES = {"ROC-AUC": "ROC-AUC", "Accuracy": "Accuracy", "F1-score": "F1", "Precision": "Precision", "Recall": "Recall"}
CHART_NAMES = {
    "roc": "ROC", "precision-recall": "Precision–Recall",
    "learning-curve": "Кривая обучения", "confusion-matrix": "Матрица ошибок",
}


async def selected_model(state: FSMContext) -> dict:
    return (await state.get_data()).get("model_selection", {})


@router.message(Command("model"))
@router.message(F.text.in_((MENU_MODEL, menu_text(MENU_MODEL))))
async def show_releases(message: Message, state: FSMContext, weather_api: WeatherApi):
    try:
        catalog = await weather_api.versions()
    except WeatherApiError as error:
        await message.answer(str(error))
        return

    selection = await selected_model(state)
    current = "Будет использована лучшая модель последнего выпуска."
    if selection:
        current = f"Текущая модель {selection['model_id']} (v{selection['model_version']})."
    await message.answer(
        f"<b>🧩 Выбор модели</b>\n\n{escape(current)}\n\nВыберите выпуск или автоматический режим.",
        parse_mode=ParseMode.HTML, reply_markup=releases_keyboard(catalog, 0),
    )


@router.callback_query(ReleasePage.filter(F.page >= 0))
async def change_release_page(callback: CallbackQuery, callback_data: ReleasePage, weather_api: WeatherApi):
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    try:
        catalog = await weather_api.versions()
    except WeatherApiError as error:
        await callback.message.answer(str(error))
        return
    last_page = max(0, (len(catalog["versions"]) - 1) // VERSIONS_PER_PAGE)
    await callback.message.edit_text("Выберите выпуск.", reply_markup=releases_keyboard(catalog, min(callback_data.page, last_page)))


@router.callback_query(ReleaseChoice.filter())
async def show_release_models(callback: CallbackQuery, callback_data: ReleaseChoice, weather_api: WeatherApi):
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    try:
        catalog = await weather_api.versions()
    except WeatherApiError as error:
        await callback.message.answer(str(error))
        return
    release = next((item for item in catalog["versions"] if item["model_version"] == callback_data.version), None)
    if release is None:
        await callback.message.answer("Этот выпуск недоступен. Откройте список через /model.")
        return
    text = f"Модели выпуска {release['model_version']}. Выберите модель."
    await callback.message.edit_text(text, reply_markup=models_keyboard(release, catalog["latest_version"]))


@router.callback_query(ModelChoice.filter(F.index >= 0))
async def choose_model(callback: CallbackQuery, callback_data: ModelChoice, state: FSMContext, weather_api: WeatherApi):
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    try:
        release = await weather_api.models(callback_data.version)
    except WeatherApiError as error:
        await callback.message.answer(str(error))
        return
    if callback_data.index >= len(release["models"]):
        await callback.message.answer("Эта модель недоступна. Откройте список через /model.")
        return
    model = release["models"][callback_data.index]
    version = release["model_version"]
    await state.update_data(model_selection={"model_version": version, "model_id": model["model_id"]})
    await callback.message.edit_text(f"Выбрана модель {model['model_name']} (v{version}).")


@router.callback_query(F.data == "model_auto")
async def choose_automatically(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if isinstance(callback.message, Message):
        await state.update_data(model_selection={})
        await callback.message.edit_text("Будет использоваться лучшая модель последнего выпуска.")


@router.message(Command("metrics"))
@router.message(F.text.in_((MENU_METRICS, menu_text(MENU_METRICS))))
async def show_metrics(message: Message, state: FSMContext, weather_api: WeatherApi):
    try:
        data = await weather_api.metrics(**await selected_model(state))
    except WeatherApiError as error:
        await message.answer(str(error) if error.status != 404 else "Модель недоступна. Выберите другую через /model.")
        return

    version, model_id = data["model_version"], data["model_id"]
    lines = ["<b>📊 Метрики модели</b>", f"Модель: {escape(data['model_name'])} (v{escape(version)})", ""]
    for key, title in METRIC_NAMES.items():
        value = data["metrics"].get(key)
        if type(value) in (int, float):
            formatted = f"{value:.4f}".replace(".", ",")
            lines.append(f"{title}: <b>{formatted}</b>" if key == "ROC-AUC" else f"{title}: {formatted}")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)

    charts = [key for key in CHART_NAMES if key in data.get("charts", [])]
    if not charts:
        await message.answer("Для этой модели сохранены только числовые метрики.")
        return
    images = await asyncio.gather(
        *(weather_api.chart(key, model_version=version, model_id=model_id) for key in charts), return_exceptions=True,
    )
    media = [
        InputMediaPhoto(media=BufferedInputFile(image, filename=f"{key}.png"), caption=CHART_NAMES[key])
        for key, image in zip(charts, images) if isinstance(image, bytes)
    ]
    if len(media) == 1:
        await message.answer_photo(media[0].media, caption=media[0].caption)
    elif media:
        await message.answer_media_group(media)
    if len(media) < len(charts):
        await message.answer("Некоторые графики не удалось загрузить. Повторите /metrics.")
