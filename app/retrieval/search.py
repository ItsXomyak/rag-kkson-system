"""Search the ChromaDB collection with hybrid semantic + keyword matching."""

import logging
from dataclasses import dataclass

from app.config import settings
from app.ingestion.embedder import embed_texts, get_collection

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search hit with text, metadata, and relevance score."""

    text: str
    source_file: str
    page_number: int
    chunk_index: int
    score: float  # cosine similarity (0–1, higher = more relevant)

    @property
    def citation(self) -> str:
        """Human-readable source reference."""
        return f"[{self.source_file}, стр. {self.page_number}]"


def semantic_search(query: str, top_k: int | None = None) -> list[SearchResult]:
    """Find the most relevant chunks for a query using vector similarity.

    Args:
        query: User's research question.
        top_k: Number of results (defaults to settings.search_top_k).

    Returns:
        List of SearchResult sorted by relevance (best first).
    """
    top_k = top_k or settings.search_top_k
    collection = get_collection()

    if collection.count() == 0:
        logger.warning("Collection is empty. Run ingestion first.")
        return []

    query_embedding = embed_texts([query])[0]

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    return _parse_results(results)


def hybrid_search(
    query: str,
    keyword: str | None = None,
    top_k: int | None = None,
) -> list[SearchResult]:
    """Combine semantic search with optional keyword filtering.

    Args:
        query: User's research question (for semantic matching).
        keyword: Optional keyword that MUST appear in the chunk text.
        top_k: Number of results.

    Returns:
        List of SearchResult sorted by relevance.
    """
    top_k = top_k or settings.search_top_k
    collection = get_collection()

    if collection.count() == 0:
        logger.warning("Collection is empty. Run ingestion first.")
        return []

    query_embedding = embed_texts([query])[0]

    where_doc = None
    if keyword and keyword.strip():
        where_doc = {"$contains": keyword.strip()}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where_document=where_doc,
        include=["documents", "metadatas", "distances"],
    )

    return _parse_results(results)


def _parse_results(raw: dict) -> list[SearchResult]:
    """Convert ChromaDB query results into SearchResult objects."""
    hits: list[SearchResult] = []

    if not raw["ids"] or not raw["ids"][0]:
        return hits

    for doc, meta, dist in zip(
        raw["documents"][0],
        raw["metadatas"][0],
        raw["distances"][0],
    ):
        # ChromaDB returns cosine *distance* (0=identical); convert to similarity
        score = 1.0 - dist

        # Score threshold — drop irrelevant chunks
        if score < settings.score_threshold:
            continue

        hits.append(
            SearchResult(
                text=doc,
                source_file=meta.get("source_file", "unknown"),
                page_number=meta.get("page_number", 0),
                chunk_index=meta.get("chunk_index", 0),
                score=round(score, 4),
            )
        )

    return hits
