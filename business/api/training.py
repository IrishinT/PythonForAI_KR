import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from uuid import uuid4

from dotenv import dotenv_values

from business.model_registry import VERSION_PATTERN, read_model_metrics

PROJECT_DIR = Path(__file__).resolve().parents[2]
MASTER_KEY_VARIABLE = "WEATHER_MASTER_KEY"
logger = logging.getLogger("weather_api.training")


def configured_master_key() -> str:
    key = os.getenv(MASTER_KEY_VARIABLE)
    if key is None:
        key = dotenv_values(PROJECT_DIR / ".env").get(MASTER_KEY_VARIABLE)
    return key or ""


class TrainingJob:
    def __init__(self):
        self.state = {"status": "idle"}
        self.task = None
        self.process = None
        self.progress_file = None
        self.started = None
        self.job_id = None
        self.progress_cursor = 0

    def start(self) -> bool:
        if self.task is not None and not self.task.done():
            return False
        self.job_id = uuid4().hex
        self.progress_cursor = 0
        self.started = monotonic()
        self.state = {
            "status": "running", "stage": "preparing", "completed_models": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("training started job_id=%s", self.job_id, extra={"console_message": "Training started"})
        self.task = asyncio.create_task(self.run())
        return True

    def read_progress(self):
        if self.progress_file is None:
            return
        try:
            events = self.progress_file.read_bytes().split(b"\n")[:-1]
        except FileNotFoundError:
            return
        except OSError:
            logger.debug("training progress cannot be read job_id=%s", self.job_id, exc_info=True)
            return
        for event in events[self.progress_cursor:]:
            try:
                progress = json.loads(event)
            except ValueError:
                continue
            if not isinstance(progress, dict):
                continue
            self.state.update(progress)
            stage = progress.get("stage")
            model = progress.get("model_name")
            completed, total = progress.get("completed_models"), progress.get("total_models")
            summary = f"Training {stage}"
            if model:
                summary += f" ({model})"
            if total:
                summary += f", {completed}/{total} ready"
            logger.info(
                "training progress job_id=%s stage=%s model=%s completed=%s total=%s",
                self.job_id, stage, model, completed, total, extra={"console_message": summary},
            )
        self.progress_cursor = len(events)

    def wait_for_process(self, process):
        with process.stdout as output:
            for line in output:
                if message := line.rstrip():
                    logger.info("training output job_id=%s %s", self.job_id, message, extra={"file_only": True})
        return process.wait()

    def snapshot(self) -> dict:
        if self.state["status"] != "running":
            return dict(self.state)
        self.read_progress()
        return {**self.state, "elapsed_seconds": int(monotonic() - self.started)}

    async def run(self):
        try:
            with TemporaryDirectory() as directory:
                result = Path(directory) / "release.txt"
                self.progress_file = Path(directory) / "progress.jsonl"
                env = dict(os.environ)
                env.pop(MASTER_KEY_VARIABLE, None)
                env.update(
                    MPLBACKEND="Agg", MPLCONFIGDIR=directory, OMP_NUM_THREADS="1",
                    OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONIOENCODING="utf-8",
                )
                self.process = subprocess.Popen(
                    [
                        sys.executable, "-B", "-u", "-m", "ml.training.train_models",
                        "--result-file", str(result), "--progress-file", str(self.progress_file),
                    ],
                    cwd=PROJECT_DIR, env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                worker = asyncio.create_task(asyncio.to_thread(self.wait_for_process, self.process))
                while not worker.done():
                    await asyncio.wait({worker}, timeout=0.5)
                    self.read_progress()
                code = worker.result()
                if code != 0:
                    raise RuntimeError(f"Training exited with code {code}")
                version = result.read_text(encoding="utf-8").strip()
                if not re.fullmatch(VERSION_PATTERN, version):
                    raise RuntimeError("Training returned an invalid release version")
                best = read_model_metrics(version)
                self.state.update(
                    status="succeeded", model_version=version, best_model_name=best["model_name"],
                    best_roc_auc=best["metrics"]["ROC-AUC"],
                )
                logger.info(
                    "release published job_id=%s version=%s model=%s roc_auc=%.4f",
                    self.job_id, version, best["model_name"], best["metrics"]["ROC-AUC"],
                    extra={"console_message": f"Published model release {version}"},
                )
        except Exception:
            stage = self.state.get("stage")
            logger.exception(
                "training failed job_id=%s stage=%s", self.job_id, stage,
                extra={"console_message": f"Training failed at {stage}"},
            )
            self.state.update(status="failed")
        finally:
            self.process = None
            self.progress_file = None
            self.state.update(
                finished_at=datetime.now(timezone.utc).isoformat(),
                elapsed_seconds=int(monotonic() - self.started),
            )
            logger.info(
                "training finished job_id=%s status=%s elapsed_seconds=%s",
                self.job_id, self.state["status"], self.state["elapsed_seconds"],
                extra={"file_only": True},
            )

    async def close(self):
        if self.task is None or self.task.done():
            return
        if self.process is None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            return
        try:
            logger.info("stopping training worker job_id=%s", self.job_id)
            self.process.kill()
        except ProcessLookupError:
            pass
        await self.task
