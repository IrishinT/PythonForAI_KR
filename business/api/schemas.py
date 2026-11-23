from pydantic import BaseModel, Field

from business.weather_limits import WEATHER_LIMITS


def measurement_field(name):
    minimum, maximum = WEATHER_LIMITS[name]
    return Field(default=None, ge=minimum, le=maximum, allow_inf_nan=False)


class WeatherInput(BaseModel):
    MinTemp: float | None = measurement_field("MinTemp")
    MaxTemp: float | None = None
    Rainfall: float | None = measurement_field("Rainfall")
    WindGustSpeed: float | None = measurement_field("WindGustSpeed")
    WindSpeed9am: float | None = None
    WindSpeed3pm: float | None = None
    Humidity9am: float | None = None
    Humidity3pm: float | None = measurement_field("Humidity3pm")
    Pressure9am: float | None = None
    Pressure3pm: float | None = measurement_field("Pressure3pm")
    Temp9am: float | None = None
    Temp3pm: float | None = None
    RainToday: str | None = Field(default="No", examples=["No", "Yes"])
    Month: int = Field(default=6, ge=1, le=12)

    Location: str | None = Field(default="Sydney", examples=["Sydney", "Melbourne"])
    WindGustDir: str | None = Field(default=None, examples=["W", "NW", "SSE"])
    WindDir9am: str | None = Field(default=None, examples=["W", "NW", "SSE"])
    WindDir3pm: str | None = Field(default=None, examples=["W", "NW", "SSE"])
