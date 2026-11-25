from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader

from business.model_registry import (
    MODEL_ID_PATTERN,
    VERSION_PATTERN,
    latest_model_version,
    list_model_releases,
    list_version_models,
    model_chart_path,
    read_model_metrics,
)

from .schemas import WeatherInput

router = APIRouter()
ModelVersion = Annotated[str | None, Query(pattern=VERSION_PATTERN, examples=["1.1.0"])]
ModelId = Annotated[str | None, Query(pattern=MODEL_ID_PATTERN, examples=["random-forest"])]
master_key_header = APIKeyHeader(name="X-Master-Key", auto_error=False)


def require_master_key(request: Request, supplied: Annotated[str | None, Security(master_key_header)]):
    configured = request.app.state.master_key
    if not configured:
        raise HTTPException(503, "Training is not configured")
    if supplied is None or not compare_digest(supplied.encode("latin-1"), configured.encode("utf-8")):
        raise HTTPException(401, "Invalid master key")


@router.post("/models/training", status_code=202, dependencies=[Depends(require_master_key)])
async def start_training(request: Request):
    training = request.app.state.training
    if not training.start():
        raise HTTPException(409, "Training is already running")
    return training.snapshot()


@router.get("/models/training", dependencies=[Depends(require_master_key)])
async def training_status(request: Request):
    return request.app.state.training.snapshot()


@router.get("/health")
def health(request: Request):
    service = request.app.state.load_prediction_service(latest_model_version(), None)
    return {
        "status": "ok",
        "model": service.model_name,
        "model_id": service.model_id,
        "version": service.version,
        "preprocess_loaded": True,
    }


@router.get("/models", responses={404: {"description": "Model version not found"}})
def models(model_version: ModelVersion = None):
    version = model_version or latest_model_version()
    try:
        return list_version_models(version)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"Model version {version} not found") from exc


@router.get("/models/versions")
def model_versions():
    return list_model_releases()


@router.get("/models/metrics", responses={404: {"description": "Model or version not found"}})
def model_metrics(model_version: ModelVersion = None, model_id: ModelId = None):
    version = model_version or latest_model_version()
    try:
        return read_model_metrics(version, model_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"Model {model_id or 'default'} not found in version {version}") from exc


@router.get(
    "/models/metrics/{chart_id}",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {}}}, 404: {"description": "Chart not found"}},
)
def model_chart(chart_id: str, model_version: ModelVersion = None, model_id: ModelId = None):
    version = model_version or latest_model_version()
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
    version = (model_version or latest_model_version()).removeprefix("v")
    try:
        service = request.app.state.load_prediction_service(version, model_id)
    except FileNotFoundError as exc:
        detail = f"Model version {version} not found"
        if model_id is not None:
            detail = f"Model {model_id} not found in version {version}"
        raise HTTPException(404, detail) from exc

    prediction = service.predict(weather.model_dump())
    request.state.model_version = prediction.model_version
    request.state.model_id = service.model_id
    return {
        "rain_tomorrow": prediction.rain_tomorrow,
        "probability": round(prediction.probability, 4),
        "model_version": prediction.model_version,
        "model_id": service.model_id,
    }
