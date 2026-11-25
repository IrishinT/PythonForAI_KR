import unittest
from unittest.mock import Mock

import pandas as pd

from business.prediction import PredictionService


class PredictionTests(unittest.TestCase):
    def test_model_receives_features_in_training_column_order(self):
        feature_names = ["Location_Melbourne", "RainToday", "MinTemp", "Location_Sydney"]
        preprocess_params = {
            "mean": {"MinTemp": 10, "RainToday": 0.25},
            "std": {"MinTemp": 2, "RainToday": 0.5},
            "medians": {"MinTemp": 12, "RainToday": 0},
            "modes": {"Location": "Sydney"},
        }
        model = Mock()
        service = PredictionService(
            model, model_name="Legacy", version="1.0.0",
            feature_names=feature_names, preprocess_params=preprocess_params,
        )

        for weather, expected_features, probability, expected_rain in (
            ({"Location": "Melbourne", "RainToday": " yEs ", "MinTemp": 14}, [1, 1.5, 2, 0], 0.8, True),
            ({}, [0, -0.5, 1, 1], 0.5, True),
            ({"Location": "Unknown", "MinTemp": 10}, [0, -0.5, 0, 0], 0.2, False),
        ):
            with self.subTest(weather=weather):
                model.predict_proba.return_value = [[1 - probability, probability]]
                prediction = service.predict(weather)
                expected = pd.DataFrame([expected_features], columns=feature_names, dtype=float)
                pd.testing.assert_frame_equal(model.predict_proba.call_args.args[0], expected)
                self.assertEqual(prediction.probability, probability)
                self.assertEqual(prediction.rain_tomorrow, expected_rain)
                self.assertEqual(prediction.model_version, "1.0.0")
