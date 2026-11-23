from aiogram import F, Router
from aiogram.enums import ChatType
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

from .keyboards import (
    LAST_PAGE,
    LocationChoice,
    LocationPage,
    WindChoice,
    forecast_menu,
    location_keyboard,
    wind_keyboard,
)
from .weather_api import WeatherApi, WeatherApiError

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

LOCATION_NAMES = {name.casefold(): name for name in LOCATIONS}
WIND_CODES = {code for code, _ in WIND_DIRECTIONS}


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


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await hide_keyboard(message, state)
    await state.clear()
    await message.answer(
        "Чтобы узнать, будет ли дождь завтра, введите семь параметров сегодняшней погоды.",
        reply_markup=forecast_menu(),
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await hide_keyboard(message, state)
    await state.clear()
    await message.answer("Ввод отменён.", reply_markup=forecast_menu())


@router.message(Command("status"))
async def status(message: Message, weather_api: WeatherApi):
    connected = await weather_api.is_connected()
    await message.answer("🟢 Подключено" if connected else "🟠 Нет подключения к сервису прогноза.")


@router.message(Command("forecast"))
async def begin_forecast(message: Message, state: FSMContext):
    await hide_keyboard(message, state)
    await state.set_state(Forecast.location)
    await state.set_data({"weather": {}, "step": 0})
    prompt = await message.answer(
        "Где сделаны наблюдения? Выберите место из списка или напишите его название.",
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
    _, title, unit, example = MEASUREMENTS[step]
    await message.answer(f"{title}, {unit}. Например, {example}.")


@router.message(Forecast.measurement)
async def read_measurement(message: Message, state: FSMContext):
    data = await state.get_data()
    step = data["step"]
    name, title, _, _ = MEASUREMENTS[step]
    try:
        value = parse_measurement(name, title, message.text or "")
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
        "Выберите направление ветра в 15:00. N — север, E — восток, S — юг, W — запад.",
        reply_markup=wind_keyboard(),
    )
    await state.update_data(keyboard_id=prompt.message_id)


async def send_forecast(message: Message, state: FSMContext, weather_api: WeatherApi):
    data = await state.get_data()
    weather = data["weather"]
    try:
        rain, probability = await weather_api.predict(weather)
    except WeatherApiError as error:
        await state.set_state(Forecast.retry)
        prompt = await message.answer(str(error), reply_markup=forecast_menu(retry=True))
        await state.update_data(keyboard_id=prompt.message_id)
        return

    await state.clear()
    verdict = "🌧 Ожидается дождь" if rain else "☀️ Дождь не ожидается"
    await message.answer(
        f"{verdict}\n{weather['Location']} · завтра\nВероятность дождя: {format_probability(probability)}",
        reply_markup=forecast_menu(),
    )


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
