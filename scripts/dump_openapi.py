"""Dump the canonical OpenAPI document for the standup-gen API.

Used by the 0.6.0 OpenAPI snapshot gate. Imports the FastAPI app, calls
``app.openapi()``, normalises the result (sorted keys, stable whitespace,
deterministic ordering of ``paths`` entries), and writes the document
to either stdout or a target file.

The output is the **single source of truth** for the project's public
API surface. The committed ``docs/openapi.json`` is a baseline; a CI
workflow (``.forgejo/workflows/openapi-snapshot.yml``) regenerates the
dump and fails the build if it differs from the baseline.

Why a separate script rather than calling ``app.openapi()`` in pytest:
we want the dump to be runnable in CI without the full test harness
(no DB, no coverage, no plugins), and we want a stable command name
(``uv run python scripts/dump_openapi.py > docs/openapi.json``) that
the snapshot workflow can call.

Usage:
    uv run python scripts/dump_openapi.py                # to stdout
    uv run python scripts/dump_openapi.py --output FILE  # to FILE

Exit code 0 on success, non-zero on any error (import failure, app
not configured, write error). Errors are written to stderr and are
human-readable; this script is meant to be readable when it fails.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# The script must run before ``backend.api`` is imported, because
# ``backend.config`` reads env vars at module-load time. Match the test
# setup in ``tests/conftest.py``: SQLite-backed ephemeral DB, all
# provider keys blank, ingest scheduler disabled. AUTH_MODE defaults
# to "off" (the only mode that doesn't try to bootstrap an admin on
# lifespan startup), but we set it explicitly to make the intent
# clear and to keep the dump free of any "we tried to talk to a DB"
# side effects.
_DEFAULT_DB = Path("/tmp/standup_openapi_dump.db")
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = f"sqlite:///{_DEFAULT_DB}"
os.environ.setdefault("AUTH_MODE", "off")
os.environ.setdefault("INGEST_INTERVAL", "0")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("DEEPSEEK_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")

# Lazy import: do this AFTER env setup, not at module top, so the
# import-order dance above is the first thing that runs.
from backend.api import app  # noqa: E402


def _normalise(obj: Any) -> Any:
    """Recursively normalise the OpenAPI document for stable diffs.

    OpenAPI documents are JSON objects; we want byte-stable output so a
    diff between two runs is the actual semantic change rather than
    Python's dictionary ordering, FastAPI's internal dict ordering, or
    Pydantic's representation choices.

    The transform is intentionally minimal:
      - ``Mapping`` (incl. ``dict``) → sorted-key JSON-ready dict.
      - ``list`` / ``tuple`` → list, recursively normalised.
      - everything else → unchanged.

    We do **not** reorder ``paths`` entries by HTTP method or URL: the
    OpenAPI spec puts methods inside each path entry, not as siblings,
    so the only ordering that matters at the top level is the URL
    ordering. FastAPI's ``app.openapi()`` returns paths in the order
    they were registered; we sort by URL to make the diff readable
    (a new route shows up as an inserted block in alphabetical
    position, not appended at the end).
    """
    if isinstance(obj, Mapping):
        return {k: _normalise(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [_normalise(item) for item in obj]
    return obj


def _sort_paths(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Sort the top-level ``paths`` object by URL.

    Everything else in the document is already key-sorted by
    ``_normalise``. ``paths`` is a dict whose keys are URL templates
    (``/repos``, ``/repos/{repo_id}/commits``); we want them in
    alphabetical order so a new route is inserted in the right place
    rather than appended.
    """
    if "paths" not in document:
        return document
    result = dict(document)
    result["paths"] = {url: document["paths"][url] for url in sorted(document["paths"])}
    return result


def _strip_volatile_fields(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Remove fields that change between runs without representing a
    real API change.

    The 0.6.0 plan called this out as a sub-item of the
    "diff-friendly schema config" work: the OpenAPI generator should
    not include any per-process state (PID, request IDs, timestamps)
    in the document. FastAPI doesn't do this by default, but we add
    the strip as a defence-in-depth so a future regression in
    FastAPI's generator doesn't silently break the snapshot gate.
    """
    result = dict(document)
    for field in ("servers", "info"):
        info = result.get(field)
        if isinstance(info, Mapping):
            cleaned = {k: v for k, v in info.items() if k not in {"x-build-id", "x-process-id"}}
            result[field] = cleaned
    return result


def dump() -> str:
    """Return the normalised OpenAPI document as a JSON string."""
    raw = app.openapi()
    normalised = _normalise(raw)
    sorted_paths = _sort_paths(normalised)
    stripped = _strip_volatile_fields(sorted_paths)
    return json.dumps(stripped, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dump the canonical OpenAPI document for standup-gen."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write the dump to this file. Default: stdout.",
    )
    args = parser.parse_args(argv)

    try:
        text = dump()
    except Exception as exc:  # noqa: BLE001 — we want to surface the raw error
        print(f"dump_openapi: failed to generate the OpenAPI document: {exc}", file=sys.stderr)
        return 1

    if args.output is None:
        sys.stdout.write(text)
    else:
        try:
            args.output.write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"dump_openapi: failed to write {args.output}: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
