import pytest
import requests

from backend import summarizer
from backend.summarizer import (
    ProviderError,
    default_provider,
    generate_summary,
    generate_summary_per_repo,
    provider_status,
    resolve_provider,
    summarize_commits,
)


class FakeResp:
    def __init__(self, payload=None, raise_exc=None):
        self._payload = payload or {}
        self._raise_exc = raise_exc

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc


def _anthropic_payload(text):
    return {"content": [{"type": "text", "text": text}]}


def _openai_payload(text):
    return {"choices": [{"message": {"content": text}}]}


# --- provider resolution ---


def test_default_provider_is_anthropic(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert default_provider() == "anthropic"


def test_default_provider_respects_env_case_insensitively(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "GROQ")
    assert default_provider() == "groq"


def test_resolve_provider_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert resolve_provider(None).name == "anthropic"


def test_resolve_provider_explicit():
    assert resolve_provider("deepseek").name == "deepseek"


def test_resolve_provider_unknown_raises():
    with pytest.raises(ProviderError):
        resolve_provider("bogus")


# --- provider_status ---


def test_provider_status_all_unavailable_without_keys():
    # conftest clears every provider key.
    assert all(s["available"] is False for s in provider_status())


def test_provider_status_marks_configured_key_available(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    by_name = {s["name"]: s for s in provider_status()}
    assert by_name["groq"]["available"] is True
    assert by_name["deepseek"]["available"] is False


def test_provider_status_flags_the_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    by_name = {s["name"]: s for s in provider_status()}
    assert by_name["deepseek"]["default"] is True
    assert by_name["anthropic"]["default"] is False


# --- system prompt ---


def test_system_prompt_includes_identity(monkeypatch):
    monkeypatch.setenv("STANDUP_USER", "Nick")
    monkeypatch.setenv("STANDUP_ROLE", "developer")
    assert "Nick (developer)" in summarizer._build_system_prompt()


def test_system_prompt_without_identity_has_no_attribution(monkeypatch):
    monkeypatch.delenv("STANDUP_USER", raising=False)
    monkeypatch.delenv("STANDUP_ROLE", raising=False)
    assert "authored by" not in summarizer._build_system_prompt()


def test_system_prompt_instructs_theme_grouping():
    prompt = summarizer._build_system_prompt()
    assert "## " in prompt
    assert "group" in prompt.lower()


def test_system_prompt_with_settings_identity():
    prompt = summarizer._build_system_prompt(
        {"user_name": "Alice", "user_role": "backend engineer"}
    )
    assert "Alice (backend engineer)" in prompt


def test_system_prompt_with_settings_first_person():
    prompt = summarizer._build_system_prompt({"tone": "first-person"})
    assert "first person" in prompt.lower()


def test_system_prompt_with_settings_plain_format():
    prompt = summarizer._build_system_prompt({"output_format": "plain"})
    assert "plain text" in prompt.lower()
    assert "## " not in prompt


def test_system_prompt_with_settings_custom_group_count():
    prompt = summarizer._build_system_prompt({"group_count": "1-3"})
    assert "1-3" in prompt


def test_system_prompt_with_custom_instructions():
    prompt = summarizer._build_system_prompt({"custom_instructions": "Focus on bug fixes."})
    assert "Focus on bug fixes." in prompt


def test_system_prompt_settings_override_env(monkeypatch):
    monkeypatch.setenv("STANDUP_USER", "EnvUser")
    prompt = summarizer._build_system_prompt({"user_name": "SettingsUser"})
    assert "SettingsUser" in prompt
    assert "EnvUser" not in prompt


def test_system_prompt_settings_fallback_to_env(monkeypatch):
    monkeypatch.setenv("STANDUP_USER", "EnvUser")
    monkeypatch.setenv("STANDUP_ROLE", "dev")
    prompt = summarizer._build_system_prompt({})
    assert "EnvUser (dev)" in prompt


# --- generate_summary ---


def test_generate_summary_missing_key_raises():
    # conftest leaves ANTHROPIC_API_KEY empty.
    with pytest.raises(ProviderError):
        generate_summary("log", provider="anthropic")


def test_generate_summary_anthropic_path(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setattr(
        summarizer.requests,
        "post",
        lambda *a, **k: FakeResp(_anthropic_payload("Accomplishments:\n- shipped")),
    )
    out = generate_summary("commit log", provider="anthropic")
    assert out == {
        "summary": "Accomplishments:\n- shipped",
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
    }


def test_generate_summary_openai_path_with_model_override(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(
        summarizer.requests,
        "post",
        lambda *a, **k: FakeResp(_openai_payload("Accomplishments:\n- did it")),
    )
    out = generate_summary("log", provider="groq", model="custom-model")
    assert out["summary"] == "Accomplishments:\n- did it"
    assert out["provider"] == "groq"
    assert out["model"] == "custom-model"


def test_generate_summary_propagates_request_errors(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(summarizer.requests, "post", boom)
    with pytest.raises(requests.RequestException):
        generate_summary("log", provider="anthropic")


def test_summarize_commits_returns_text_only(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(
        summarizer.requests,
        "post",
        lambda *a, **k: FakeResp(_openai_payload("just text")),
    )
    assert summarize_commits("log", provider="deepseek") == "just text"


# --- generate_summary_per_repo ---


def test_per_repo_blank_log_skips_provider():
    out = generate_summary_per_repo({"repo-a": "   "})
    assert out["repo-a"]["summary"] == "No commits in this period."


def test_per_repo_provider_error_is_captured_not_raised():
    # No key configured -> ProviderError captured per repo.
    out = generate_summary_per_repo({"repo-a": "some log"}, provider="anthropic")
    assert out["repo-a"]["summary"].startswith("Error:")


def test_per_repo_success(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(
        summarizer.requests,
        "post",
        lambda *a, **k: FakeResp(_openai_payload("## Features\n- x")),
    )
    out = generate_summary_per_repo({"repo-a": "log"}, provider="groq")
    assert out["repo-a"]["summary"].startswith("## Features")
    assert out["repo-a"]["provider"] == "groq"


def test_per_repo_calls_run_concurrently(monkeypatch):
    """Both provider calls must be in flight at once: each blocks on a barrier
    that only releases when the other arrives. Sequential execution would leave
    the first call waiting alone until the timeout breaks the barrier."""
    import threading

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    barrier = threading.Barrier(2)

    def fake_post(*a, **k):
        barrier.wait(timeout=5)  # raises BrokenBarrierError if run sequentially
        return FakeResp(_openai_payload("ok"))

    monkeypatch.setattr(summarizer.requests, "post", fake_post)
    out = generate_summary_per_repo({"repo-a": "log a", "repo-b": "log b"}, provider="groq")
    assert out["repo-a"]["summary"] == "ok"
    assert out["repo-b"]["summary"] == "ok"


def test_per_repo_preserves_input_order(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(
        summarizer.requests,
        "post",
        lambda *a, **k: FakeResp(_openai_payload("ok")),
    )
    out = generate_summary_per_repo({"zeta": "log", "blank": "  ", "alpha": "log"}, provider="groq")
    assert list(out.keys()) == ["zeta", "blank", "alpha"]
    assert out["blank"]["summary"] == "No commits in this period."
