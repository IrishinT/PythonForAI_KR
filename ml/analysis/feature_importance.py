from argparse import ArgumentParser

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from threadpoolctl import threadpool_limits

from business.api.schemas import WeatherInput
from business.model_registry import load_versioned_model
from data.datasets import load_preprocess_params, load_raw_weather, load_training_data
from ml.features import encode_rain_today, prepare_features, select_preprocess_params

RANDOM_STATE = 42
MAX_AUC_LOSS = 0.01
MAX_AP_LOSS = 0.02


def load_examples():
    params = load_preprocess_params()
    weather = load_raw_weather().dropna(subset=["RainTomorrow"]).sort_values("Date")
    # Берём те же поля, что использует API.
    dates = pd.to_datetime(weather["Date"])
    weather["Month"] = dates.dt.month
    weather["RainToday"] = encode_rain_today(weather["RainToday"])
    for name in params["modes"]:
        weather[name] = weather[name].astype("category")

    features = weather[[*params["mean"], *params["modes"]]]
    target = weather["RainTomorrow"].eq("Yes")

    # Более поздние даты оставляем на проверку.
    days = dates.unique()
    validation_start = days[len(days) * 3 // 5]
    test_start = days[len(days) * 4 // 5]
    train = dates < validation_start
    validation = (dates >= validation_start) & (dates < test_start)
    test = dates >= test_start
    return features, target, train, validation, test


def fit_model(features, target):
    model = HistGradientBoostingClassifier(
        categorical_features="from_dtype", random_state=RANDOM_STATE
    )
    return model.fit(features, target)


def evaluate(model, features, target):
    probability = model.predict_proba(features)[:, 1]
    return {
        "ROC-AUC": roc_auc_score(target, probability),
        "Average precision": average_precision_score(target, probability),
        "F1": f1_score(target, probability >= 0.5),
    }


def show_scores(title, full, short):
    print(f"\n{title}")
    scores = pd.DataFrame([full, short], index=["Все поля", "Короткий набор"])
    print(scores.to_string(float_format="{:.4f}".format))


def check_api(selected_fields):
    model, metadata = load_versioned_model()
    _, X_test, _, y_test = load_training_data()
    params = metadata.get("preprocess_params")
    columns = metadata["feature_names"]
    model_fields = {column.partition("_")[0] for column in columns}
    expected_params = select_preprocess_params(load_preprocess_params(), model_fields)
    if params != expected_params or not set(columns).issubset(X_test.columns):
        print("\nПроверка API пропущена: артефакт и подготовленная выборка различаются.")
        return

    # Подставляем те же значения, что API подставляет при пропуске поля.
    X_test = X_test[columns]
    defaults = prepare_features(WeatherInput().model_dump(), columns, params).iloc[0]
    short_input = X_test.copy()
    for column in columns:
        if column.partition("_")[0] not in selected_fields:
            short_input[column] = defaults[column]

    show_scores(
        f"Модель API v{metadata['version']} на её тестовой выборке",
        evaluate(model, X_test, y_test),
        evaluate(model, short_input, y_test),
    )


def main(spearman_only=False):
    features, target, train, validation, test = load_examples()
    X_val, y_val = features.loc[validation], target.loc[validation]

    # Спирмен показывает направление связи числового поля с дождём.
    numeric = X_val.select_dtypes(include="number")
    correlation = numeric.corrwith(y_val.astype(int), method="spearman")
    if spearman_only:
        print(correlation.sort_values(key=abs, ascending=False).round(4).to_string())
        return

    all_fields = features.columns.tolist()
    X_train, y_train = features.loc[train], target.loc[train]
    full_model = fit_model(X_train, y_train)

    # Перемешиваем по одному полю и смотрим, насколько падает ROC-AUC.
    importance = permutation_importance(
        full_model, X_val, y_val, scoring="roc_auc", n_repeats=5,
        random_state=RANDOM_STATE,
    )
    ranking = pd.DataFrame({"ROC-AUC drop": importance.importances_mean}, index=all_fields)
    ranking = ranking.sort_values("ROC-AUC drop", ascending=False)

    ranking["Spearman"] = correlation
    print("Важность полей на валидации")
    print(ranking.to_string(float_format="{:.4f}".format, na_rep="-"))

    # Добавляем поля по одному, пока потери не уложатся в допуск.
    baseline = evaluate(full_model, X_val, y_val)
    selected_fields = all_fields
    for count in range(1, len(all_fields)):
        fields = ranking.index[:count].tolist()
        model = fit_model(X_train[fields], y_train)
        scores = evaluate(model, X_val[fields], y_val)
        if (
            baseline["ROC-AUC"] - scores["ROC-AUC"] <= MAX_AUC_LOSS
            and baseline["Average precision"] - scores["Average precision"] <= MAX_AP_LOSS
        ):
            selected_fields = fields
            break

    print("\nВыбранные поля:", ", ".join(selected_fields))

    # После выбора обучаем обе модели на train и validation.
    X_fit, y_fit = features.loc[~test], target.loc[~test]
    X_test, y_test = features.loc[test], target.loc[test]
    full = fit_model(X_fit, y_fit)
    short = fit_model(X_fit[selected_fields], y_fit)
    show_scores(
        "Качество на тесте",
        evaluate(full, X_test, y_test),
        evaluate(short, X_test[selected_fields], y_test),
    )
    check_api(selected_fields)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--spearman", action="store_true", help="Только корреляция числовых полей")
    args = parser.parse_args()
    with threadpool_limits(limits=2):
        main(spearman_only=args.spearman)
