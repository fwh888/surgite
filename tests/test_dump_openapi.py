"""Tests for ``scripts/dump_openapi.py``.

The dump script is the foundation of the 0.6.0 OpenAPI snapshot
gate — if the dump is wrong, the snapshot is wrong, the CI gate is
wrong, and the entire stability promise is on a false foundation.
These tests pin the *shape* of the dump so a regression in the
generator or the normalisation layer is caught here, before it
silently corrupts the committed ``docs/openapi.json``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dump_openapi.py"


@pytest.fixture(scope="module")
def dump_output() -> str:
    """Run the dump script once and cache the result.

    The dump imports the FastAPI app, which itself imports the
    database engine. Running it once per module keeps the tests
    fast (the import is the expensive part) and exercises the same
    end-to-end path the CI workflow will use.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"dump_openapi.py exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout[:500]}\n"
        f"--- stderr ---\n{result.stderr[:1000]}"
    )
    return result.stdout


def test_dump_is_valid_json(dump_output: str) -> None:
    """The dump must be parseable as JSON.

    If the dump is not valid JSON, every downstream consumer breaks
    (the CI workflow, the OpenAPI viewer, the docs site). This is
    the cheapest possible test and catches the most common
    regression — adding a non-serialisable object to a route's
    response model.
    """
    parsed = json.loads(dump_output)
    assert isinstance(parsed, dict)


def test_dump_has_openapi_required_keys(dump_output: str) -> None:
    """An OpenAPI 3.x document must have ``openapi``, ``info``,
    and ``paths`` (or ``components``/``webhooks``).

    The exact version string is whatever FastAPI emits (3.1.0
    today); we don't pin it because FastAPI bumps it on its own
    schedule and we don't want a FastAPI minor release to break
    the snapshot for a non-substantive change.
    """
    parsed = json.loads(dump_output)
    assert "openapi" in parsed, "missing required 'openapi' key"
    assert "info" in parsed, "missing required 'info' key"
    assert "paths" in parsed, "missing required 'paths' key"
    # version string looks like '3.1.0'
    assert re.match(r"^\d+\.\d+\.\d+$", parsed["openapi"]), (
        f"unexpected openapi version: {parsed['openapi']!r}"
    )


def test_dump_documents_expected_routes(dump_output: str) -> None:
    """A representative sample of routes from the 0.5.0 release
    must be present.

    The full route list is 30+ entries; we don't pin the exact
    count (it'll grow), but we do pin the existence of the
    high-traffic ones so a deleted route shows up as a snapshot
    diff with a clear "this route disappeared" message.
    """
    parsed = json.loads(dump_output)
    paths = parsed["paths"]
    # Auth + summary + commits + repos are the user-visible core.
    for expected in (
        "/auth/login",
        "/auth/logout",
        "/auth/me",
        "/summary",
        "/summary/stream",
        "/commits",
        "/repos",
        "/providers",
        "/health",
        "/health/deep",
    ):
        assert expected in paths, f"expected route {expected!r} missing from OpenAPI dump"


def test_dump_operation_ids_are_unique_and_stable(dump_output: str) -> None:
    """Every operation has a non-empty, unique ``operationId``.

    OpenAPI's ``operationId`` is the contract SDK generators use
    to name methods (e.g. ``client.auth.login_auth_login_post()``
    for the default FastAPI format, or ``client.auth.login()`` for
    a custom generator). Two consequences:

    1. The ID must be non-empty — FastAPI always generates one,
       so a missing ID means a regression in the OpenAPI generator.
    2. The IDs must be unique across the whole document — a
       collision would break the OpenAPI spec and any client
       consuming it.

    This is a property the snapshot gate relies on implicitly
    (a duplicate-ID warning at ``app.openapi()`` time would change
    the dump), but pinning it here makes the failure mode obvious
    if it ever breaks.
    """
    import re
    from collections import Counter

    parsed = json.loads(dump_output)
    ids: list[str] = []
    for path, methods in parsed["paths"].items():
        for method, op in methods.items():
            if method == "parameters":
                continue
            op_id = op.get("operationId", "")
            assert op_id, f"route {method.upper()} {path} has empty operationId"
            ids.append(op_id)

    counts = Counter(ids)
    duplicates = {op_id: n for op_id, n in counts.items() if n > 1}
    assert not duplicates, f"duplicate operationIds: {duplicates}"

    # Every ID must be a valid Python identifier (no spaces,
    # no slashes, no special chars) — this is what SDK
    # generators expect.
    invalid = [op_id for op_id in ids if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", op_id)]
    assert not invalid, f"operationIds with invalid characters: {invalid}"


def test_dump_is_byte_stable(dump_output: str, tmp_path: Path) -> None:
    """Two consecutive runs of the dump script must produce
    byte-identical output.

    This is the property the snapshot gate relies on: a CI run
    that produces different bytes from the committed baseline
    is signalling a real change. If the dump is non-deterministic
    (e.g. it includes a timestamp or a PID), the gate will false-
    positive on every run.
    """
    first = tmp_path / "first.json"
    first.write_text(dump_output, encoding="utf-8")
    second = tmp_path / "second.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(second)],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    assert first.read_bytes() == second.read_bytes(), (
        "two consecutive dump runs produced different output — "
        "the dump is not byte-stable; this will cause the "
        "snapshot gate to false-positive on every run"
    )


def test_dump_paths_are_sorted(dump_output: str) -> None:
    """The top-level ``paths`` object must be URL-sorted.

    Sorted paths make the diff readable: a new route is inserted
    in alphabetical position rather than appended at the end. The
    script's ``_sort_paths`` helper enforces this; this test is
    the regression guard.
    """
    parsed = json.loads(dump_output)
    paths = list(parsed["paths"].keys())
    assert paths == sorted(paths), (
        f"paths are not URL-sorted; the diff will be unreadable.\n"
        f"first 5: {paths[:5]}\n"
        f"sorted:   {sorted(paths)[:5]}"
    )


def test_dump_output_flag_writes_to_file(dump_output: str, tmp_path: Path) -> None:
    """``--output FILE`` writes the dump to FILE; nothing is
    written to stdout.

    Used by the snapshot workflow's "regenerate and diff" step;
    if --output silently no-ops, the workflow will appear to
    pass while the snapshot drifts.
    """
    target = tmp_path / "snapshot.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"dump failed: {result.stderr}"
    assert target.exists(), "--output did not create the target file"
    assert target.read_text(encoding="utf-8") == dump_output, (
        "--output file content differs from stdout content"
    )
    assert result.stdout == "", (
        f"--output should not write to stdout, but got: {result.stdout[:200]!r}"
    )
