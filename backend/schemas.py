from pydantic import BaseModel


class RepoCreate(BaseModel):
    url: str


class ShareCreate(BaseModel):
    """Parameters of a summary to persist behind a shareable slug. Mirrors the
    /summary query string; all fields optional so a bare 'all repos, last 7
    days' share is valid."""

    repo: str | None = None
    since: str | None = None
    until: str | None = None
    author: str | None = None
    ai: bool = False
    provider: str | None = None
    combined: bool = False


class PromptSettings(BaseModel):
    user_name: str = ""
    user_role: str = ""
    tone: str = "neutral"
    group_count: str = "2-5"
    output_format: str = "markdown"
    custom_instructions: str = ""


class PromptSettingsUpdate(BaseModel):
    user_name: str | None = None
    user_role: str | None = None
    tone: str | None = None
    group_count: str | None = None
    output_format: str | None = None
    custom_instructions: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class RedeemInviteRequest(BaseModel):
    """Claim an invite and set the new account's password. `email` is required
    only for an open invite (one with no email pinned); for a pinned invite the
    server uses the invite's email and ignores this field."""

    token: str
    password: str
    email: str | None = None
    display_name: str | None = None
