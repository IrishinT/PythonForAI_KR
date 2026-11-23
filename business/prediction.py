from dataclasses import dataclass

from ml.features import prepare_features


@dataclass(frozen=True)
class RainPrediction:
    rain_tomorrow: bool
    probability: float
    model_version: str


class PredictionService:
    def __init__(self, model, *, model_name, version, feature_names, preprocess_params):
        self._model = model
        self.model_name = model_name
        self.version = version
        self._feature_names = feature_names
        self._preprocess_params = preprocess_params

    def predict(self, weather) -> RainPrediction:
        features = prepare_features(weather, self._feature_names, self._preprocess_params)
        probability = float(self._model.predict_proba(features)[0][1])
        return RainPrediction(
            rain_tomorrow=probability >= 0.5,
            probability=probability,
            model_version=self.version,
        )
