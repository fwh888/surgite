"""Tests for the CLI entry point (surgite/cli.py).

The summary paths are covered through their units (git, formatter,
summarizer); what needs a real `main()` invocation is argparse behaviour that
exits the process.
"""

import importlib.metadata

import pytest

from surgite.cli import main


def test_version_flag_prints_the_installed_version(capsys, monkeypatch):
    """`--version` reports the version from package metadata, not a literal —
    a hardcoded expectation here would break on every release."""
    monkeypatch.setattr("sys.argv", ["surgite", "--version"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    assert importlib.metadata.version("surgite") in capsys.readouterr().out


def test_version_flag_is_listed_in_help(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["surgite", "--help"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    assert "--version" in capsys.readouterr().out
