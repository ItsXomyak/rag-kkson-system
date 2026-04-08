"""Cross-encoder reranker to reduce noise in search results."""

import logging
from typing import Optional

from sentence_transformers import CrossEncoder

from app.config import settings
from app.retrieval.search import SearchResult

logger = logging.getLogger(__name__)

_reranker: Optional[CrossEncoder] = None


def get_reranker() -> CrossEncoder:
    """Load the cross-encoder model (cached after first call)."""
    global _reranker
    if _reranker is None:
        logger.info("Loading reranker model '%s' on device '%s'…", settings.reranker_model, settings.reranker_device)
        _reranker = CrossEncoder(
            settings.reranker_model,
            max_length=settings.reranker_max_length,
            device=settings.reranker_device,
        )
        logger.info("Reranker loaded.")
    return _reranker


def rerank(
    query: str,
    results: list[SearchResult],
    top_k: int | None = None,
    alt_queries: list[str] | None = None,
) -> list[SearchResult]:
    """Rerank search results using a cross-encoder.

    Uses the best single query for scoring: prefers the first expanded
    sub-query (content-focused) over the original (which may be
    conversational/meta).  This keeps reranking fast (N pairs instead of
    N×Q) while still handling meta-questions well.
    """
    if not results:
        return []

    top_k = top_k or settings.reranker_top_k
    model = get_reranker()

    # Pick best query: first expanded sub-query if available (content-focused),
    # otherwise fall back to the original query.
    rerank_query = alt_queries[0] if alt_queries else query

    pairs = [[rerank_query, r.text] for r in results]
    scores = model.predict(pairs)
    for result, score in zip(results, scores):
        result.score = round(float(score), 4)

    reranked = sorted(results, key=lambda r: r.score, reverse=True)

    # Drop results the cross-encoder considers irrelevant
    min_score = settings.reranker_min_score
    before = len(reranked)
    reranked = [r for r in reranked if r.score >= min_score]
    if len(reranked) < before:
        logger.info(
            "Reranker filtered %d/%d results below min_score=%.1f",
            before - len(reranked), before, min_score,
        )

    return reranked[:top_k]
