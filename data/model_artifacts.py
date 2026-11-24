import json
from errno import ENOTEMPTY
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import joblib
import sklearn

DEFAULT_ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
MODEL_FILENAME = "model.joblib"
LEGACY_MODEL_ID = "default"
CHART_IDS = ("roc", "precision-recall", "learning-curve", "confusion-matrix")


class FileModelStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def write_version(self, version: str, model, metadata: dict) -> dict | None:
        stored = self._write_version(version, {LEGACY_MODEL_ID: (model, metadata, None)})
        return None if stored is None else stored[LEGACY_MODEL_ID]

    def write_release(self, version: str, models: dict, default_model_id: str) -> dict | None:
        return self._write_version(version, models, default_model_id)

    def _write_version(self, version: str, models: dict, default_model_id: str | None = None):
        self.root.mkdir(parents=True, exist_ok=True)
        directory = self.root / f"v{version}"
        if directory.exists():
            return None

        with TemporaryDirectory(dir=self.root) as temporary:
            staged = Path(temporary) / "version"
            staged.mkdir()
            stored = {}
            for model_id, (model, metadata, charts) in models.items():
                model_dir = staged if default_model_id is None else staged / "models" / model_id
                model_dir.mkdir(parents=True, exist_ok=True)
                stored[model_id] = self._write_model(model_dir, model, metadata)
                if charts:
                    self._write_charts(model_dir, charts)
            if default_model_id is not None:
                self._write_json(staged / "release.json", {
                    "default_model_id": default_model_id,
                    "models": {model_id: metadata["model_name"] for model_id, metadata in stored.items()},
                })

            try:
                staged.rename(directory)
            except FileExistsError:
                return None
            except OSError as exc:
                if exc.errno == ENOTEMPTY and directory.exists():
                    return None
                raise
            return stored

    def _write_model(self, directory: Path, model, metadata: dict) -> dict:
        stored_metadata = {
            **metadata,
            "model_file": MODEL_FILENAME,
            "environment": {
                "sklearn": sklearn.__version__,
                "joblib": joblib.__version__,
            },
        }
        joblib.dump(model, directory / MODEL_FILENAME, compress=3)
        self._write_json(directory / "metadata.json", stored_metadata)
        return stored_metadata

    @staticmethod
    def _write_json(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_latest_version(self, version: str) -> None:
        with NamedTemporaryFile(dir=self.root, delete=False) as temporary:
            path = Path(temporary.name)
        try:
            self._write_json(path, {"latest_version": version})
            path.replace(self.root / "latest.json")
        finally:
            path.unlink(missing_ok=True)

    def read_latest_version(self) -> str:
        latest = self._read_json(self.root / "latest.json")
        return latest["latest_version"]

    def list_versions(self) -> list[str]:
        return [
            directory.name[1:] for directory in self.root.glob("v*")
            if (directory / "release.json").is_file() or (directory / "metadata.json").is_file()
        ]

    def read_catalog(self, version: str) -> dict:
        directory = self.root / f"v{version}"
        try:
            return self._read_json(directory / "release.json")
        except FileNotFoundError:
            metadata = self._read_json(directory / "metadata.json")
            return {
                "default_model_id": LEGACY_MODEL_ID,
                "models": {LEGACY_MODEL_ID: metadata["model_name"]},
            }

    def _model_directory(self, version: str, model_id: str | None) -> tuple[Path, str]:
        directory = self.root / f"v{version}"
        try:
            release = self._read_json(directory / "release.json")
        except FileNotFoundError:
            if model_id is not None and model_id != LEGACY_MODEL_ID:
                raise FileNotFoundError(f"Model {model_id} not found in version {version}") from None
            return directory, LEGACY_MODEL_ID

        selected_id = release["default_model_id"] if model_id is None else model_id
        if selected_id not in release["models"]:
            raise FileNotFoundError(f"Model {selected_id} not found in version {version}")
        return directory / "models" / selected_id, selected_id

    def read_version(self, version: str, model_id: str | None = None):
        directory, _ = self._model_directory(version, model_id)
        metadata = self._read_json(directory / "metadata.json")
        model = joblib.load(directory / MODEL_FILENAME)
        return model, metadata

    def read_model_metrics(self, version: str, model_id: str | None) -> dict:
        directory, selected_id = self._model_directory(version, model_id)
        metadata = self._read_json(directory / "metadata.json")
        return {
            "model_version": version,
            "model_id": selected_id,
            "model_name": metadata["model_name"],
            "metrics": metadata["metrics"],
            "charts": [chart_id for chart_id in CHART_IDS if self._chart_path(directory, chart_id).is_file()],
        }

    @staticmethod
    def _chart_path(directory: Path, chart_id: str) -> Path:
        if chart_id not in CHART_IDS:
            raise FileNotFoundError(f"Unknown chart: {chart_id}")
        return directory / "charts" / f"{chart_id}.png"

    def _write_charts(self, directory: Path, charts: dict[str, bytes]) -> None:
        for chart_id, content in charts.items():
            target = self._chart_path(directory, chart_id)
            target.parent.mkdir(exist_ok=True)
            with NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
                path = Path(temporary.name)
            try:
                path.write_bytes(content)
                path.replace(target)
            finally:
                path.unlink(missing_ok=True)

    def write_model_charts(self, version: str, model_id: str, charts: dict[str, bytes]) -> None:
        directory, _ = self._model_directory(version, model_id)
        self._read_json(directory / "metadata.json")
        self._write_charts(directory, charts)

    def model_chart_path(self, version: str, model_id: str | None, chart_id: str) -> Path:
        directory, _ = self._model_directory(version, model_id)
        path = self._chart_path(directory, chart_id)
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
