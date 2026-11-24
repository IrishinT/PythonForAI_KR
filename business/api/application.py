from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI

from business import model_registry
from business.prediction import PredictionService
from data.model_artifacts import LEGACY_MODEL_ID
from .routes import router


def load_prediction_service(version: str | None = None, model_id: str | None = None) -> PredictionService:
    model, metadata = model_registry.load_versioned_model(version, model_id=model_id)
    preprocess_params = metadata.get("preprocess_params")
    if not preprocess_params:
        raise RuntimeError(
            f"Model v{metadata['version']} has no preprocessing parameters."
        )

    return PredictionService(
        model,
        model_name=metadata["model_name"],
        version=metadata["version"],
        feature_names=metadata["feature_names"],
        preprocess_params=preprocess_params,
        model_id=metadata.get("model_id", LEGACY_MODEL_ID),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.prediction_service = load_prediction_service()
    app.state.load_prediction_service = lru_cache(maxsize=8)(load_prediction_service)
    yield


app = FastAPI(title="Weather Rain Prediction API", lifespan=lifespan)
app.include_router(router)
