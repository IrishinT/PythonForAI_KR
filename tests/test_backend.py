import asyncio
import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from threading import Event
from unittest.mock import patch

from sklearn.dummy import DummyClassifier

from business.api import app
from business.model_registry import ModelCandidate, save_model_release, save_versioned_model
from data.model_artifacts import FileModelStore

KEY = "unit-test-master-key"
PNG = bytes.fromhex("89504e470d0a1a0a") + b"test chart"
FEATURES = ["MinTemp"]
PREPROCESSING = {"mean": {"MinTemp": 0}, "std": {"MinTemp": 1}, "medians": {"MinTemp": 0}, "modes": {}}


def classifier(labels):
    return DummyClassifier(strategy="prior").fit([[0]] * len(labels), labels)


class TrainingWorker:
    """Controllable stand-in for the training subprocess."""

    def __init__(self, command):
        self.progress = Path(command[command.index("--progress-file") + 1])
        self.result = Path(command[command.index("--result-file") + 1])
        self.stdout = StringIO()
        self.finished = Event()
        self.exit_code = 1

    def report(self, stage, completed, model_name=None):
        event = {"stage": stage, "model_name": model_name, "completed_models": completed, "total_models": 2}
        with self.progress.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")

    def finish(self, version=None):
        if version is not None:
            self.result.write_text(version, encoding="utf-8")
            self.exit_code = 0
        self.finished.set()

    def wait(self):
        if not self.finished.wait(timeout=10):
            raise TimeoutError("The test did not finish the training worker")
        return self.exit_code

    def kill(self):
        self.finish()


class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.artifacts = self.root / "artifacts"
        self.enterContext(patch.dict(os.environ, {"WEATHER_MASTER_KEY": KEY, "WEATHER_LOG_DIR": str(self.root / "logs")}))
        self.enterContext(patch("business.model_registry.FileModelStore", side_effect=lambda _: FileModelStore(self.artifacts)))

        save_versioned_model(
            classifier([0, 1]), FEATURES, "Legacy", {"ROC-AUC": 0.5},
            artifacts_dir=self.artifacts, preprocess_params=PREPROCESSING,
        )
        self.candidates = {
            "best": ModelCandidate(classifier([0, 1, 1, 1]), "Best", {"ROC-AUC": 0.85}, {"roc": PNG}),
            "other": ModelCandidate(classifier([0, 0, 0, 1]), "Other", {"ROC-AUC": 0.75}),
        }
        save_model_release(self.candidates, FEATURES, PREPROCESSING, artifacts_dir=self.artifacts)
        await self.enterAsyncContext(app.router.lifespan_context(app))

    async def request(self, method, target, *, body=None, key=None):
        path, _, query = target.partition("?")
        headers = [(b"content-type", b"application/json")]
        if key is not None:
            headers.append((b"x-master-key", key.encode("utf-8")))
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.5"},
            "http_version": "1.1", "method": method, "scheme": "http", "path": path, "root_path": "",
            "query_string": query.encode("ascii"), "headers": headers,
        }
        messages = []

        async def receive():
            return {"type": "http.request", "body": json.dumps(body).encode() if body is not None else b""}

        async def send(message):
            messages.append(message)

        await app(scope, receive, send)
        start = messages[0]
        raw = b"".join(message.get("body", b"") for message in messages)
        content_type = dict(start["headers"]).get(b"content-type")
        return start["status"], json.loads(raw) if content_type == b"application/json" else raw

    async def start_worker(self):
        launched = asyncio.get_running_loop().create_future()

        def launch(command, **kwargs):
            worker = TrainingWorker(command)
            launched.set_result(worker)
            return worker

        with patch("business.api.training.subprocess.Popen", side_effect=launch):
            code, state = await self.request("POST", "/models/training", key=KEY)
            self.assertEqual((code, state["status"], state["stage"], state["completed_models"]), (202, "running", "preparing", 0))
            return await asyncio.wait_for(launched, timeout=5)

    async def test_prediction_selects_latest_default_explicit_model_and_legacy(self):
        for query, expected in (
            ("", ("1.1.0", "best", 0.75)),
            ("?model_version=v1.1.0&model_id=other", ("1.1.0", "other", 0.25)),
            ("?model_version=1.0.0", ("1.0.0", "default", 0.5)),
        ):
            with self.subTest(query=query):
                code, result = await self.request("POST", "/predict" + query, body={})
                self.assertEqual(code, 200)
                self.assertEqual((result["model_version"], result["model_id"], result["probability"]), expected)
                self.assertEqual(result["rain_tomorrow"], expected[2] >= 0.5)

    async def test_metrics_chart_and_invalid_requests(self):
        self.assertEqual(await self.request("GET", "/models/metrics/roc"), (200, PNG))
        status, metrics = await self.request("GET", "/models/metrics?model_id=best")
        self.assertEqual(status, 200)
        self.assertEqual(metrics["charts"], ["roc"])
        self.assertEqual(metrics["metrics"]["ROC-AUC"], 0.85)
        self.assertEqual((await self.request("GET", "/models/metrics/roc?model_id=other"))[0], 404)
        self.assertEqual((await self.request("POST", "/predict?model_id=unknown", body={}))[0], 404)
        self.assertEqual((await self.request("POST", "/predict?model_version=invalid", body={}))[0], 422)

    async def test_prediction_rejects_weather_values_outside_valid_range(self):
        status, result = await self.request("POST", "/predict", body={"Humidity3pm": 101, "Rainfall": -1})
        self.assertEqual(status, 422)
        self.assertEqual({tuple(error["loc"]) for error in result["detail"]}, {("body", "Humidity3pm"), ("body", "Rainfall")})

    async def test_both_training_routes_require_configured_master_key(self):
        for method in ("GET", "POST"):
            for key in (None, "wrong"):
                with self.subTest(method=method, key=key):
                    self.assertEqual((await self.request(method, "/models/training", key=key))[0], 401)
        self.assertEqual(await self.request("GET", "/models/training", key=KEY), (200, {"status": "idle"}))
        app.state.master_key = ""
        for method in ("GET", "POST"):
            self.assertEqual((await self.request(method, "/models/training", key=KEY))[0], 503)

    async def test_training_reports_progress_and_activates_published_release(self):
        worker = await self.start_worker()
        self.assertEqual((await self.request("POST", "/models/training", key=KEY))[0], 409)

        worker.report("searching", 0, "Best")
        code, state = await self.request("GET", "/models/training", key=KEY)
        self.assertEqual((code, state["status"], state["stage"], state["model_name"]), (200, "running", "searching", "Best"))
        worker.report("evaluating", 1, "Other")
        _, state = await self.request("GET", "/models/training", key=KEY)
        self.assertEqual((state["stage"], state["model_name"], state["completed_models"], state["total_models"]), ("evaluating", "Other", 1, 2))
        _, prediction = await self.request("POST", "/predict", body={})
        self.assertEqual(prediction["model_version"], "1.1.0")

        worker.report("publishing", 2)
        version = save_model_release(self.candidates, FEATURES, PREPROCESSING, artifacts_dir=self.artifacts)
        worker.finish(version)
        await asyncio.wait_for(app.state.training.task, timeout=5)

        _, state = await self.request("GET", "/models/training", key=KEY)
        self.assertEqual((state["status"], state["model_version"], state["completed_models"]), ("succeeded", "1.1.1", 2))
        self.assertEqual((state["best_model_name"], state["best_roc_auc"]), ("Best", 0.85))
        self.assertEqual((await self.request("GET", "/health"))[1]["version"], version)
        self.assertEqual((await self.request("POST", "/predict", body={}))[1]["model_version"], version)

    async def test_failed_training_keeps_last_stage_and_allows_retry(self):
        worker = await self.start_worker()
        worker.report("fitting", 1, "Other")
        with worker.progress.open("a", encoding="utf-8") as stream:
            stream.write('{"stage":')
        worker.finish()
        await asyncio.wait_for(app.state.training.task, timeout=5)

        _, state = await self.request("GET", "/models/training", key=KEY)
        self.assertEqual((state["status"], state["stage"], state["model_name"], state["completed_models"]), ("failed", "fitting", "Other", 1))
        self.assertNotIn("model_version", state)
        self.assertEqual((await self.request("GET", "/health"))[1]["version"], "1.1.0")

        retry = await self.start_worker()
        retry.finish()
        await asyncio.wait_for(app.state.training.task, timeout=5)
