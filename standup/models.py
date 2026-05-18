from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Commit:
    hash: str # full 40 char git hash
    date: str # YYYY-MM-DD
    author: str # name string
    message: str # commit message string
    repo: str | None = field(default=None) # optional repo name string
    ingested_at: datetime | None = field(default=None) # optional datetime of when the commit was ingested
    
