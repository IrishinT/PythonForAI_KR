from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from presentation.weather_input import LOCATIONS, WIND_DIRECTIONS

LOCATIONS_PER_PAGE = 12
LAST_PAGE = (len(LOCATIONS) - 1) // LOCATIONS_PER_PAGE
WIND_ARROWS = ("⬆️", "↗️", "➡️", "↘️", "⬇️", "↙️", "⬅️", "↖️")
VERSIONS_PER_PAGE = 8
MENU_FORECAST = "Прогноз"
MENU_MODEL = "Модель"
MENU_METRICS = "Метрики"
MENU_TRAINING = "Обучение"
MENU_STATUS = "Статус API"
MENU_HELP = "Справка"
MENU_ABOUT = "О боте"
MENU_ICONS = {
    MENU_FORECAST: "🌦️",
    MENU_MODEL: "🧩",
    MENU_METRICS: "📊",
    MENU_TRAINING: "⚙️",
}


class LocationChoice(CallbackData, prefix="station"):
    index: int


class LocationPage(CallbackData, prefix="stations"):
    number: int


class WindChoice(CallbackData, prefix="wind"):
    code: str


class ReleasePage(CallbackData, prefix="releases"):
    page: int


class ReleaseChoice(CallbackData, prefix="release"):
    version: str


class ModelChoice(CallbackData, prefix="model"):
    version: str
    index: int


def menu_text(label):
    icon = MENU_ICONS.get(label)
    return f"{icon} {label}" if icon else label


def main_menu(can_train=False):
    rows = [[MENU_FORECAST, MENU_MODEL], [MENU_METRICS, MENU_STATUS], [MENU_HELP, MENU_ABOUT]]
    if can_train:
        rows.append([MENU_TRAINING])
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=menu_text(label)) for label in row] for row in rows],
        resize_keyboard=True, is_persistent=True,
    )


def releases_keyboard(catalog, page):
    versions = catalog["versions"]
    first = page * VERSIONS_PER_PAGE
    keyboard = InlineKeyboardBuilder()
    for release in versions[first:first + VERSIONS_PER_PAGE]:
        version = release["model_version"]
        title = f"{version} (последняя)" if version == catalog["latest_version"] else version
        keyboard.button(text=title, callback_data=ReleaseChoice(version=version))
    keyboard.adjust(2)
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="Назад", callback_data=ReleasePage(page=page - 1).pack()))
    if first + VERSIONS_PER_PAGE < len(versions):
        navigation.append(InlineKeyboardButton(text="Дальше", callback_data=ReleasePage(page=page + 1).pack()))
    if navigation:
        keyboard.row(*navigation)
    keyboard.row(InlineKeyboardButton(text="Автоматически (последний выпуск)", callback_data="model_auto"))
    return keyboard.as_markup()


def models_keyboard(release, latest_version):
    version = release["model_version"]
    default = release["default_model_id"]
    keyboard = InlineKeyboardBuilder()
    for index, model in enumerate(release["models"]):
        name = model["model_name"]
        if model["model_id"] == default:
            suffix = "рекомендуемая" if version == latest_version else "по умолчанию"
            name = f"{name} ({suffix})"
        keyboard.button(text=name, callback_data=ModelChoice(version=version, index=index))
    keyboard.adjust(1)
    keyboard.row(InlineKeyboardButton(text="К выпускам", callback_data=ReleasePage(page=0).pack()))
    return keyboard.as_markup()


def training_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Запустить обучение", callback_data="train_start")],
        [InlineKeyboardButton(text="Проверить статус", callback_data="train_status")],
    ])


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
    # Коды идут по кругу от N. На одну стрелку приходится два направления.
    for index, (code, _) in enumerate(WIND_DIRECTIONS):
        keyboard.button(text=f"{WIND_ARROWS[index // 2]} {code}", callback_data=WindChoice(code=code))
    keyboard.adjust(4)
    return keyboard.as_markup()
