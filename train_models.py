import time
import warnings
import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GridSearchCV, StratifiedShuffleSplit
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1000)

# Загрузка подготовленных данных
print("Загрузка обучающей и тестовой выборок...")
X_train = pd.read_csv("X_train.csv")
X_test = pd.read_csv("X_test.csv")
y_train = pd.read_csv("y_train.csv").values.ravel()
y_test = pd.read_csv("y_test.csv").values.ravel()

print(f"X_train: {X_train.shape}, X_test: {X_test.shape}")

# Подвыборка (25 000 строк) для быстрого подбора гиперпараметров тяжелых моделей (KNN)
sss = StratifiedShuffleSplit(n_splits=1, train_size=25000, random_state=42)
sample_idx, _ = next(sss.split(X_train, y_train))
X_train_sub = X_train.iloc[sample_idx]
y_train_sub = y_train[sample_idx]

# Конфигурация моделей и сеток гиперпараметров
models_config = {
    "Logistic Regression": {
        "estimator": LogisticRegression(max_iter=1000, random_state=42),
        "param_grid": {
            "C": [0.01, 0.1, 1.0, 10.0],
            "class_weight": [None, "balanced"],
        },
        "use_subsample": False,
    },
    "Decision Tree": {
        "estimator": DecisionTreeClassifier(random_state=42),
        "param_grid": {
            "max_depth": [5, 10, 15],
            "min_samples_leaf": [10, 50, 100],
            "criterion": ["gini", "entropy"],
        },
        "use_subsample": False,
    },
    "KNN": {
        "estimator": KNeighborsClassifier(n_jobs=-1),
        "param_grid": {
            "n_neighbors": [7, 15, 25],
            "weights": ["uniform", "distance"],
        },
        "use_subsample": True,
    },
    "Random Forest": {
        "estimator": RandomForestClassifier(random_state=42, n_jobs=-1),
        "param_grid": {
            "n_estimators": [100, 150],
            "max_depth": [12, 18, None],
            "min_samples_leaf": [2, 10],
        },
        "use_subsample": True,
    },
}

results = []
trained_models = {}
roc_data = {}

# Цикл подбора гиперпараметров, обучения и оценки
print("\nНачало обучения и подбора гиперпараметров...")
for name, config in models_config.items():
    start_time = time.time()
    print(f"\n--- Модель: {name} ---")

    X_fit = X_train_sub if config["use_subsample"] else X_train
    y_fit = y_train_sub if config["use_subsample"] else y_train

    grid = GridSearchCV(
        estimator=config["estimator"],
        param_grid=config["param_grid"],
        scoring="f1",
        cv=3,
        n_jobs=-1,
    )
    grid.fit(X_fit, y_fit)
    best_params = grid.best_params_
    print(f"Лучшие гиперпараметры: {best_params}")

    # Если искали параметры на подвыборке, обучаем лучшую модель на всем X_train
    best_model = grid.best_estimator_
    if config["use_subsample"] and name != "KNN":
        print("Обучение лучшей конфигурации на полной выборке X_train...")
        best_model.fit(X_train, y_train)

    # Предсказание на тестовой выборке
    y_pred = best_model.predict(X_test)
    y_proba = best_model.predict_proba(X_test)[:, 1]

    # Расчет метрик
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, y_proba)
    elapsed = time.time() - start_time

    print(
        f"Accuracy: {acc:.4f} | Precision: {prec:.4f} | Recall: {rec:.4f} | "
        f"F1-score: {f1:.4f} | ROC-AUC: {roc_auc:.4f} (Время: {elapsed:.1f} сек)"
    )

    results.append(
        {
            "Модель": name,
            "Лучшие параметры": str(best_params),
            "Accuracy": round(acc, 4),
            "Precision": round(prec, 4),
            "Recall": round(rec, 4),
            "F1-score": round(f1, 4),
            "ROC-AUC": round(roc_auc, 4),
            "Время (с)": round(elapsed, 1),
        }
    )

    trained_models[name] = best_model
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    roc_data[name] = (fpr, tpr, roc_auc)

results_df = pd.DataFrame(results).sort_values(by="ROC-AUC", ascending=False).reset_index(drop=True)
print("\n================ СВОДНАЯ ТАБЛИЦА МЕТРИК ================")
print(results_df.to_string(index=False))
results_df.to_csv("models_metrics_comparison.csv", index=False)

best_model_name = results_df.iloc[0]["Модель"]
best_model_instance = trained_models[best_model_name]
print(f"\nЛучшая модель по ROC-AUC: {best_model_name}")

# ROC-кривые всех моделей
plt.figure(figsize=(8, 6))
for name, (fpr, tpr, auc_val) in roc_data.items():
    plt.plot(fpr, tpr, linewidth=2, label=f"{name} (AUC = {auc_val:.4f})")

plt.plot([0, 1], [0, 1], "k--", label="Случайный классификатор (AUC = 0.5000)")
plt.xlabel("False Positive Rate (Доля ложных срабатываний)")
plt.ylabel("True Positive Rate (Полнота / Recall)")
plt.title("ROC-кривые моделей классификации погодных условий")
plt.legend(loc="lower right")
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig("models_roc_curves.png", dpi=300)
plt.show()

# Сравнение метрик (Столбчатая диаграмма)
metrics_melted = results_df.melt(
    id_vars="Модель",
    value_vars=["Accuracy", "Precision", "Recall", "F1-score", "ROC-AUC"],
    var_name="Метрика",
    value_name="Значение",
)
plt.figure(figsize=(10, 6))
sns.barplot(data=metrics_melted, x="Метрика", y="Значение", hue="Модель", palette="viridis")
plt.ylim(0.4, 1.0)
plt.title("Сравнение показателей качества моделей классификации")
plt.ylabel("Значение метрики")
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("models_metrics_comparison.png", dpi=300)
plt.show()

# Матрица ошибок (Confusion Matrix) для лучшей модели
y_pred_best = best_model_instance.predict(X_test)
cm = confusion_matrix(y_test, y_pred_best)

plt.figure(figsize=(6, 5))
sns.heatmap(
    cm,
    annot=True,
    fmt="d",
    cmap="Blues",
    xticklabels=["Нет дождя (0)", "Дождь (1)"],
    yticklabels=["Нет дождя (0)", "Дождь (1)"],
)
plt.title(f"Матрица ошибок лучшей модели ({best_model_name})")
plt.xlabel("Предсказанный класс")
plt.ylabel("Истинный класс")
plt.tight_layout()
plt.savefig("best_model_confusion_matrix.png", dpi=300)
plt.show()

# Анализ важности признаков (Feature Importance)
if hasattr(best_model_instance, "feature_importances_"):
    importances = best_model_instance.feature_importances_
elif hasattr(best_model_instance, "coef_"):
    importances = np.abs(best_model_instance.coef_[0])
else:
    importances = trained_models["Random Forest"].feature_importances_

feat_imp_df = (
    pd.DataFrame({"Признак": X_train.columns, "Важность": importances})
    .sort_values(by="Важность", ascending=False)
    .head(15)
)

print("\n================ 15 САМЫХ ВАЖНЫХ ПРИЗНАКОВ ================")
print(feat_imp_df.to_string(index=False))

plt.figure(figsize=(10, 6))
sns.barplot(
    data=feat_imp_df,
    x="Важность",
    y="Признак",
    palette="magma",
    hue="Признак",
    legend=False,
)
plt.title(f"15 наиболее значимых признаков ({best_model_name})")
plt.xlabel("Относительная важность признака")
plt.ylabel("Признак")
plt.tight_layout()
plt.savefig("feature_importance.png", dpi=300)
plt.show()

# Сохранение лучшей модели и списка колонок
joblib.dump(best_model_instance, "best_weather_model.pkl")
joblib.dump(list(X_train.columns), "model_columns.pkl")
print(f"\nЛучшая модель сохранена в 'best_weather_model.pkl'")
print("Список признаков сохранен в 'model_columns.pkl'")