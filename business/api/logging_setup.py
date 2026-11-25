import logging
import os
from contextlib import contextmanager
from copy import copy
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import gmtime, perf_counter

from uvicorn.logging import AccessFormatter, DefaultFormatter

PROJECT_DIR = Path(__file__).resolve().parents[2]
logger = logging.getLogger("weather_api")
request_logger = logging.getLogger("weather_api.http")


class ConsoleFormatter(DefaultFormatter):
    def __init__(self):
        super().__init__("%(levelprefix)s %(message)s")
        self.access = AccessFormatter('%(levelprefix)s "%(request_line)s" %(status_code)s')

    def format(self, record):
        if access_args := getattr(record, "access_args", None):
            access_record = copy(record)
            access_record.msg = '%s "%s %s HTTP/%s" %d'
            access_record.args = access_args
            return self.access.format(access_record)
        if message := getattr(record, "console_message", None):
            record = copy(record)
            record.msg = message
            record.args = ()
        return super().format(record)


@contextmanager
def api_logging():
    previous_level, previous_propagate = logger.level, logger.propagate
    uvicorn_access = logging.getLogger("uvicorn.access")
    previous_access = uvicorn_access.disabled
    uvicorn_access.disabled = True
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    formatter.converter = gmtime
    console = logging.StreamHandler()
    console.setFormatter(ConsoleFormatter())
    logger.addHandler(console)
    handlers = [console]

    try:
        directory = PROJECT_DIR / (os.getenv("WEATHER_LOG_DIR") or "logs")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                directory / "backend.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
            )
        except OSError:
            logger.exception("file logging unavailable directory=%s", directory)
        else:
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            handlers.append(file_handler)
            console.addFilter(lambda record: not getattr(record, "file_only", False))
        yield
    finally:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        uvicorn_access.disabled = previous_access


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = perf_counter()
        status = 500

        async def record_status(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, record_status)
        except Exception:
            request_logger.exception("unhandled request error")
            raise
        finally:
            route = getattr(scope.get("route"), "path", "<unmatched>")
            state = scope.get("state", {})
            level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
            request_logger.log(
                level, "request method=%s route=%s status=%s duration_ms=%.1f model_version=%s model_id=%s",
                scope["method"], route, status, (perf_counter() - start) * 1000,
                state.get("model_version", "-"), state.get("model_id", "-"),
                extra={"access_args": ("", scope["method"], route, scope.get("http_version", "1.1"), status)},
            )
