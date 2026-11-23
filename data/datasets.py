import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent
RAW_WEATHER_FILE = DATA_DIR / "raw" / "weatherAUS.csv"
PROCESSED_DIR = DATA_DIR / "processed"


def load_raw_weather():
    return pd.read_csv(RAW_WEATHER_FILE)


def load_training_data():
    X_train = pd.read_csv(PROCESSED_DIR / "X_train.csv")
    X_test = pd.read_csv(PROCESSED_DIR / "X_test.csv")
    y_train = pd.read_csv(PROCESSED_DIR / "y_train.csv").values.ravel()
    y_test = pd.read_csv(PROCESSED_DIR / "y_test.csv").values.ravel()
    return X_train, X_test, y_train, y_test


def load_preprocess_params():
    return json.loads((PROCESSED_DIR / "preprocess_params.json").read_text(encoding="utf-8"))


def save_training_data(X_train, X_test, y_train, y_test, preprocess_params):
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    X_train.to_csv(PROCESSED_DIR / "X_train.csv", index=False)
    X_test.to_csv(PROCESSED_DIR / "X_test.csv", index=False)
    y_train.to_csv(PROCESSED_DIR / "y_train.csv", index=False)
    y_test.to_csv(PROCESSED_DIR / "y_test.csv", index=False)
    (PROCESSED_DIR / "preprocess_params.json").write_text(
        json.dumps(preprocess_params, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
