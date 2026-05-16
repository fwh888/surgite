import os
from groq import Groq

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