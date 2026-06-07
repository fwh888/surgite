from datetime import date
from pydantic import BaseModel

class IngestRequest(BaseModel):
    repo_path: str
    since: date | None = None
    until: date | None = None

class RepoCreate(BaseModel):
    url: str
