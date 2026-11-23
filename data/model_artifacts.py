import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import joblib
import sklearn

DEFAULT_ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
MODEL_FILENAME = "model.joblib"


class FileModelStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def write_version(self, version: str, model, metadata: dict) -> dict | None:
        self.root.mkdir(parents=True, exist_ok=True)
        directory = self.root / f"v{version}"
        try:
            directory.mkdir()
        except FileExistsError:
            return None

        model_path = directory / MODEL_FILENAME
        metadata_path = directory / "metadata.json"
        stored_metadata = {
            **metadata,
            "model_file": MODEL_FILENAME,
            "environment": {
                "sklearn": sklearn.__version__,
                "joblib": joblib.__version__,
            },
        }
        try:
            joblib.dump(model, model_path, compress=3)
            metadata_path.write_text(
                json.dumps(stored_metadata, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            model_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            directory.rmdir()
            raise
        return stored_metadata

    def write_latest_version(self, version: str) -> None:
        with NamedTemporaryFile(dir=self.root, delete=False) as temporary:
            path = Path(temporary.name)
        try:
            path.write_text(
                json.dumps({"latest_version": version}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            path.replace(self.root / "latest.json")
        finally:
            path.unlink(missing_ok=True)

    def read_latest_version(self) -> str:
        latest = json.loads((self.root / "latest.json").read_text(encoding="utf-8"))
        return latest["latest_version"]

    def read_version(self, version: str):
        directory = self.root / f"v{version}"
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        model = joblib.load(directory / MODEL_FILENAME)
        return model, metadata
