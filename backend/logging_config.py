"""Centralised stdlib logging configuration.

Read at app startup so the container's stdout is greppable in a structured form
when `LOG_FORMAT=json` is set, and remains human-readable otherwise. Level is
controlled by `LOG_LEVEL` (default INFO).
"""

import json
import logging
import os
import sys


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per record. Extra fields on the LogRecord are
    flattened to top-level keys, which is what Loki / vector / fluentbit
    pipelines expect."""

    # Standard LogRecord attributes we don't want to dump on every line.
    _RESERVED = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Install the root handler. Idempotent: re-runs (e.g. by uvicorn's
    reload) replace the handler rather than stacking duplicates."""
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    fmt = os.environ.get("LOG_FORMAT", "").lower() == "json"
    handler = logging.StreamHandler(stream=sys.stdout)
    if fmt:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
