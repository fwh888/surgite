"""Tests for backend.logging_config: format selection and JSON shape."""

import json
import logging
import re

from backend.logging_config import _JsonFormatter, configure_logging


def test_json_formatter_emits_required_fields():
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    out = json.loads(_JsonFormatter().format(record))
    assert out["level"] == "INFO"
    assert out["logger"] == "x"
    assert out["message"] == "hello world"
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", out["ts"])


def test_json_formatter_flattens_extras_and_skips_reserved():
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="m",
        args=None,
        exc_info=None,
    )
    record.repo = "demo"
    record.since = "2026-06-01"
    out = json.loads(_JsonFormatter().format(record))
    assert out["repo"] == "demo"
    assert out["since"] == "2026-06-01"
    # Reserved internal attrs are not leaked.
    assert "pathname" not in out
    assert "levelno" not in out


def test_configure_logging_uses_human_format_by_default(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    configure_logging()
    root = logging.getLogger()
    assert root.level == logging.WARNING
    fmt = root.handlers[0].formatter
    assert not isinstance(fmt, _JsonFormatter)


def test_configure_logging_uses_json_when_env_set(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    configure_logging()
    logging.getLogger("test.logger").info("ping", extra={"repo": "demo"})

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured, "expected at least one log line on stdout"
    payload = json.loads(captured[-1])
    assert payload["message"] == "ping"
    assert payload["repo"] == "demo"
    assert payload["logger"] == "test.logger"


def test_configure_logging_replaces_handlers(monkeypatch):
    """Re-running configure_logging must not stack duplicate handlers."""
    logging.getLogger().addHandler(logging.NullHandler())
    configure_logging()
    configure_logging()
    handlers = logging.getLogger().handlers
    # Exactly one, and it's a fresh StreamHandler (not the NullHandler we started with).
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.StreamHandler)
    assert not isinstance(handlers[0], logging.NullHandler)
