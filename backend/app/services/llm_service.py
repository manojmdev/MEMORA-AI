import logging
from openai import AsyncOpenAI, APIError
from app.config import settings

logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    api_key=settings.NEBIUS_API_KEY,
    base_url=settings.NEBIUS_BASE_URL,
    timeout=60.0,
    max_retries=1
)

async def generate_response(message: str) -> str:
    try:
        response = await client.chat.completions.create(
            model=settings.NEBIUS_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are MEMORA AI, a helpful, "
                        "thoughtful and intelligent personal "
                        "AI assistant. Give clear, accurate "
                        "and useful responses."
                    )
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
        )
        return response.choices[0].message.content or ""
    except APIError as e:
        logger.error(f"Nebius API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in generate_response: {e}")
        raise
