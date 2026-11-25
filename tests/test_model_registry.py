import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sklearn.dummy import DummyClassifier

from business.model_registry import ModelCandidate, list_model_releases, load_versioned_model, save_model_release
from data.model_artifacts import FileModelStore


class ModelReleaseTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = Path(self.enterContext(tempfile.TemporaryDirectory()))
        estimator = DummyClassifier().fit([[0], [1]], [0, 1])
        self.candidates = {
            "first": ModelCandidate(estimator, "First", {"ROC-AUC": 0.8}),
            "best": ModelCandidate(estimator, "Best", {"ROC-AUC": 0.9}, {"roc": b"chart"}),
        }

    def publish(self):
        return save_model_release(self.candidates, ["feature"], {}, artifacts_dir=self.artifacts)

    def test_publishes_default_for_each_release_and_increments_version(self):
        self.assertEqual(self.publish(), "1.1.0")
        self.assertEqual(self.publish(), "1.1.1")
        catalog = list_model_releases(self.artifacts)
        self.assertEqual(catalog["latest_version"], "1.1.1")
        self.assertEqual([release["default_model_id"] for release in catalog["versions"]], ["best", "best"])
        _, metadata = load_versioned_model("1.1.0", self.artifacts, model_id="first")
        self.assertEqual(metadata["model_id"], "first")
        self.assertEqual(FileModelStore(self.artifacts).model_chart_path("1.1.0", None, "roc").read_bytes(), b"chart")

    def test_failed_write_leaves_previous_release_active(self):
        self.publish()
        original_write = FileModelStore._write_model

        def fail_second_model(store, directory, model, metadata):
            if metadata["model_id"] == "best":
                raise OSError("disk write failed")
            return original_write(store, directory, model, metadata)

        with patch.object(FileModelStore, "_write_model", fail_second_model):
            with self.assertRaisesRegex(OSError, "disk write failed"):
                self.publish()

        self.assertEqual({path.name for path in self.artifacts.iterdir()}, {"latest.json", "v1.1.0"})
        self.assertEqual(FileModelStore(self.artifacts).read_latest_version(), "1.1.0")
        self.assertEqual(self.publish(), "1.1.1")
