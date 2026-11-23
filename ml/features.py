import pandas as pd

KEY_WEATHER_FIELDS = (
    "Humidity3pm",
    "Pressure3pm",
    "Location",
    "WindGustSpeed",
    "WindDir3pm",
    "Rainfall",
    "MinTemp",
)


def select_preprocess_params(params, fields):
    return {
        name: {field: value for field, value in values.items() if field in fields}
        for name, values in params.items()
    }


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
    data = {name: weather.get(name) for name in (*params["mean"], *params["modes"])}
    features = pd.DataFrame([data])
    if "RainToday" in data:
        rain_today = data["RainToday"]
        if rain_today is not None:
            features["RainToday"] = "Yes" if rain_today.strip().lower() == "yes" else "No"
        features["RainToday"] = encode_rain_today(features["RainToday"])
    features = fill_missing(features, params["medians"], params["modes"])
    features = encode_categories(features, params["modes"])
    features = scale_numeric(features, params["mean"], params["std"])
    return features.reindex(columns=feature_names, fill_value=0).astype(float)
