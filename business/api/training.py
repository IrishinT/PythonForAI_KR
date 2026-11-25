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

from dotenv import dotenv_values

from business.model_registry import VERSION_PATTERN, read_model_metrics

PROJECT_DIR = Path(__file__).resolve().parents[2]
MASTER_KEY_VARIABLE = "WEATHER_MASTER_KEY"
logger = logging.getLogger("uvicorn.error")


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

    def start(self) -> bool:
        if self.task is not None and not self.task.done():
            return False
        self.started = monotonic()
        self.state = {
            "status": "running", "stage": "preparing", "completed_models": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self.task = asyncio.create_task(self.run())
        return True

    def read_progress(self):
        if self.progress_file is None:
            return
        try:
            events = self.progress_file.read_bytes().splitlines()
        except FileNotFoundError:
            return
        for event in reversed(events):
            try:
                progress = json.loads(event)
            except ValueError:
                continue
            self.state.update(progress)
            break

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
                    OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
                )
                self.process = subprocess.Popen(
                    [
                        sys.executable, "-B", "-u", "-m", "ml.training.train_models",
                        "--result-file", str(result), "--progress-file", str(self.progress_file),
                    ],
                    cwd=PROJECT_DIR, env=env, stdin=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                code = await asyncio.to_thread(self.process.wait)
                self.read_progress()
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
        except Exception:
            logger.exception("Model training failed")
            self.state.update(status="failed")
        finally:
            self.process = None
            self.progress_file = None
            self.state.update(
                finished_at=datetime.now(timezone.utc).isoformat(),
                elapsed_seconds=int(monotonic() - self.started),
            )

    async def close(self):
        if self.task is None or self.task.done():
            return
        if self.process is None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            return
        try:
            self.process.kill()
        except ProcessLookupError:
            pass
        await self.task
