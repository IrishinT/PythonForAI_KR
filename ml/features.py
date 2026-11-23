import pandas as pd


def encode_rain_today(values):
    return values.map({"No": 0, "Yes": 1})


def fill_missing(features, medians, modes):
    return features.fillna({**medians, **modes})


def encode_categories(features, category_names, *, drop_first=False):
    return pd.get_dummies(
        features, columns=list(category_names), drop_first=drop_first, dtype=int
    )


def scale_numeric(features, mean, std):
    numeric = list(mean)
    scaled = features.copy()
    scaled[numeric] = (scaled[numeric] - pd.Series(mean)) / pd.Series(std)
    return scaled


def prepare_features(weather, feature_names, params):
    data = dict(weather)
    rain_today = data["RainToday"]
    if rain_today is not None:
        data["RainToday"] = "Yes" if rain_today.strip().lower() == "yes" else "No"
    features = pd.DataFrame([data])
    features["RainToday"] = encode_rain_today(features["RainToday"])
    features = fill_missing(features, params["medians"], params["modes"])
    features = encode_categories(features, params["modes"])
    features = scale_numeric(features, params["mean"], params["std"])
    return features.reindex(columns=feature_names, fill_value=0).astype(float)
