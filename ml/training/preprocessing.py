import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data.datasets import load_raw_weather, save_training_data
from ml.features import encode_categories, encode_rain_today, fill_missing, scale_numeric


df = load_raw_weather()
print(f"Загружен датасет: {df.shape} строк")

# Удаление признаков с экстремальным количеством пропусков (>38%)
cols_to_drop = ["Sunshine", "Evaporation", "Cloud3pm", "Cloud9am"]
df = df.drop(columns=cols_to_drop)
print(f"Удалены столбцы с >38% пропусков: {cols_to_drop}")

# Удаляем строки, где нет целевой метки RainTomorrow
df = df.dropna(subset=["RainTomorrow"])

# Извлечение месяца (сезонность) и удаление самой даты
df["Date"] = pd.to_datetime(df["Date"])
df["Month"] = df["Date"].dt.month
df = df.drop(columns=["Date"])

# биннаризация переменных
df["RainTomorrow"] = (df["RainTomorrow"] == "Yes").astype(int)
df["RainToday"] = encode_rain_today(df["RainToday"])

# Разделяем на числовые и категориальные признаки
num_cols = df.select_dtypes(include=[np.number]).columns.drop("RainTomorrow")
cat_cols = df.select_dtypes(include=["object", "str"]).columns

# Заполняем числовые признаки медианой
medians = {col: float(df[col].median()) for col in num_cols}

# Заполняем категориальные признаки модой
modes = {col: str(df[col].mode()[0]) for col in cat_cols}
df = fill_missing(df, medians, modes)

print(f"Осталось пропусков в датасете = {df.isnull().sum().sum()}")

# Кодирование категориальных признаков One-Hot Encoding
df = encode_categories(df, cat_cols, drop_first=True)
print(f"Размер после One-Hot Encoding: {df.shape}")

# Разделение на X (признаки) и y (цель)
X = df.drop(columns=["RainTomorrow"])
y = df["RainTomorrow"]

# 80% на обучение, 20% на тест. stratify=y сохраняет пропорцию классов 78/22
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# Для алгоритмов KNN и Logistic Regression необходимо приведение к одному масштабу.
# Подсчёт среднего и стандартного отклонения на X_train:
train_mean = {col: float(value) for col, value in X_train[num_cols].mean().items()}
train_std = {col: float(value) for col, value in X_train[num_cols].std().items()}

# (X - mu) / sigma
X_train = scale_numeric(X_train, train_mean, train_std)
X_test = scale_numeric(X_test, train_mean, train_std)

print(f"Размер X_train: {X_train.shape}")
print(f"Размер X_test:  {X_test.shape}")


preprocess_params = {
    "medians": medians,
    "modes": modes,
    "mean": train_mean,
    "std": train_std,
}
save_training_data(X_train, X_test, y_train, y_test, preprocess_params)

print("Выборки и параметры преобразования сохранены в data/processed/")
