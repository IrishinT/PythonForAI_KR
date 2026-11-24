import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from data.model_artifacts import DEFAULT_ARTIFACTS_DIR, FileModelStore

VERSION_PATTERN = r"^v?[0-9]+\.[0-9]+\.[0-9]+$"
MODEL_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


@dataclass(frozen=True)
class ModelCandidate:
    estimator: object
    name: str
    metrics: dict[str, float]
    charts: dict[str, bytes] | None = None


def _model_metadata(
    model,
    feature_names: list[str],
    model_name: str,
    metrics: dict,
    preprocess_params: dict | None,
) -> dict:
    return {
        "model_name": model_name,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_count": len(feature_names),
        "feature_names": feature_names,
        "best_params": model.get_params(),
        "metrics": {key: float(value) for key, value in metrics.items()},
        "preprocess_params": preprocess_params,
    }


def save_versioned_model(
    model,
    columns,
    model_name: str,
    metrics: dict,
    base_version: str = "1.0.0",
    artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
    preprocess_params: dict | None = None,
) -> dict:
    """Сохраняет модель и назначает её последней доступной версией."""
    store = FileModelStore(artifacts_dir)
    major, minor, patch = map(int, base_version.split("."))
    metadata = _model_metadata(model, list(columns), model_name, metrics, preprocess_params)

    while True:
        version = f"{major}.{minor}.{patch}"
        stored_metadata = store.write_version(version, model, {**metadata, "version": version})
        if stored_metadata is not None:
            store.write_latest_version(version)
            return stored_metadata
        patch += 1


def save_model_release(
    models: dict[str, ModelCandidate],
    columns,
    preprocess_params: dict,
    base_version: str = "1.1.0",
    artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
) -> str:
    """Публикует выпуск моделей и выбирает модель с наибольшим ROC-AUC."""
    if not models or any(not re.fullmatch(MODEL_ID_PATTERN, model_id) for model_id in models):
        raise ValueError("A release requires models with valid IDs")

    default_id = max(models, key=lambda model_id: models[model_id].metrics["ROC-AUC"])
    store = FileModelStore(artifacts_dir)
    major, minor, patch = map(int, base_version.split("."))
    feature_names = list(columns)
    metadata = {
        model_id: _model_metadata(
            candidate.estimator, feature_names, candidate.name, candidate.metrics, preprocess_params
        )
        for model_id, candidate in models.items()
    }

    while True:
        version = f"{major}.{minor}.{patch}"
        artifacts = {
            model_id: (
                candidate.estimator,
                {**metadata[model_id], "version": version, "model_id": model_id},
                candidate.charts,
            )
            for model_id, candidate in models.items()
        }
        if store.write_release(version, artifacts, default_id) is not None:
            store.write_latest_version(version)
            return version
        patch += 1


def _resolve_version(store: FileModelStore, version: str | None) -> str:
    selected_version = store.read_latest_version() if version is None else version
    if not re.fullmatch(VERSION_PATTERN, selected_version):
        raise ValueError(f"Invalid model version: {selected_version}")
    return selected_version.removeprefix("v")


def list_version_models(
    version: str | None = None,
    artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
) -> dict:
    store = FileModelStore(artifacts_dir)
    selected_version = _resolve_version(store, version)
    catalog = store.read_catalog(selected_version)
    return {
        "model_version": selected_version,
        "default_model_id": catalog["default_model_id"],
        "models": [
            {"model_id": model_id, "model_name": name} for model_id, name in catalog["models"].items()
        ],
    }


def list_model_releases(artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR) -> dict:
    store = FileModelStore(artifacts_dir)
    versions = sorted(
        (version for version in store.list_versions() if re.fullmatch(VERSION_PATTERN, version)),
        key=lambda version: tuple(map(int, version.split("."))),
        reverse=True,
    )
    return {
        "latest_version": _resolve_version(store, None),
        "versions": [list_version_models(version, artifacts_dir) for version in versions],
    }


def read_model_metrics(version: str, model_id: str | None = None) -> dict:
    store = FileModelStore(DEFAULT_ARTIFACTS_DIR)
    return store.read_model_metrics(_resolve_version(store, version), model_id)


def model_chart_path(version: str, model_id: str | None, chart_id: str) -> Path:
    store = FileModelStore(DEFAULT_ARTIFACTS_DIR)
    return store.model_chart_path(_resolve_version(store, version), model_id, chart_id)


def load_versioned_model(
    version: str | None = None,
    artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
    *,
    model_id: str | None = None,
):
    """Загружает выбранную модель или модель по умолчанию в выпуске."""
    store = FileModelStore(artifacts_dir)
    return store.read_version(_resolve_version(store, version), model_id)
