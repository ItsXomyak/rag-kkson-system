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
            max_length=512,
            device=settings.reranker_device,
        )
        logger.info("Reranker loaded.")
    return _reranker


def rerank(
    query: str,
    results: list[SearchResult],
    top_k: int | None = None,
) -> list[SearchResult]:
    """Rerank search results using a cross-encoder.

    Takes top-N candidates from vector search and reranks them
    with a more accurate (but slower) cross-encoder model.
    """
    if not results:
        return []

    top_k = top_k or settings.reranker_top_k
    model = get_reranker()

    pairs = [[query, r.text] for r in results]
    scores = model.predict(pairs)

    for result, score in zip(results, scores):
        result.score = round(float(score), 4)

    reranked = sorted(results, key=lambda r: r.score, reverse=True)
    return reranked[:top_k]
