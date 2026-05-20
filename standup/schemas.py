from pydantic import BaseModel

class IngestRequest(BaseModel):
    repo_path: str
    since: str | None = None
    until: str | None = None
