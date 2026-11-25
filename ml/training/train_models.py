import json
import sys
import time
import warnings
from argparse import ArgumentParser
from contextlib import nullcontext
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from joblib import parallel_config

from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier

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
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from business.model_registry import ModelCandidate, save_model_release
from data.datasets import load_preprocess_params, load_training_data
from ml.features import KEY_WEATHER_FIELDS, select_preprocess_params
from ml.training.model_diagnostics import evaluation_diagnostics, learning_diagnostics, render_model_charts

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
parser = ArgumentParser(description="Обучить и опубликовать выпуск моделей")
parser.add_argument("--result-file", type=Path, help="Записать номер выпуска для API без общих отчётов")
parser.add_argument("--progress-file", type=Path, help="Записывать этапы обучения для API")
args = parser.parse_args()
result_file = args.result_file
jobs = 2 if result_file else -1


def report_progress(stage, *, model_name=None, completed_models=0, total_models=None):
    if args.progress_file is None:
        return
    event = {
        "stage": stage,
        "model_name": model_name,
        "completed_models": completed_models,
        "total_models": total_models,
    }
    with args.progress_file.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1000)

# Загрузка подготовленных данных
report_progress("preparing")
print("Загрузка обучающей и тестовой выборок...")
X_train, X_test, y_train, y_test = load_training_data()
preprocess_params = select_preprocess_params(load_preprocess_params(), KEY_WEATHER_FIELDS)

# У города и направления ветра по несколько one-hot столбцов.
columns = [column for column in X_train if column.partition("_")[0] in KEY_WEATHER_FIELDS]
prepared_fields = {column.partition("_")[0] for column in columns}
parameter_fields = preprocess_params["mean"].keys() | preprocess_params["modes"].keys()
missing = set(KEY_WEATHER_FIELDS) - (prepared_fields & parameter_fields)
if missing:
    raise ValueError(f"В обучающей выборке нет полей: {', '.join(sorted(missing))}")
X_train = X_train[columns]
X_test = X_test[columns]

print(f"Поля для обучения: {', '.join(KEY_WEATHER_FIELDS)}")
print(f"X_train: {X_train.shape}, X_test: {X_test.shape}")

# Подвыборка (25 000 строк) для быстрого подбора гиперпараметров тяжелых моделей (KNN)
sss = StratifiedShuffleSplit(n_splits=1, train_size=25000, random_state=42)
sample_idx, _ = next(sss.split(X_train, y_train))
X_train_sub = X_train.iloc[sample_idx]
y_train_sub = y_train[sample_idx]

# Конфигурация моделей и сеток гиперпараметров
models_config = {
    "Logistic Regression": {
        "id": "logistic-regression",
        "estimator": LogisticRegression(max_iter=1000, random_state=42),
        "param_grid": {
            "C": [0.01, 0.1, 1.0, 10.0],
            "class_weight": [None, "balanced"],
        },
        "use_subsample": False,
    },
    "Decision Tree": {
        "id": "decision-tree",
        "estimator": DecisionTreeClassifier(random_state=42),
        "param_grid": {
            "max_depth": [5, 10, 15],
            "min_samples_leaf": [10, 50, 100],
            "criterion": ["gini", "entropy"],
        },
        "use_subsample": False,
    },
    "KNN": {
        "id": "knn",
        "estimator": KNeighborsClassifier(n_jobs=jobs),
        "param_grid": {
            "n_neighbors": [7, 15, 25],
            "weights": ["uniform", "distance"],
        },
        "use_subsample": True,
    },
    "Random Forest": {
        "id": "random-forest",
        "estimator": RandomForestClassifier(random_state=42, n_jobs=jobs),
        "param_grid": {
            "n_estimators": [100, 150],
            "max_depth": [12, 18, None],
            "min_samples_leaf": [2, 10],
        },
        "use_subsample": True,
    },
    "Neural Network (MLP)": {
        "id": "mlp",
        "estimator": MLPClassifier(
            random_state=42, 
            max_iter=100, 
            early_stopping=True,
            n_iter_no_change=5
        ),
        "param_grid": {
            "hidden_layer_sizes": [(64,), (64, 32)],
            "activation": ["relu"],
            "alpha": [0.0001, 0.01],
        },
        "use_subsample": False,
    },
}

results = []
release_models = {}
roc_data = {}

# Цикл подбора гиперпараметров, обучения и оценки
print("\nНачало обучения и подбора гиперпараметров...")
for name, config in models_config.items():
    start_time = time.time()
    print(f"\n--- Модель: {name} ---")

    X_fit = X_train_sub if config["use_subsample"] else X_train
    y_fit = y_train_sub if config["use_subsample"] else y_train
    progress = {"model_name": name, "completed_models": len(release_models), "total_models": len(models_config)}

    report_progress("searching", **progress)
    grid = GridSearchCV(
        estimator=config["estimator"],
        param_grid=config["param_grid"],
        scoring="f1",
        cv=3,
        n_jobs=jobs,
        refit=False,
    )
    with parallel_config(backend="threading") if result_file else nullcontext():
        grid.fit(X_fit, y_fit)
    best_params = grid.best_params_
    print(f"Лучшие гиперпараметры: {best_params}")

    # Если искали параметры на подвыборке, обучаем лучшую модель на всем X_train
    report_progress("fitting", **progress)
    best_model = clone(config["estimator"]).set_params(**best_params)
    if config["use_subsample"] and name != "KNN":
        print("Обучение лучшей конфигурации на полной выборке X_train...")
        X_fit, y_fit = X_train, y_train
    best_model.fit(X_fit, y_fit)

    # Предсказание на тестовой выборке
    report_progress("evaluating", **progress)
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

    metrics = {
        "Accuracy": acc,
        "Precision": prec,
        "Recall": rec,
        "F1-score": f1,
        "ROC-AUC": roc_auc,
    }
    report_progress("charting", **progress)
    evaluation = evaluation_diagnostics(y_test, y_pred, y_proba)
    learning = learning_diagnostics(best_model, X_train, y_train, X_test, y_test)
    release_models[config["id"]] = ModelCandidate(best_model, name, metrics, render_model_charts(evaluation, learning))
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    roc_data[name] = (fpr, tpr, roc_auc)

report_progress("publishing", completed_models=len(release_models), total_models=len(models_config))
results_df = pd.DataFrame(results).sort_values(by="ROC-AUC", ascending=False).reset_index(drop=True)
print("\n================ СВОДНАЯ ТАБЛИЦА МЕТРИК ================")
print(results_df.to_string(index=False))

best_model = max(release_models.values(), key=lambda candidate: candidate.metrics["ROC-AUC"])
best_model_name = best_model.name
best_model_instance = best_model.estimator
print(f"\nЛучшая модель по ROC-AUC: {best_model_name}")
release_version = save_model_release(release_models, X_train.columns, preprocess_params)
print(f"Модели сохранены в artifacts/v{release_version}/")

if result_file:
    result_file.write_text(release_version, encoding="utf-8")
    sys.exit(0)

REPORTS_DIR.mkdir(exist_ok=True)
results_df.to_csv(REPORTS_DIR / "models_metrics_comparison.csv", index=False)

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
plt.savefig(REPORTS_DIR / "models_roc_curves.png", dpi=300)
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
plt.savefig(REPORTS_DIR / "models_metrics_comparison.png", dpi=300)
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
plt.savefig(REPORTS_DIR / "best_model_confusion_matrix.png", dpi=300)
plt.show()

# Анализ важности признаков (Feature Importance)
importance_model_name = best_model_name
if hasattr(best_model_instance, "feature_importances_"):
    importances = best_model_instance.feature_importances_
elif hasattr(best_model_instance, "coef_"):
    importances = np.abs(best_model_instance.coef_[0])
else:
    importance_model = release_models["random-forest"]
    importance_model_name = importance_model.name
    importances = importance_model.estimator.feature_importances_

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
plt.title(f"15 наиболее значимых признаков ({importance_model_name})")
plt.xlabel("Относительная важность признака")
plt.ylabel("Признак")
plt.tight_layout()
plt.savefig(REPORTS_DIR / "feature_importance.png", dpi=300)
plt.show()
