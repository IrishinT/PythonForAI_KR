from io import BytesIO

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from sklearn.base import clone
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedShuffleSplit


BLUE = "#255b9f"
GREEN = "#318359"


def evaluation_diagnostics(y_test, predictions, probabilities):
    fpr, tpr, _ = roc_curve(y_test, probabilities)
    precision, recall, _ = precision_recall_curve(y_test, probabilities)
    return {
        "roc": {"x": fpr, "y": tpr, "auc": roc_auc_score(y_test, probabilities)},
        "precision_recall": {
            "x": recall,
            "y": precision,
            "average_precision": average_precision_score(y_test, probabilities),
        },
        "confusion_matrix": confusion_matrix(y_test, predictions, labels=[0, 1]).tolist(),
    }


def learning_diagnostics(estimator, x_train, y_train, x_test, y_test):
    # Use the same held-out sample at every size to make the scores comparable.
    if len(y_test) > 4000:
        split = StratifiedShuffleSplit(n_splits=1, train_size=4000, random_state=42)
        indices, _ = next(split.split(x_test, y_test))
        x_test, y_test = x_test.iloc[indices], y_test[indices]

    sizes = [size for size in (500, 2000, 5000, 10000) if size < len(y_train)]
    train_scores, validation_scores = [], []
    for size in sizes:
        split = StratifiedShuffleSplit(n_splits=1, train_size=size, random_state=42)
        indices, _ = next(split.split(x_train, y_train))
        x_sample, y_sample = x_train.iloc[indices], y_train[indices]
        fitted = clone(estimator).fit(x_sample, y_sample)
        train_scores.append(roc_auc_score(y_sample, fitted.predict_proba(x_sample)[:, 1]))
        validation_scores.append(roc_auc_score(y_test, fitted.predict_proba(x_test)[:, 1]))

    return {
        "sizes": sizes,
        "train_auc": train_scores,
        "validation_auc": validation_scores,
        "validation_samples": len(y_test),
    }


def draw_curve(axis, series, title, x_label, y_label):
    axis.plot(series["x"], series["y"], color=BLUE, linewidth=2)
    axis.set(title=title, xlabel=x_label, ylabel=y_label, xlim=(0, 1), ylim=(0, 1.02))
    axis.grid(color="#e3eaf1")


def draw_roc(axis, series):
    draw_curve(axis, series, f"ROC · AUC {series['auc']:.4f}", "Доля ложных срабатываний", "Полнота")
    axis.plot([0, 1], [0, 1], color="#96a7ba", linestyle="--", linewidth=1)


def draw_precision_recall(axis, series):
    title = f"Precision–Recall · AP {series['average_precision']:.4f}"
    draw_curve(axis, series, title, "Полнота", "Точность")


def draw_learning(axis, series):
    sizes = series["sizes"]
    axis.plot(sizes, series["train_auc"], color=BLUE, marker="o", label="Обучающая")
    axis.plot(sizes, series["validation_auc"], color=GREEN, marker="o", label="Отложенная")
    lower = min(0.5, min(series["train_auc"]), min(series["validation_auc"]))
    axis.set(title="Кривая обучения", xlabel="Размер обучающей выборки", ylabel="ROC-AUC", ylim=(lower - 0.02, 1.02))
    axis.set_xticks(sizes, [f"{size:,}".replace(",", " ") for size in sizes])
    axis.grid(color="#e3eaf1")
    axis.legend(loc="lower right", fontsize="small")


def draw_confusion(axis, matrix):
    axis.imshow(matrix, cmap="Blues", aspect="auto", vmin=0)
    axis.set(title="Матрица ошибок", xlabel="Прогноз", ylabel="Факт")
    labels = ["Без дождя", "Дождь"]
    axis.set_xticks([0, 1], labels)
    axis.set_yticks([0, 1], labels)
    peak = max(map(max, matrix))
    for row, values in enumerate(matrix):
        for column, value in enumerate(values):
            number = f"{value:,}".replace(",", " ")
            axis.text(column, row, number, ha="center", va="center", color="white" if value > peak / 2 else "#20374f")


def render_model_charts(evaluation, learning):
    charts = {
        "roc": (draw_roc, evaluation["roc"]),
        "precision-recall": (draw_precision_recall, evaluation["precision_recall"]),
        "confusion-matrix": (draw_confusion, evaluation["confusion_matrix"]),
    }
    if learning["sizes"]:
        charts["learning-curve"] = (draw_learning, learning)

    images = {}
    for chart_id, (draw, series) in charts.items():
        figure = Figure(figsize=(6, 3.75), layout="constrained", facecolor="white")
        FigureCanvasAgg(figure)
        draw(figure.subplots(), series)
        with BytesIO() as output:
            figure.savefig(output, format="png", dpi=150)
            images[chart_id] = output.getvalue()
        figure.clear()
    return images


def main():
    from business.model_registry import DEFAULT_ARTIFACTS_DIR, list_model_releases, load_versioned_model
    from data.datasets import load_training_data
    from data.model_artifacts import FileModelStore

    x_train, x_test, y_train, y_test = load_training_data()
    store = FileModelStore(DEFAULT_ARTIFACTS_DIR)
    for release in list_model_releases()["versions"]:
        version = release["model_version"]
        for entry in release["models"]:
            model_id = entry["model_id"]
            model, metadata = load_versioned_model(version, model_id=model_id)
            features = metadata["feature_names"]
            train, test = x_train[features], x_test[features]
            probabilities = model.predict_proba(test)
            predictions = model.classes_[probabilities.argmax(axis=1)]
            evaluation = evaluation_diagnostics(y_test, predictions, probabilities[:, 1])
            learning = learning_diagnostics(model, train, y_train, test, y_test)
            store.write_model_charts(version, model_id, render_model_charts(evaluation, learning))
            print(f"{version} {model_id}: ROC-AUC {evaluation['roc']['auc']:.4f}", flush=True)


if __name__ == "__main__":
    main()
