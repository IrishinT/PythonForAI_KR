import json
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field

from model_training.model_registry import load_versioned_model

app = FastAPI(title="Weather Rain Prediction API")

model, metadata = load_versioned_model()
FEATURE_NAMES: list[str] = metadata["feature_names"]

PREPROCESS = metadata.get("preprocess_params")
if PREPROCESS is None:
    fallback = Path("model_training/preprocess_params.json")
    if fallback.exists():
        PREPROCESS = json.loads(fallback.read_text(encoding="utf-8"))


class WeatherInput(BaseModel):
    MinTemp: Optional[float] = None
    MaxTemp: Optional[float] = None
    Rainfall: Optional[float] = None
    WindGustSpeed: Optional[float] = None
    WindSpeed9am: Optional[float] = None
    WindSpeed3pm: Optional[float] = None
    Humidity9am: Optional[float] = None
    Humidity3pm: Optional[float] = None
    Pressure9am: Optional[float] = None
    Pressure3pm: Optional[float] = None
    Temp9am: Optional[float] = None
    Temp3pm: Optional[float] = None
    RainToday: Optional[str] = Field(default="No", examples=["No", "Yes"])
    Month: int = Field(default=6, ge=1, le=12)

    Location: Optional[str] = Field(default="Sydney", examples=["Sydney", "Melbourne"])
    WindGustDir: Optional[str] = Field(default=None, examples=["W", "NW", "SSE"])
    WindDir9am: Optional[str] = Field(default=None, examples=["W", "NW", "SSE"])
    WindDir3pm: Optional[str] = Field(default=None, examples=["W", "NW", "SSE"])


def prepare_features(payload: WeatherInput) -> pd.DataFrame:
    row = {col: 0.0 for col in FEATURE_NAMES}
    data = payload.model_dump()

    rt = data.pop("RainToday")
    if isinstance(rt, str):
        data["RainToday"] = 1.0 if rt.strip().lower() == "yes" else 0.0
    elif rt is not None:
        data["RainToday"] = float(rt)
    else:
        data["RainToday"] = None

    cat_values = {
        "Location": data.pop("Location"),
        "WindGustDir": data.pop("WindGustDir"),
        "WindDir9am": data.pop("WindDir9am"),
        "WindDir3pm": data.pop("WindDir3pm"),
    }

    for cat_name, val in cat_values.items():
        if val is None and PREPROCESS:
            val = PREPROCESS["modes"].get(cat_name)
        if val:
            ohe_col = f"{cat_name}_{val}"
            if ohe_col in row:
                row[ohe_col] = 1.0

    for col, val in data.items():
        if val is None:
            val = PREPROCESS["medians"][col] if PREPROCESS else 0.0
        if PREPROCESS:
            val = (val - PREPROCESS["mean"][col]) / PREPROCESS["std"][col]
        row[col] = float(val)

    return pd.DataFrame([row], columns=FEATURE_NAMES)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": metadata["model_name"],
        "version": metadata["version"],
        "preprocess_loaded": PREPROCESS is not None,
    }


@app.post("/predict")
def predict(weather: WeatherInput):
    X = prepare_features(weather)
    proba = float(model.predict_proba(X)[0][1])
    return {
        "rain_tomorrow": proba >= 0.5,
        "probability": round(proba, 4),
        "model_version": metadata["version"],
    }