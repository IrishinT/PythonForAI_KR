from datetime import datetime, timezone
from pathlib import Path

from data.model_artifacts import DEFAULT_ARTIFACTS_DIR, FileModelStore


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
    feature_names = list(columns)
    metadata = {
        "model_name": model_name,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_count": len(feature_names),
        "feature_names": feature_names,
        "best_params": model.get_params(),
        "metrics": {key: float(value) for key, value in metrics.items()},
        "preprocess_params": preprocess_params,
    }

    while True:
        version = f"{major}.{minor}.{patch}"
        stored_metadata = store.write_version(version, model, {**metadata, "version": version})
        if stored_metadata is not None:
            store.write_latest_version(version)
            return stored_metadata
        patch += 1


def load_versioned_model(
    version: str | None = None,
    artifacts_dir: str | Path = DEFAULT_ARTIFACTS_DIR,
):
    """Загружает указанную версию или последнюю опубликованную."""
    store = FileModelStore(artifacts_dir)
    selected_version = store.read_latest_version() if version is None else version
    return store.read_version(selected_version.removeprefix("v"))
