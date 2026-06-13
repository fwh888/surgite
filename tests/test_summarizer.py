import httpx
import pytest

from backend import summarizer
from backend.summarizer import (
    ProviderError,
    default_provider,
    generate_summary,
    generate_summary_per_repo,
    provider_status,
    resolve_provider,
    stream_summary,
    summarize_commits,
)


def _mock_client(handler) -> httpx.AsyncClient:
    """An AsyncClient whose requests are answered by `handler(request)` instead
    of hitting the network — exercises the real request-building and
    response-parsing code paths."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _anthropic_response(text: str) -> httpx.Response:
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})


def _openai_response(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


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


# --- generate_summary (async, httpx) ---


async def test_generate_summary_missing_key_raises():
    # conftest leaves ANTHROPIC_API_KEY empty.
    with pytest.raises(ProviderError):
        await generate_summary("log", provider="anthropic")


async def test_generate_summary_anthropic_path(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    client = _mock_client(lambda req: _anthropic_response("Accomplishments:\n- shipped"))
    out = await generate_summary("commit log", provider="anthropic", client=client)
    assert out == {
        "summary": "Accomplishments:\n- shipped",
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
    }


async def test_generate_summary_anthropic_request_shape(monkeypatch):
    """The Anthropic path must hit /v1/messages with the x-api-key header."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["key"] = req.headers.get("x-api-key")
        return _anthropic_response("ok")

    await generate_summary("log", provider="anthropic", client=_mock_client(handler))
    assert seen["url"].endswith("/v1/messages")
    assert seen["key"] == "sk-ant-test"


async def test_generate_summary_openai_path_with_model_override(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    client = _mock_client(lambda req: _openai_response("Accomplishments:\n- did it"))
    out = await generate_summary("log", provider="groq", model="custom-model", client=client)
    assert out["summary"] == "Accomplishments:\n- did it"
    assert out["provider"] == "groq"
    assert out["model"] == "custom-model"


async def test_generate_summary_propagates_request_errors(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(httpx.HTTPError):
        await generate_summary("log", provider="anthropic", client=_mock_client(boom))


async def test_generate_summary_raises_on_http_error_status(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    client = _mock_client(lambda req: httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(httpx.HTTPStatusError):
        await generate_summary("log", provider="groq", client=client)


def test_summarize_commits_returns_text_only(monkeypatch):
    """The CLI helper is sync; it drives the async path on its own loop."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

    async def fake_generate(*a, **k):
        return {"summary": "just text", "provider": "deepseek", "model": "x"}

    monkeypatch.setattr(summarizer, "generate_summary", fake_generate)
    assert summarize_commits("log", provider="deepseek") == "just text"


# --- generate_summary_per_repo ---


async def test_per_repo_blank_log_skips_provider():
    out = await generate_summary_per_repo({"repo-a": "   "})
    assert out["repo-a"]["summary"] == "No commits in this period."


async def test_per_repo_provider_error_is_captured_not_raised():
    # No key configured -> ProviderError captured per repo.
    out = await generate_summary_per_repo({"repo-a": "some log"}, provider="anthropic")
    assert out["repo-a"]["summary"].startswith("Error:")


async def test_per_repo_success(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    async def fake_generate(log_text, **kwargs):
        return {"summary": "## Features\n- x", "provider": "groq", "model": "m"}

    monkeypatch.setattr(summarizer, "generate_summary", fake_generate)
    out = await generate_summary_per_repo({"repo-a": "log"}, provider="groq")
    assert out["repo-a"]["summary"].startswith("## Features")
    assert out["repo-a"]["provider"] == "groq"


async def test_per_repo_uses_per_repo_settings(monkeypatch):
    """settings_by_repo overrides the fallback `settings` per repo."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    seen: dict[str, dict | None] = {}

    async def fake_generate(log_text, provider=None, settings=None, client=None):
        seen[log_text] = settings
        return {"summary": "ok", "provider": "groq", "model": "m"}

    monkeypatch.setattr(summarizer, "generate_summary", fake_generate)
    await generate_summary_per_repo(
        {"a": "log-a", "b": "log-b"},
        provider="groq",
        settings={"tone": "neutral"},
        settings_by_repo={"a": {"tone": "casual"}},
    )
    assert seen["log-a"] == {"tone": "casual"}
    assert seen["log-b"] == {"tone": "neutral"}


async def test_per_repo_preserves_input_order(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    async def fake_generate(log_text, **kwargs):
        return {"summary": "ok", "provider": "groq", "model": "m"}

    monkeypatch.setattr(summarizer, "generate_summary", fake_generate)
    out = await generate_summary_per_repo(
        {"zeta": "log", "blank": "  ", "alpha": "log"}, provider="groq"
    )
    assert list(out.keys()) == ["zeta", "blank", "alpha"]
    assert out["blank"]["summary"] == "No commits in this period."


# --- stream_summary ---


async def test_stream_summary_openai_yields_deltas(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    sse = (
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    client = _mock_client(lambda req: httpx.Response(200, content=sse))
    chunks = [c async for c in stream_summary("log", provider="groq", client=client)]
    assert "".join(chunks) == "Hello world"


async def test_stream_summary_anthropic_yields_deltas(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    sse = (
        b"event: content_block_delta\n"
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi "}}\n\n'
        b"event: content_block_delta\n"
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"there"}}\n\n'
        b"event: message_stop\ndata: {}\n\n"
    )
    client = _mock_client(lambda req: httpx.Response(200, content=sse))
    chunks = [c async for c in stream_summary("log", provider="anthropic", client=client)]
    assert "".join(chunks) == "Hi there"


async def test_stream_summary_missing_key_raises():
    with pytest.raises(ProviderError):
        async for _ in stream_summary("log", provider="anthropic"):
            pass


async def test_stream_summary_raises_on_http_error_status(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    client = _mock_client(lambda req: httpx.Response(429, json={"error": "rate"}))
    with pytest.raises(httpx.HTTPStatusError):
        async for _ in stream_summary("log", provider="groq", client=client):
            pass
