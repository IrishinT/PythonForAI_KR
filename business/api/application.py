import logging
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI

from business import model_registry
from business.prediction import PredictionService
from data.model_artifacts import LEGACY_MODEL_ID
from .logging_setup import RequestLoggingMiddleware, api_logging
from .routes import router
from .training import TrainingJob, configured_master_key

logger = logging.getLogger("weather_api.lifecycle")


def load_prediction_service(version: str | None = None, model_id: str | None = None) -> PredictionService:
    model, metadata = model_registry.load_versioned_model(version, model_id=model_id)
    preprocess_params = metadata.get("preprocess_params")
    if not preprocess_params:
        raise RuntimeError(
            f"Model v{metadata['version']} has no preprocessing parameters."
        )

    logger.info("model loaded version=%s model_id=%s", metadata["version"], metadata.get("model_id", LEGACY_MODEL_ID))
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
    with api_logging():
        try:
            app.state.load_prediction_service = lru_cache(maxsize=8)(load_prediction_service)
            version = model_registry.latest_model_version()
            app.state.load_prediction_service(version, None)
            app.state.master_key = configured_master_key()
            app.state.training = TrainingJob()
        except Exception:
            logger.exception("api startup failed")
            raise
        logger.info("api started version=%s training_enabled=%s", version, bool(app.state.master_key))
        try:
            yield
        finally:
            await app.state.training.close()
            logger.info("api stopped")


app = FastAPI(title="Weather Rain Prediction API", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(router)
