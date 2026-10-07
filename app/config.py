import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure .env variables are loaded from the root directory
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)


def get_groq_api_key() -> str:
    """
    Retrieve GROQ_API_KEY securely from environment without printing or exposing it.
    """
    return os.getenv("GROQ_API_KEY", "").strip()

def is_groq_configured() -> bool:
    """
    Check whether a non-empty GROQ_API_KEY is loaded in environment.
    """
    key = get_groq_api_key()
    return bool(key and key != "your_groq_api_key_here")
