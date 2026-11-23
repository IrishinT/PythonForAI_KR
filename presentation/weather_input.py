import re
from math import isfinite

MEASUREMENTS = (
    ("Humidity3pm", "Влажность в 15:00", "%", "70"),
    ("Pressure3pm", "Давление в 15:00", "гПа", "1015,2"),
    ("MinTemp", "Мин. температура", "°C", "12"),
    ("Rainfall", "Осадки за день", "мм", "0,6"),
    ("WindGustSpeed", "Макс. порыв ветра", "км/ч", "40"),
)
DECIMAL_PATTERN = r"(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)"

LOCATIONS = (
    "Adelaide", "Albany", "Albury", "AliceSprings", "BadgerysCreek", "Ballarat",
    "Bendigo", "Brisbane", "Cairns", "Canberra", "Cobar", "CoffsHarbour",
    "Dartmoor", "Darwin", "GoldCoast", "Hobart", "Katherine", "Launceston",
    "Melbourne", "MelbourneAirport", "Mildura", "Moree", "MountGambier",
    "MountGinini", "Newcastle", "Nhil", "NorahHead", "NorfolkIsland",
    "Nuriootpa", "PearceRAAF", "Penrith", "Perth", "PerthAirport", "Portland",
    "Richmond", "Sale", "SalmonGums", "Sydney", "SydneyAirport", "Townsville",
    "Tuggeranong", "Uluru", "WaggaWagga", "Walpole", "Watsonia", "Williamtown",
    "Witchcliffe", "Wollongong", "Woomera",
)

WIND_DIRECTIONS = (
    ("N", "Север"), ("NNE", "Северо-северо-восток"), ("NE", "Северо-восток"),
    ("ENE", "Востоко-северо-восток"), ("E", "Восток"), ("ESE", "Востоко-юго-восток"),
    ("SE", "Юго-восток"), ("SSE", "Юго-юго-восток"), ("S", "Юг"),
    ("SSW", "Юго-юго-запад"), ("SW", "Юго-запад"), ("WSW", "Западо-юго-запад"),
    ("W", "Запад"), ("WNW", "Западо-северо-запад"), ("NW", "Северо-запад"),
    ("NNW", "Северо-северо-запад"),
)


def measurement_pattern(name):
    return "-?" + DECIMAL_PATTERN if name == "MinTemp" else DECIMAL_PATTERN


def parse_measurement(name, title, text):
    text = text.strip()
    error = f"Введите число в поле «{title}»."
    if re.fullmatch(measurement_pattern(name), text) is None:
        raise ValueError(error)
    value = float(text.replace(",", "."))
    if not isfinite(value):
        raise ValueError(error)
    if name == "Humidity3pm" and not 0 <= value <= 100:
        raise ValueError("Влажность должна быть от 0 до 100%.")
    if name == "Pressure3pm" and not 900 <= value <= 1100:
        raise ValueError("Введите давление от 900 до 1100 гПа. Если оно указано в кПа, умножьте значение на 10.")
    return value


def format_probability(probability):
    number = f"{probability * 100:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{number}%"
