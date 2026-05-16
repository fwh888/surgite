from dataclasses import dataclass

@dataclass
class Commit:
    hash: str # full 40 char git hash
    date: str # YYYY-MM-DD
    author: str # name string
    message: str # commit message string

