from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from business.model_registry import (
    MODEL_ID_PATTERN,
    VERSION_PATTERN,
    list_model_releases,
    list_version_models,
    model_chart_path,
    read_model_metrics,
)

from .schemas import WeatherInput

router = APIRouter()
ModelVersion = Annotated[str | None, Query(pattern=VERSION_PATTERN, examples=["1.1.0"])]
ModelId = Annotated[str | None, Query(pattern=MODEL_ID_PATTERN, examples=["random-forest"])]


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


@router.get("/models/versions")
def model_versions():
    return list_model_releases()


@router.get("/models/metrics", responses={404: {"description": "Model or version not found"}})
def model_metrics(request: Request, model_version: ModelVersion = None, model_id: ModelId = None):
    version = model_version or request.app.state.prediction_service.version
    try:
        return read_model_metrics(version, model_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"Model {model_id or 'default'} not found in version {version}") from exc


@router.get(
    "/models/metrics/{chart_id}",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {}}}, 404: {"description": "Chart not found"}},
)
def model_chart(chart_id: str, request: Request, model_version: ModelVersion = None, model_id: ModelId = None):
    version = model_version or request.app.state.prediction_service.version
    try:
        path = model_chart_path(version, model_id, chart_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Chart not found for the selected model") from exc
    return FileResponse(path, media_type="image/png")


@router.post("/predict", responses={404: {"description": "Model or version not found"}})
def predict(
    weather: WeatherInput,
    request: Request,
    model_version: ModelVersion = None,
    model_id: ModelId = None,
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
