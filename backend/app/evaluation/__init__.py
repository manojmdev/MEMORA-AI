"""
MEMORA AI — Memory Intelligence & Retrieval Evaluation Module
Provides quantitative benchmark datasets, retrieval metrics, evaluation runner, and report generation.
"""
from app.evaluation.dataset import EVALUATION_BENCHMARK_SUITE, SeedMemory, TestCase
from app.evaluation.retrieval_metrics import (
    compute_precision_at_k,
    compute_recall_at_k,
    compute_reciprocal_rank,
    compute_ndcg_at_k,
    EvaluationMetricsResult
)
from app.evaluation.retrieval_evaluator import run_retrieval_evaluation
from app.evaluation.report_generator import generate_evaluation_markdown_report

__all__ = [
    "EVALUATION_BENCHMARK_SUITE",
    "SeedMemory",
    "TestCase",
    "compute_precision_at_k",
    "compute_recall_at_k",
    "compute_reciprocal_rank",
    "compute_ndcg_at_k",
    "EvaluationMetricsResult",
    "run_retrieval_evaluation",
    "generate_evaluation_markdown_report",
]
