import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1000)

df = pd.read_csv("weatherAUS.csv")

print(f"Загружен датасет: {df.shape[0]} строк, {df.shape[1]} колонок")

# Анализ пропусков
print("Статистика пропусков по признакам:")

missing_count = df.isnull().sum()
missing_percent = (missing_count / len(df)) * 100

missing_df = (
    pd.DataFrame(
        {
            "Колонка": df.columns,
            "Количество NaN": missing_count,
            "Процент NaN (%)": missing_percent.round(2),
        }
    )
    .sort_values(by="Процент NaN (%)", ascending=False)
    .reset_index(drop=True)
)

print(missing_df[missing_df["Количество NaN"] > 0].to_string())

plt.figure(figsize=(10, 6))

top_missing = missing_df[missing_df["Процент NaN (%)"] > 0]

sns.barplot(
    x="Процент NaN (%)",
    y="Колонка",
    data=top_missing,
    palette="viridis",
    hue="Колонка",
    legend=False,
)

plt.title("Процент пропущенных значений в признаках")
plt.xlabel("Процент пропусков (%)")
plt.ylabel("Признаки")
plt.tight_layout()
plt.savefig("ds_missing.png", dpi=300)
plt.show()


# Анализ целевого признака
print("Анализ целевого признака (RainTomorrow)")
target_counts = df["RainTomorrow"].value_counts(dropna=False)
target_percents = df["RainTomorrow"].value_counts(normalize=True, dropna=False) * 100

for val in target_counts.index:
    print(
        f"Значение '{val}': {target_counts[val]} строк ({target_percents[val]:.2f}%)"
    )

print("Анализ числовых данных")

num_cols = df.select_dtypes(include=[np.number]).columns
stats_num = df[num_cols].describe().T[["min", "mean", "50%", "max", "std"]]
stats_num = stats_num.rename(columns={"50%": "median"})

# Подсчёт ассиметрии (скошенность распределения). Если |skew| > 1, распределение несимметрично
stats_num["skewness"] = df[num_cols].skew().round(2)
print(stats_num.round(2).to_string())

# Визуализация выбросов и скошенност
plt.figure(figsize=(12, 4))

plt.subplot(1, 2, 1)
sns.histplot(df["Rainfall"], bins=40, kde=True, color="teal")
plt.title("Распределение осадков (Rainfall) - Скошенность")

plt.subplot(1, 2, 2)
sns.boxplot(x=df["Rainfall"], color="lightblue")
plt.title("Boxplot осадков (Rainfall) - Выбросы")

plt.tight_layout()
plt.savefig("ds_rainfall_distribution.png", dpi=300)
plt.show()


print("Анализ категориальных признаков")

cat_cols = df.select_dtypes(include=["object", "str"]).columns.drop(
    ["Date", "RainTomorrow"]
)

for col in cat_cols:
    unique_vals = df[col].nunique()
    mode_val = df[col].mode()[0]
    print(
        f"Колонка '{col}': уникальных значений = {unique_vals}, Самое частое (мода) = '{mode_val}'"
    )