from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from presentation.weather_input import LOCATIONS, WIND_DIRECTIONS

LOCATIONS_PER_PAGE = 12
LAST_PAGE = (len(LOCATIONS) - 1) // LOCATIONS_PER_PAGE


class LocationChoice(CallbackData, prefix="station"):
    index: int


class LocationPage(CallbackData, prefix="stations"):
    number: int


class WindChoice(CallbackData, prefix="wind"):
    code: str


def forecast_menu(retry=False):
    buttons = []
    if retry:
        buttons.append([InlineKeyboardButton(text="Повторить", callback_data="forecast_retry")])
    buttons.append([InlineKeyboardButton(text="Получить прогноз", callback_data="forecast_start")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def location_keyboard(page=0):
    keyboard = InlineKeyboardBuilder()
    start = page * LOCATIONS_PER_PAGE
    for index, name in enumerate(LOCATIONS[start:start + LOCATIONS_PER_PAGE], start=start):
        keyboard.button(text=name, callback_data=LocationChoice(index=index))
    keyboard.adjust(3)

    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="‹ Назад", callback_data=LocationPage(number=page - 1).pack()))
    if page < LAST_PAGE:
        navigation.append(InlineKeyboardButton(text="Дальше ›", callback_data=LocationPage(number=page + 1).pack()))
    if navigation:
        keyboard.row(*navigation)
    return keyboard.as_markup()


def wind_keyboard():
    keyboard = InlineKeyboardBuilder()
    for code, _ in WIND_DIRECTIONS:
        keyboard.button(text=code, callback_data=WindChoice(code=code))
    keyboard.adjust(4)
    return keyboard.as_markup()
