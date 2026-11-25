from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from presentation.weather_input import (
    LOCATIONS,
    MEASUREMENTS,
    WIND_DIRECTIONS,
    format_probability,
    parse_measurement,
)
from weather_contract import WEATHER_LIMITS

from .catalog import selected_model
from .keyboards import (
    LAST_PAGE,
    MENU_ABOUT,
    MENU_FORECAST,
    MENU_HELP,
    MENU_STATUS,
    MENU_TRAINING,
    LocationChoice,
    LocationPage,
    WindChoice,
    forecast_menu,
    location_keyboard,
    main_menu,
    menu_text,
    training_keyboard,
    wind_keyboard,
)
from .training import TrainingControls
from .weather_api import WeatherApi, WeatherApiError

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

LOCATION_NAMES = {name.casefold(): name for name in LOCATIONS}
WIND_CODES = {code for code, _ in WIND_DIRECTIONS}
COMMANDS = {
    "start": "Открыть меню",
    "forecast": "Получить прогноз дождя",
    "model": "Выбрать выпуск и модель",
    "metrics": "Посмотреть метрики и графики выбранной модели",
    "train": "Запустить обучение (для администраторов)",
    "training_status": "Проверить обучение (для администраторов)",
    "status": "Проверить подключение к API",
    "cancel": "Отменить ввод прогноза",
    "id": "Узнать свой Telegram ID",
    "help": "Открыть справку",
    "about": "Узнать, что делает бот",
}


class Forecast(StatesGroup):
    location = State()
    measurement = State()
    wind = State()
    retry = State()


async def hide_keyboard(message: Message, state: FSMContext):
    data = await state.get_data()
    keyboard_id = data.get("keyboard_id")
    if keyboard_id is not None:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id, message_id=keyboard_id, reply_markup=None
            )
        except TelegramBadRequest:
            pass
        await state.update_data(keyboard_id=None)


async def current_keyboard(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    message = callback.message
    if not isinstance(message, Message) or message.message_id != data.get("keyboard_id"):
        await callback.answer("Эта кнопка устарела. Используйте /forecast.")
        return None
    await callback.answer()
    return message


async def reset_forecast(state: FSMContext):
    selection = await selected_model(state)
    await state.set_state(None)
    await state.set_data({"model_selection": selection} if selection else {})


def user_id(message: Message):
    return message.from_user.id if message.from_user else None


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, training: TrainingControls):
    await hide_keyboard(message, state)
    await reset_forecast(state)
    await message.answer(
        "<b>🌦️ Дождь завтра</b>\n\n"
        "Я рассчитаю вероятность дождя на завтра по вашим наблюдениям за сегодня.\n\n"
        "Нажмите «Прогноз», чтобы начать, или откройте /help.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(training.can_manage(user_id(message))),
    )


@router.message(Command("help"))
@router.message(F.text == MENU_HELP)
async def help_menu(message: Message, training: TrainingControls):
    commands = "\n".join(f"/{command} {description}" for command, description in COMMANDS.items())
    text = (
        "<b>📘 Справка</b>\n\n"
        "Нажмите «Прогноз» и введите сегодняшние наблюдения. "
        "В разделе «Модель» можно выбрать выпуск и модель. "
        "Раздел «Метрики» покажет показатели качества и графики выбранной модели.\n\n"
        f"<b>Команды</b>\n{commands}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=main_menu(training.can_manage(user_id(message))))


@router.message(Command("about"))
@router.message(F.text == MENU_ABOUT)
async def about(message: Message, training: TrainingControls):
    await message.answer(
        "<b>ℹ️ О боте</b>\n\n"
        "Бот рассчитывает вероятность дождя на завтра по вашим наблюдениям за сегодня.\n\n"
        "Модели обучены на австралийских метеонаблюдениях из набора <i>Rain in Australia</i>. "
        "Можно выбрать модель и посмотреть, как она показала себя на тестовой выборке.\n\n"
        "Начните с /forecast или откройте справку через /help.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(training.can_manage(user_id(message))),
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext, training: TrainingControls):
    await hide_keyboard(message, state)
    await reset_forecast(state)
    await message.answer("Ввод отменён.", reply_markup=main_menu(training.can_manage(user_id(message))))


@router.message(Command("status"))
@router.message(F.text == MENU_STATUS)
async def status(message: Message, weather_api: WeatherApi):
    connected = await weather_api.is_connected()
    await message.answer("🟢 Подключено" if connected else "🟠 Нет подключения к сервису прогноза.")


@router.message(Command("id"))
async def show_user_id(message: Message):
    await message.answer(f"Ваш Telegram ID: {user_id(message)}")


@router.message(Command("train"))
@router.message(F.text.in_((MENU_TRAINING, menu_text(MENU_TRAINING))))
async def confirm_training(message: Message, state: FSMContext, training: TrainingControls):
    sender = user_id(message)
    try:
        data = await training.request(sender)
    except WeatherApiError as error:
        await message.answer(str(error))
        return
    if data.get("status") == "running":
        await training.present(message, sender, data)
        return
    prompt = await message.answer(
        "<b>⚙️ Обучение моделей</b>\n\n"
        "Сервер обучит все модели и опубликует новый выпуск. Бот покажет этап и число готовых моделей.",
        parse_mode=ParseMode.HTML, reply_markup=training_keyboard(),
    )
    await state.update_data(training_prompt=prompt.message_id)


@router.callback_query(F.data == "train_start")
async def start_training(callback: CallbackQuery, state: FSMContext, training: TrainingControls):
    message = callback.message
    if not isinstance(message, Message) or message.message_id != (await state.get_data()).get("training_prompt"):
        await callback.answer("Подтверждение устарело. Используйте /train.")
        return
    await callback.answer()
    await state.update_data(training_prompt=None)
    await message.edit_reply_markup(reply_markup=None)
    await training.show(message, callback.from_user.id, start=True)


@router.message(Command("training_status"))
async def training_status(message: Message, training: TrainingControls):
    await training.show(message, user_id(message))


@router.callback_query(F.data == "train_status")
async def training_status_button(callback: CallbackQuery, training: TrainingControls):
    await callback.answer()
    if isinstance(callback.message, Message):
        await training.show(callback.message, callback.from_user.id)


@router.message(Command("forecast"))
@router.message(F.text.in_((MENU_FORECAST, menu_text(MENU_FORECAST))))
async def begin_forecast(message: Message, state: FSMContext):
    await hide_keyboard(message, state)
    await state.set_state(Forecast.location)
    await state.update_data(weather={}, step=0)
    prompt = await message.answer(
        "<b>Станция наблюдений</b>\n\nВыберите станцию из списка или введите её название.",
        parse_mode=ParseMode.HTML,
        reply_markup=location_keyboard(),
    )
    await state.update_data(keyboard_id=prompt.message_id)


@router.callback_query(F.data == "forecast_start")
async def start_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if isinstance(callback.message, Message):
        await begin_forecast(callback.message, state)


@router.callback_query(Forecast.location, LocationPage.filter((F.number >= 0) & (F.number <= LAST_PAGE)))
async def change_location_page(callback: CallbackQuery, callback_data: LocationPage, state: FSMContext):
    message = await current_keyboard(callback, state)
    if message is not None:
        await message.edit_reply_markup(reply_markup=location_keyboard(callback_data.number))


async def save_location(message: Message, state: FSMContext, location: str):
    await hide_keyboard(message, state)
    await state.update_data(weather={"Location": location})
    await state.set_state(Forecast.measurement)
    await ask_measurement(message, 0)


@router.callback_query(Forecast.location, LocationChoice.filter((F.index >= 0) & (F.index < len(LOCATIONS))))
async def choose_location(callback: CallbackQuery, callback_data: LocationChoice, state: FSMContext):
    message = await current_keyboard(callback, state)
    if message is not None:
        await save_location(message, state, LOCATIONS[callback_data.index])


@router.message(Forecast.location)
async def type_location(message: Message, state: FSMContext):
    name = "".join((message.text or "").split()).casefold()
    location = LOCATION_NAMES.get(name)
    if location is None:
        await message.answer("Места с таким названием нет в списке. Выберите место из списка или проверьте написание.")
        return
    await save_location(message, state, location)


async def ask_measurement(message: Message, step: int):
    name, title, unit, _ = MEASUREMENTS[step]
    minimum, maximum = WEATHER_LIMITS[name]
    await message.answer(
        f"<b>{escape(title)}</b>\nВведите число от {minimum} до {maximum} {escape(unit)}.\n"
        f"<i>Измерение {step + 1} из {len(MEASUREMENTS)}</i>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Forecast.measurement)
async def read_measurement(message: Message, state: FSMContext):
    data = await state.get_data()
    step = data["step"]
    name, title, unit, _ = MEASUREMENTS[step]
    try:
        value = parse_measurement(name, title, unit, message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return

    step += 1
    await state.update_data(weather={**data["weather"], name: value}, step=step)
    if step < len(MEASUREMENTS):
        await ask_measurement(message, step)
        return
    await state.set_state(Forecast.wind)
    prompt = await message.answer(
        "<b>Направление ветра в 15:00</b>\n\nВыберите, откуда дует ветер. Например, NW означает северо-запад.",
        parse_mode=ParseMode.HTML,
        reply_markup=wind_keyboard(),
    )
    await state.update_data(keyboard_id=prompt.message_id)


async def send_forecast(message: Message, state: FSMContext, weather_api: WeatherApi):
    data = await state.get_data()
    weather = data["weather"]
    try:
        rain, probability, version, model_id = await weather_api.predict(weather, **await selected_model(state))
    except WeatherApiError as error:
        await state.set_state(Forecast.retry)
        prompt = await message.answer(str(error), reply_markup=forecast_menu(retry=True))
        await state.update_data(keyboard_id=prompt.message_id)
        return

    await reset_forecast(state)
    verdict = "🌧 Завтра ожидается дождь" if rain else "☀️ Завтра дождь не ожидается"
    location = escape(weather["Location"])
    text = (
        f"<b>{verdict}</b>\n\n"
        f"Станция: {location}\n"
        f"Вероятность дождя: <b>{format_probability(probability)}</b>"
    )
    if version:
        model = f"{model_id} (v{version})" if model_id else f"v{version}"
        text += f"\n\nМодель: {escape(model)}"
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.callback_query(Forecast.wind, WindChoice.filter(F.code.in_(WIND_CODES)))
async def choose_wind(
    callback: CallbackQuery, callback_data: WindChoice, state: FSMContext, weather_api: WeatherApi
):
    message = await current_keyboard(callback, state)
    if message is not None:
        await hide_keyboard(message, state)
        data = await state.get_data()
        await state.update_data(weather={**data["weather"], "WindDir3pm": callback_data.code})
        await send_forecast(message, state, weather_api)


@router.callback_query(Forecast.retry, F.data == "forecast_retry")
async def retry_forecast(callback: CallbackQuery, state: FSMContext, weather_api: WeatherApi):
    message = await current_keyboard(callback, state)
    if message is not None:
        await hide_keyboard(message, state)
        await send_forecast(message, state, weather_api)


@router.message(Forecast.wind)
async def remind_wind(message: Message):
    await message.answer("Выберите направление ветра кнопкой в предыдущем сообщении.")


@router.message(Forecast.retry)
async def remind_retry(message: Message):
    await message.answer("Нажмите «Повторить» под последним сообщением или начните заново через /forecast.")


@router.callback_query(F.data.startswith(("station:", "stations:", "wind:", "forecast_retry", "forecast_status")))
async def stale_button(callback: CallbackQuery):
    await callback.answer("Эта кнопка устарела. Используйте /forecast.")
