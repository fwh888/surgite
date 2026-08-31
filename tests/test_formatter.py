from surgite.formatter import format_commit, format_log
from surgite.models import Commit


def _commit(**overrides) -> Commit:
    defaults = {
        "hash": "abcdef1234567890" + "0" * 24,
        "date": "2026-06-01",
        "author": "Alice",
        "message": "fix the thing",
    }
    defaults.update(overrides)
    return Commit(**defaults)


def test_format_commit_uses_short_hash_and_fields():
    line = format_commit(_commit())
    assert line == "[2026-06-01] fix the thing (Alice) <abcdef1>"


def test_format_log_joins_with_newlines():
    out = format_log([_commit(message="one"), _commit(message="two")])
    assert out == "[2026-06-01] one (Alice) <abcdef1>\n[2026-06-01] two (Alice) <abcdef1>"


def test_format_log_empty_is_empty_string():
    assert format_log([]) == ""
