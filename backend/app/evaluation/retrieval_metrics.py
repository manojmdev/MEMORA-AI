"""
MEMORA AI — Retrieval Evaluation Metrics
Implements quantitative information retrieval metrics:
Precision@K, Recall@K, Mean Reciprocal Rank (MRR), NDCG@K, Latency, and Privacy Leakage.
"""
import math
from dataclasses import dataclass
from typing import List, Set, Optional

@dataclass
class EvaluationMetricsResult:
    test_case_id: str
    name: str
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    latency_ms: float
    leakage_detected: bool
    retrieved_keys: List[str]
    expected_keys: List[str]
    passed: bool

def compute_precision_at_k(
    retrieved_keys: List[str],
    expected_keys: List[str],
    k: int,
    forbidden_keys: Optional[List[str]] = None
) -> float:
    """
    Precision@K: Fraction of retrieved top-K items that are relevant.
    For negative/empty-expected tests (distractor rejection), precision is 1.0 if 0 items retrieved.
    For privacy/isolation tests with forbidden_keys, precision is 1.0 if no forbidden keys leaked.
    """
    top_k = retrieved_keys[:k]
    expected_set: Set[str] = set(expected_keys)

    if not expected_set:
        if forbidden_keys:
            has_leak = any(k in forbidden_keys for k in top_k)
            return 0.0 if has_leak else 1.0
        return 1.0 if len(top_k) == 0 else 0.0

    if not top_k:
        return 0.0

    relevant_retrieved = sum(1 for item in top_k if item in expected_set)
    return round(relevant_retrieved / len(top_k), 4)

def compute_recall_at_k(
    retrieved_keys: List[str],
    expected_keys: List[str],
    k: int,
    forbidden_keys: Optional[List[str]] = None
) -> float:
    """
    Recall@K: Fraction of relevant ground-truth items that were successfully retrieved in top-K.
    For negative/empty-expected tests, recall is 1.0 if 0 items retrieved or 0 forbidden keys leaked.
    """
    top_k = retrieved_keys[:k]
    expected_set: Set[str] = set(expected_keys)

    if not expected_set:
        if forbidden_keys:
            has_leak = any(k in forbidden_keys for k in top_k)
            return 0.0 if has_leak else 1.0
        return 1.0 if len(top_k) == 0 else 0.0

    relevant_retrieved = sum(1 for item in top_k if item in expected_set)
    return round(relevant_retrieved / len(expected_set), 4)

def compute_reciprocal_rank(
    retrieved_keys: List[str],
    expected_keys: List[str],
    forbidden_keys: Optional[List[str]] = None
) -> float:
    """
    Reciprocal Rank (RR): 1 / rank of first relevant item in retrieved list.
    """
    expected_set: Set[str] = set(expected_keys)

    if not expected_set:
        if forbidden_keys:
            has_leak = any(k in forbidden_keys for k in retrieved_keys)
            return 0.0 if has_leak else 1.0
        return 1.0 if len(retrieved_keys) == 0 else 0.0

    for idx, item in enumerate(retrieved_keys):
        if item in expected_set:
            return round(1.0 / (idx + 1), 4)
    return 0.0

def compute_ndcg_at_k(
    retrieved_keys: List[str],
    expected_keys: List[str],
    k: int,
    forbidden_keys: Optional[List[str]] = None
) -> float:
    """
    Normalized Discounted Cumulative Gain (NDCG@K) with binary relevance.
    """
    top_k = retrieved_keys[:k]
    expected_set: Set[str] = set(expected_keys)

    if not expected_set:
        if forbidden_keys:
            has_leak = any(k in forbidden_keys for k in top_k)
            return 0.0 if has_leak else 1.0
        return 1.0 if len(top_k) == 0 else 0.0

    # Calculate Discounted Cumulative Gain (DCG)
    dcg = 0.0
    for idx, item in enumerate(top_k):
        rel = 1.0 if item in expected_set else 0.0
        dcg += rel / math.log2(idx + 2)

    # Calculate Ideal Discounted Cumulative Gain (IDCG)
    idcg = 0.0
    ideal_hits = min(len(expected_set), k)
    for idx in range(ideal_hits):
        idcg += 1.0 / math.log2(idx + 2)

    if idcg == 0.0:
        return 0.0

    return round(dcg / idcg, 4)

def check_cross_session_leakage(retrieved_keys: List[str], forbidden_keys: List[str]) -> bool:
    """
    Returns True if ANY forbidden cross-session key appears in retrieved results.
    """
    forbidden_set = set(forbidden_keys)
    return any(item in forbidden_set for item in retrieved_keys)
