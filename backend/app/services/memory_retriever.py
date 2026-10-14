import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Set
from app.database import get_db_pool
from app.schemas import MemoryRecord
from app.services.memory_service import record_from_row

logger = logging.getLogger(__name__)

STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does",
    "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had",
    "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd",
    "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself",
    "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over",
    "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't",
    "we", "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when",
    "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's",
    "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your",
    "yours", "yourself", "yourselves"
}

def extract_keywords(text: str) -> List[str]:
    """Extract normalized search keywords from a query string, filtering punctuation and stopwords."""
    words = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]

class BaseMemoryRetriever(ABC):
    """Abstract retriever contract to allow seamless transition to semantic / embedding search."""

    @abstractmethod
    async def retrieve(
        self,
        session_id: str,
        query: str,
        category: Optional[str] = None,
        limit: int = 5
    ) -> List[MemoryRecord]:
        pass

class KeywordMemoryRetriever(BaseMemoryRetriever):
    """
    Retrieves memories using exact keyword matching, category filtering,
    confidence weighting, and recency prioritization under strict session isolation.
    """

    async def retrieve(
        self,
        session_id: str,
        query: str,
        category: Optional[str] = None,
        limit: int = 5
    ) -> List[MemoryRecord]:
        pool = await get_db_pool()
        if pool is None:
            return []

        session_id = session_id.strip()
        keywords = extract_keywords(query)

        async with pool.acquire() as conn:
            # Query all active, non-expired memories for the isolated session
            if category:
                rows = await conn.fetch(
                    """
                    SELECT * FROM memories 
                    WHERE session_id = $1 AND is_active = TRUE 
                      AND (valid_until IS NULL OR valid_until > NOW())
                      AND category = $2
                    ORDER BY updated_at DESC
                    LIMIT 50
                    """,
                    session_id,
                    category.strip().lower(),
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM memories 
                    WHERE session_id = $1 AND is_active = TRUE
                      AND (valid_until IS NULL OR valid_until > NOW())
                    ORDER BY updated_at DESC
                    LIMIT 50
                    """,
                    session_id,
                )

            records = [record_from_row(r) for r in rows]
            if not records:
                return []

            # If no distinctive keywords extracted, return most recent high-confidence memories
            if not keywords:
                records.sort(key=lambda r: (r.confidence_score, r.updated_at), reverse=True)
                return records[:limit]

            # Score each memory by keyword overlap and confidence using word tokens
            scored: List[tuple[float, MemoryRecord]] = []
            for record in records:
                score = 0.0
                mem_key_lower = record.memory_key.lower()
                content_lower = record.content.lower()
                cat_lower = record.category.lower()

                # Tokenize memory fields into distinct word sets
                key_tokens = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", mem_key_lower))
                content_tokens = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", content_lower))
                cat_tokens = set(re.findall(r"\b[a-zA-Z0-9_-]+\b", cat_lower))

                for kw in keywords:
                    if kw in key_tokens or kw == mem_key_lower:
                        score += 3.0
                    elif kw in content_tokens:
                        score += 2.0
                    elif kw in cat_tokens:
                        score += 1.0

                # Weight by confidence
                final_score = score * record.confidence_score
                if final_score > 0:
                    scored.append((final_score, record))

            # Sort primarily by score descending, then recency
            scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
            results = [item[1] for item in scored[:limit]]

            logger.info(f"Retrieved {len(results)} relevant memories for session '{session_id}' against query: '{query[:40]}...'")
            return results

# Default retriever instance
default_retriever = KeywordMemoryRetriever()

async def retrieve_relevant_memories(
    session_id: str,
    query: str,
    category: Optional[str] = None,
    limit: int = 5
) -> List[MemoryRecord]:
    """Helper entry point for retrieving relevant memories for a session."""
    return await default_retriever.retrieve(
        session_id=session_id,
        query=query,
        category=category,
        limit=limit
    )
