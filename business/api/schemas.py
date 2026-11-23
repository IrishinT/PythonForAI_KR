from pydantic import BaseModel, Field


class WeatherInput(BaseModel):
    MinTemp: float | None = None
    MaxTemp: float | None = None
    Rainfall: float | None = None
    WindGustSpeed: float | None = None
    WindSpeed9am: float | None = None
    WindSpeed3pm: float | None = None
    Humidity9am: float | None = None
    Humidity3pm: float | None = None
    Pressure9am: float | None = None
    Pressure3pm: float | None = None
    Temp9am: float | None = None
    Temp3pm: float | None = None
    RainToday: str | None = Field(default="No", examples=["No", "Yes"])
    Month: int = Field(default=6, ge=1, le=12)

    Location: str | None = Field(default="Sydney", examples=["Sydney", "Melbourne"])
    WindGustDir: str | None = Field(default=None, examples=["W", "NW", "SSE"])
    WindDir9am: str | None = Field(default=None, examples=["W", "NW", "SSE"])
    WindDir3pm: str | None = Field(default=None, examples=["W", "NW", "SSE"])
