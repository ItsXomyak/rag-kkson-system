"""Search the ChromaDB collection with hybrid semantic + keyword matching."""

import logging
import re
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


def multi_query_search(
    queries: list[str],
    keyword: str | None = None,
    top_k: int | None = None,
) -> list[SearchResult]:
    """Search with multiple queries and merge results for broader coverage.

    Each query retrieves ``top_k`` candidates independently.  Results are
    deduplicated by (source_file, page_number, chunk_index) keeping the
    highest score, then sorted by score descending.

    Also performs a supplementary keyword-filtered search using content words
    extracted from the original query (first in the list), so that broad or
    conversational queries still find chunks containing the key topic word.
    """
    top_k = top_k or settings.search_top_k
    collection = get_collection()

    if collection.count() == 0:
        logger.warning("Collection is empty. Run ingestion first.")
        return []

    # Embed all queries in one batch for efficiency
    query_embeddings = embed_texts(queries)

    where_doc = None
    if keyword and keyword.strip():
        where_doc = {"$contains": keyword.strip()}

    seen: dict[tuple, SearchResult] = {}

    # --- Semantic search for each query ---
    for emb in query_embeddings:
        raw = collection.query(
            query_embeddings=[emb],
            n_results=top_k,
            where_document=where_doc,
            include=["documents", "metadatas", "distances"],
        )
        for hit in _parse_results(raw):
            key = (hit.source_file, hit.page_number, hit.chunk_index)
            if key not in seen or hit.score > seen[key].score:
                seen[key] = hit

    # --- Supplementary keyword-filtered search ---
    # Extract content words from the original query and require them in chunks.
    # This catches chunks that mention the topic but aren't close in embedding space.
    if not keyword:  # don't duplicate if user already set a keyword filter
        content_words = _extract_content_words(queries[0])
        if content_words:
            kw_filter = (
                {"$contains": content_words[0]}
                if len(content_words) == 1
                else {"$and": [{"$contains": w} for w in content_words[:2]]}
            )
            try:
                raw = collection.query(
                    query_embeddings=[query_embeddings[0]],
                    n_results=top_k,
                    where_document=kw_filter,
                    include=["documents", "metadatas", "distances"],
                )
                kw_hits = _parse_results(raw)
                for hit in kw_hits:
                    key = (hit.source_file, hit.page_number, hit.chunk_index)
                    if key not in seen or hit.score > seen[key].score:
                        seen[key] = hit
                if kw_hits:
                    logger.info(
                        "Keyword-supplementary search for %s → %d extra chunks.",
                        content_words, len(kw_hits),
                    )
            except Exception as exc:
                logger.debug("Keyword-supplementary search failed: %s", exc)

    merged = sorted(seen.values(), key=lambda r: r.score, reverse=True)
    # Cap results — reranker processes each as a cross-encoder pair
    max_for_reranker = top_k + 7  # e.g. 15+7=22, enough headroom for top-8
    logger.info(
        "Multi-query search: %d queries → %d unique chunks (capped to %d).",
        len(queries), len(merged), min(len(merged), max_for_reranker),
    )
    return merged[:max_for_reranker]


# Russian/Kazakh stop words common in conversational queries
_STOP_WORDS = frozenset(
    "и в на по с к о у а но что как где когда это тот эта все они его её их "
    "для при про без над под из за не ни ты мы вы он она оно мне нам вам тебя "
    "какие какой какая каких есть нет было будет быть можно нужно надо "
    "данные информация расскажи покажи найди скажи объясни дай давай "
    "жəне бар жоқ бұл қандай туралы үшін мен сен біз".split()
)


def _extract_content_words(query: str) -> list[str]:
    """Extract meaningful content words from a query for keyword filtering.

    Returns up to 2 words that are likely topic-bearing (not stop words,
    length > 3 chars).  Uses the stem-like prefix for better matching in
    ChromaDB ``$contains`` (e.g. "прав" matches "право", "правовой", etc.).
    """
    words = re.findall(r"[а-яёәіңғүұқөһa-z]+", query.lower())
    content = [w for w in words if len(w) > 3 and w not in _STOP_WORDS]
    if not content:
        return []
    # Trim to stem-like prefix (drop last 2 chars for Russian morphology)
    stems = []
    for w in content:
        stem = w[:-2] if len(w) > 5 else w
        if len(stem) >= 3 and stem not in stems:
            stems.append(stem)
    return stems[:2]


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
