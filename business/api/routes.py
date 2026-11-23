from fastapi import APIRouter, Request

from .schemas import WeatherInput

router = APIRouter()


@router.get("/health")
def health(request: Request):
    service = request.app.state.prediction_service
    return {
        "status": "ok",
        "model": service.model_name,
        "version": service.version,
        "preprocess_loaded": True,
    }


@router.post("/predict")
def predict(weather: WeatherInput, request: Request):
    prediction = request.app.state.prediction_service.predict(weather.model_dump())
    return {
        "rain_tomorrow": prediction.rain_tomorrow,
        "probability": round(prediction.probability, 4),
        "model_version": prediction.model_version,
    }
