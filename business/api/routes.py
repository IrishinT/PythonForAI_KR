from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from business.model_registry import MODEL_ID_PATTERN, VERSION_PATTERN, list_version_models

from .schemas import WeatherInput

router = APIRouter()
ModelVersion = Annotated[str | None, Query(pattern=VERSION_PATTERN, examples=["1.1.0"])]


@router.get("/health")
def health(request: Request):
    service = request.app.state.prediction_service
    return {
        "status": "ok",
        "model": service.model_name,
        "model_id": service.model_id,
        "version": service.version,
        "preprocess_loaded": True,
    }


@router.get("/models", responses={404: {"description": "Model version not found"}})
def models(request: Request, model_version: ModelVersion = None):
    version = model_version or request.app.state.prediction_service.version
    try:
        return list_version_models(version)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"Model version {version} not found") from exc


@router.post("/predict", responses={404: {"description": "Model or version not found"}})
def predict(
    weather: WeatherInput,
    request: Request,
    model_version: ModelVersion = None,
    model_id: Annotated[
        str | None, Query(pattern=MODEL_ID_PATTERN, examples=["random-forest"])
    ] = None,
):
    service = request.app.state.prediction_service
    version = (model_version or service.version).removeprefix("v")
    if version != service.version or model_id not in (None, service.model_id):
        try:
            service = request.app.state.load_prediction_service(version, model_id)
        except FileNotFoundError as exc:
            detail = f"Model version {version} not found"
            if model_id is not None:
                detail = f"Model {model_id} not found in version {version}"
            raise HTTPException(404, detail) from exc

    prediction = service.predict(weather.model_dump())
    return {
        "rain_tomorrow": prediction.rain_tomorrow,
        "probability": round(prediction.probability, 4),
        "model_version": prediction.model_version,
        "model_id": service.model_id,
    }
