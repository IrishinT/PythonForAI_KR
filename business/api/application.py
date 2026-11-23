from contextlib import asynccontextmanager

from fastapi import FastAPI

from business import model_registry
from business.prediction import PredictionService
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    model, metadata = model_registry.load_versioned_model()
    preprocess_params = metadata.get("preprocess_params")
    if not preprocess_params:
        raise RuntimeError(
            f"Model v{metadata['version']} has no preprocessing parameters."
        )

    app.state.prediction_service = PredictionService(
        model,
        model_name=metadata["model_name"],
        version=metadata["version"],
        feature_names=metadata["feature_names"],
        preprocess_params=preprocess_params,
    )
    yield


app = FastAPI(title="Weather Rain Prediction API", lifespan=lifespan)
app.include_router(router)
