import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import sklearn

DEFAULT_ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"

def _resolve_version(artifacts_dir: Path, base_version: str) -> str:
    """Автоматически увеличивает patch-версию, если папка уже существует."""
    major, minor, patch = map(int, base_version.split("."))
    while (artifacts_dir / f"v{major}.{minor}.{patch}").exists():
        patch += 1
    return f"{major}.{minor}.{patch}"


def save_versioned_model(
    model,
    columns,
    model_name: str,
    metrics: dict,
    base_version: str = "1.0.0",
    artifacts_dir: str = str(DEFAULT_ARTIFACTS_DIR),
    preprocess_params: dict = None,
) -> dict:
    root_dir = Path(artifacts_dir)
    root_dir.mkdir(exist_ok=True)

    version = _resolve_version(root_dir, base_version)
    version_dir = root_dir / f"v{version}"
    version_dir.mkdir(parents=True, exist_ok=True)

    model_path = version_dir / "model.joblib"
    metadata_path = version_dir / "metadata.json"

    # Сохраняем модель
    joblib.dump(model, model_path, compress=3)

    # Сохраняем метаданные, список колонок и версии библиотек в JSON
    metadata = {
        "model_name": model_name,
        "version": version,
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_file": model_path.name,
        "feature_count": len(columns),
        "feature_names": list(columns),
        "best_params": model.get_params(),
        "metrics": {k: float(v) for k, v in metrics.items()},
        "preprocess_params": preprocess_params,
        "environment": {
            "sklearn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    # Обновляем указатель на последнюю версию
    (root_dir / "latest.json").write_text(
        json.dumps({"latest_version": version}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return metadata


def load_versioned_model(version: str = None, artifacts_dir: str = str(DEFAULT_ARTIFACTS_DIR)):
    """Загружает последнюю (если version=None) или конкретную версию модели."""
    root_dir = Path(artifacts_dir)
    if version is None:
        latest = json.loads((root_dir / "latest.json").read_text(encoding="utf-8"))
        version = latest["latest_version"]

    v_dir = root_dir / (version if version.startswith("v") else f"v{version}")
    metadata = json.loads((v_dir / "metadata.json").read_text(encoding="utf-8"))
    model = joblib.load(v_dir / "model.joblib")
    return model, metadata