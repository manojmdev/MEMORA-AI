import asyncio
import logging
from typing import List, Optional
from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError
from app.config import settings

logger = logging.getLogger(__name__)

# Dedicated client for embeddings
_client: Optional[AsyncOpenAI] = None

def get_embedding_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.NEBIUS_API_KEY,
            base_url=settings.EMBEDDING_API_BASE_URL or settings.NEBIUS_BASE_URL,
            timeout=30.0,
            max_retries=1
        )
    return _client

import hashlib

# Simple in-memory LRU-like cache for frequent embeddings (session-agnostic)
_embedding_cache: dict[str, List[float]] = {}
_MAX_CACHE_ENTRIES = 512
_in_flight_locks: dict[str, asyncio.Event] = {}
_in_flight_results: dict[str, Optional[List[float]]] = {}

def vector_to_sql_str(embedding: List[float]) -> str:
    """Format a list of floats into a PostgreSQL vector string representation: '[0.1,0.2,...]'."""
    return f"[{','.join(f'{x:.8f}' for x in embedding)}]"

async def generate_embedding(text: str, is_query: bool = False) -> Optional[List[float]]:
    """
    Generate a normalized embedding vector for a given text using the configured Nebius model.
    Validates output dimension, handles timeouts, and deduplicates in-flight identical requests.
    """
    if not text or not text.strip():
        return None

    cleaned_text = text.strip()
    cache_key = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()

    # Fast in-memory cache hit
    if cache_key in _embedding_cache:
        return _embedding_cache[cache_key]

    # In-flight deduplication: if an identical request is currently active, await its outcome
    if cache_key in _in_flight_locks:
        await _in_flight_locks[cache_key].wait()
        return _in_flight_results.get(cache_key)

    # Register in-flight gate for concurrent callers
    event = asyncio.Event()
    _in_flight_locks[cache_key] = event
    client = get_embedding_client()

    try:
        response = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=cleaned_text,
            dimensions=settings.EMBEDDING_DIMENSION
        )

        if not response.data or not response.data[0].embedding:
            logger.warning("Embedding service returned empty response data.")
            _in_flight_results[cache_key] = None
            return None

        embedding = response.data[0].embedding

        # Validate vector dimension
        if len(embedding) != settings.EMBEDDING_DIMENSION:
            logger.error(
                f"Vector dimension mismatch: expected {settings.EMBEDDING_DIMENSION}, "
                f"got {len(embedding)}. Discarding invalid vector."
            )
            _in_flight_results[cache_key] = None
            return None

        # Store in LRU cache
        if len(_embedding_cache) >= _MAX_CACHE_ENTRIES:
            oldest_key = next(iter(_embedding_cache))
            del _embedding_cache[oldest_key]
        _embedding_cache[cache_key] = embedding
        _in_flight_results[cache_key] = embedding
        return embedding

    except APIConnectionError as e:
        logger.error(f"Embedding service connection error: {e}")
        _in_flight_results[cache_key] = None
        return None
    except RateLimitError as e:
        logger.error(f"Embedding service rate limit reached: {e}")
        return None
    except APIError as e:
        logger.error(f"Embedding service API error: {e.message if hasattr(e, 'message') else e}")
        return None
    except asyncio.TimeoutError:
        logger.error("Embedding generation timed out after 30 seconds.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in embedding generation: {e.__class__.__name__}")
        _in_flight_results[cache_key] = None
        return None
    finally:
        event.set()
        _in_flight_locks.pop(cache_key, None)

async def generate_embeddings_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """Generate embeddings for a list of texts in batch."""
    if not texts:
        return []

    valid_indices = [i for i, t in enumerate(texts) if t and t.strip()]
    cleaned_texts = [texts[i].strip() for i in valid_indices]

    results: List[Optional[List[float]]] = [None] * len(texts)
    if not cleaned_texts:
        return results

    client = get_embedding_client()

    try:
        response = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=cleaned_texts,
            dimensions=settings.EMBEDDING_DIMENSION
        )

        for i, item in enumerate(response.data):
            orig_idx = valid_indices[i]
            if len(item.embedding) == settings.EMBEDDING_DIMENSION:
                results[orig_idx] = item.embedding
            else:
                logger.error(f"Batch item {i} dimension mismatch: {len(item.embedding)}")

    except Exception as e:
        logger.error(f"Batch embedding generation error: {e.__class__.__name__}")
        # Fallback to individual calls
        for orig_idx in valid_indices:
            results[orig_idx] = await generate_embedding(texts[orig_idx])

    return results
