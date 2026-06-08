from pydantic import BaseModel


class RepoCreate(BaseModel):
    url: str
