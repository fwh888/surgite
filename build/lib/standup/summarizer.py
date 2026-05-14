from groq import Groq

def summarize_commits(summary: str) -> str:
    client = Groq()
    response = client.chat.completions.create(
        model = "llama-3.1-8b-instant",
        messages = [
            {
                "role": "system",
                "content": (
                    "You are helping Nick write his weekly standup update. "
                    "Nick is the developer who wrote all the commits. "
                    "Given his git commits, write a brief, plain standup summary in first person. "
                    "No bullet points, no headers, no fluff — just some sentences he can copy and send."
                ),
            },
            {"role": "user", "content": summary},
        ],
    )
    return response.choices[0].message.content or "No summary available."