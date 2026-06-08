from pydantic import BaseModel


class RepoCreate(BaseModel):
    url: str


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
