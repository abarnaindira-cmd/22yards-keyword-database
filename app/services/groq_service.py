import logging
from typing import Optional
from groq import Groq
from app.config import get_groq_api_key, is_groq_configured

logger = logging.getLogger("groq_service")

def get_groq_client() -> Optional[Groq]:
    """
    Initialize and return a Groq client instance using the configured GROQ_API_KEY.
    Ensures the key is read securely without printing or exposing it in log files or console.
    Returns None if GROQ_API_KEY is not set or empty.
    """
    api_key = get_groq_api_key()
    if not api_key or api_key == "your_groq_api_key_here":
        logger.info("GROQ_API_KEY is not configured.")
        return None

    try:
        # Keep retries in the title service, where 429 backoff and request
        # budgets are observable. The SDK defaults to two hidden retries.
        client = Groq(api_key=api_key, max_retries=0)
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {type(e).__name__}")
        return None
