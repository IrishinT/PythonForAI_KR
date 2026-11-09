import numpy as np
import pandas as pd
from sklearn.model_selection import (
    train_test_split,
) 

df = pd.read_csv("weatherAUS.csv")
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
df["RainToday"] = df["RainToday"].map({"No": 0, "Yes": 1})

# Разделяем на числовые и категориальные признаки
num_cols = df.select_dtypes(include=[np.number]).columns.drop("RainTomorrow")
cat_cols = df.select_dtypes(include=["object", "str"]).columns

# Заполняем числовые признаки медианой
for col in num_cols:
    median_val = df[col].median()
    df[col] = df[col].fillna(median_val)

# Заполняем категориальные признаки модой
for col in cat_cols:
    mode_val = df[col].mode()[0]
    df[col] = df[col].fillna(mode_val)

print(f"Осталось пропусков в датасете = {df.isnull().sum().sum()}")

# Кодирование категориальных признаков One-Hot Encoding
df = pd.get_dummies(df, columns=cat_cols, drop_first=True, dtype=int)
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
train_mean = X_train[num_cols].mean()
train_std = X_train[num_cols].std()

# (X - mu) / sigma
X_train[num_cols] = (X_train[num_cols] - train_mean) / train_std
X_test[num_cols] = (X_test[num_cols] - train_mean) / train_std

print(f"Размер X_train: {X_train.shape}")
print(f"Размер X_test:  {X_test.shape}")

X_train.to_csv("X_train.csv", index=False)
X_test.to_csv("X_test.csv", index=False)
y_train.to_csv("y_train.csv", index=False)
y_test.to_csv("y_test.csv", index=False)

print("Результат сохранён в X_train.csv, X_test.csv, y_train.csv, y_test.csv")