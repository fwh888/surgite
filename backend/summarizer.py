"""Model-agnostic commit summarization.

One summary, any provider. Pick the provider via the LLM_PROVIDER env var or
per call. GROQ and DeepSeek expose OpenAI-compatible chat endpoints, so they
share a code path; Anthropic uses its Messages API. All calls go over plain
HTTP via `requests` so no provider SDK is required.
"""

import os
from dataclasses import dataclass

import requests

_TIMEOUT = 120
_MAX_TOKENS = 1024
DEFAULT_PROVIDER = "anthropic"


class ProviderError(Exception):
    """Provider is unknown or its API key is not configured."""


@dataclass(frozen=True)
class Provider:
    name: str
    kind: str  # "openai" (GROQ/DeepSeek-compatible) or "anthropic"
    base_url: str
    key_env: str
    model_env: str
    default_model: str

    @property
    def api_key(self) -> str | None:
        # Read at call time so .env (loaded by backend.config) is in effect.
        return os.environ.get(self.key_env) or None

    def model(self, override: str | None = None) -> str:
        return override or os.environ.get(self.model_env) or self.default_model


PROVIDERS: dict[str, Provider] = {
    "groq": Provider(
        name="groq",
        kind="openai",
        base_url="https://api.groq.com/openai/v1",
        key_env="GROQ_API_KEY",
        model_env="GROQ_MODEL",
        default_model="llama-3.1-8b-instant",
    ),
    "deepseek": Provider(
        name="deepseek",
        kind="openai",
        base_url="https://api.deepseek.com",
        key_env="DEEPSEEK_API_KEY",
        model_env="DEEPSEEK_MODEL",
        default_model="deepseek-chat",
    ),
    "anthropic": Provider(
        name="anthropic",
        kind="anthropic",
        base_url="https://api.anthropic.com",
        key_env="ANTHROPIC_API_KEY",
        model_env="ANTHROPIC_MODEL",
        default_model="claude-haiku-4-5-20251001",
    ),
}


def default_provider() -> str:
    return (os.environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER).lower()


def resolve_provider(name: str | None) -> Provider:
    """Look up a provider by name, falling back to the configured default."""
    name = (name or default_provider()).lower()
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ProviderError(
            f"Unknown provider {name!r}; choose from {', '.join(PROVIDERS)}"
        )
    return provider


def provider_status() -> list[dict]:
    """Provider catalogue for clients: name, default model, and whether a key
    is configured. Lets a UI offer only the providers that will actually work."""
    default = default_provider()
    return [
        {
            "name": p.name,
            "model": p.model(),
            "available": p.api_key is not None,
            "default": p.name == default,
        }
        for p in PROVIDERS.values()
    ]


def _build_system_prompt() -> str:
    user = os.environ.get("STANDUP_USER", "")
    role = os.environ.get("STANDUP_ROLE", "")
    who = f"{user} ({role})" if user and role else user or "the developer"
    attribution = f"All commits were authored by {who}." if who != "the developer" else ""
    return (
        "You are a tool that summarizes git commit history into a concise list of accomplishments. "
        + (attribution + " " if attribution else "")
        + "Given the git commits, output a short list of what was accomplished. "
        "Format the response as:\n\nAccomplishments:\n- <item>\n- <item>\n\n"
        "Each bullet should describe a distinct piece of work in plain, neutral language. "
        "Do not use first person. Do not add headers beyond 'Accomplishments:'. No filler or sign-off."
    )


def _call_openai_compatible(
    provider: Provider, api_key: str, model: str, system: str, user_text: str
) -> str:
    resp = requests.post(
        f"{provider.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or "No summary available."


def _call_anthropic(
    provider: Provider, api_key: str, model: str, system: str, user_text: str
) -> str:
    resp = requests.post(
        f"{provider.base_url}/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user_text}],
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    blocks = resp.json().get("content", [])
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return text or "No summary available."


def generate_summary(
    commit_log: str,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """Summarize a formatted commit log with the chosen (or default) provider.

    Returns the summary plus the provider and model actually used. Raises
    ProviderError if the provider is unknown or its key is missing; lets
    requests exceptions propagate so callers can map them to a 502.
    """
    resolved = resolve_provider(provider)
    api_key = resolved.api_key
    if api_key is None:
        raise ProviderError(f"{resolved.key_env} is not set")

    chosen_model = resolved.model(model)
    system = _build_system_prompt()
    if resolved.kind == "anthropic":
        summary = _call_anthropic(resolved, api_key, chosen_model, system, commit_log)
    else:
        summary = _call_openai_compatible(resolved, api_key, chosen_model, system, commit_log)

    return {"summary": summary, "provider": resolved.name, "model": chosen_model}


def summarize_commits(summary: str, provider: str | None = None) -> str:
    """Backward-compatible helper (used by the CLI): returns just the text."""
    return generate_summary(summary, provider=provider)["summary"]
