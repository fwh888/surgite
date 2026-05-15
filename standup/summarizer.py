import os
from groq import Groq

def _build_system_prompt() -> str:
    user = os.environ.get("STANDUP_USER", "the developer")
    role = os.environ.get("STANDUP_ROLE", "")
    identity = f"{user}, a {role}" if role else user
    return (
        f"You are helping {identity} write a weekly standup update. "
        f"{user if user != 'the developer' else 'They'} wrote all the commits. "
        "Given the git commits, write a brief, plain standup summary in first person. "
        "No bullet points, no headers, no fluff — just some sentences they can copy and send."
    )

def summarize_commits(summary: str) -> str:
    client = Groq()
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": summary},
        ],
    )
    return response.choices[0].message.content or "No summary available."