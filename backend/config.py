import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"] # hard brackets because this is required and should fail if not set
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", 8000))
# Summary provider keys (ANTHROPIC_API_KEY / GROQ_API_KEY / DEEPSEEK_API_KEY)
# are read by backend.summarizer at call time, not here.