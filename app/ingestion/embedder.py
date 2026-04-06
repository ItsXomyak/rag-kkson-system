"""Generate embeddings with bge-m3 and store in ChromaDB."""

import logging
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.ingestion.chunker import Chunk

logger = logging.getLogger(__name__)

# Module-level singletons (lazy-loaded)
_model: Optional[SentenceTransformer] = None
_client: Optional[chromadb.ClientAPI] = None


def get_model() -> SentenceTransformer:
    """Load the embedding model (cached after first call).

    bge-m3 supports 100+ languages including Russian, Kazakh, English.
    ~570M params, runs on CPU (~2-5 sec per batch of 32).
    """
    global _model
    if _model is None:
        logger.info("Loading embedding model '%s'…", settings.embedding_model)
        _model = SentenceTransformer(
            settings.embedding_model,
            cache_folder=settings.embedding_cache_dir,
        )
        logger.info("Model loaded. Embedding dimension: %d.", _model.get_sentence_embedding_dimension())
    return _model


def get_chroma_client() -> chromadb.ClientAPI:
    """Get or create a persistent ChromaDB client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info("ChromaDB client initialized at '%s'.", settings.chroma_dir)
    return _client


def get_collection() -> chromadb.Collection:
    """Get or create the KKSON articles collection."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )


def get_indexed_files() -> set[str]:
    """Return set of source_file names already stored in ChromaDB."""
    collection = get_collection()
    total = collection.count()
    if total == 0:
        return set()

    result = collection.get(include=["metadatas"])
    return {m["source_file"] for m in result["metadatas"] if "source_file" in m}


def embed_texts(texts: list[str], batch_size: int | None = None) -> list[list[float]]:
    """Generate embeddings for a list of texts.

    Args:
        texts: Input strings to embed.
        batch_size: Number of texts per batch (None = use config).

    Returns:
        List of embedding vectors.
    """
    model = get_model()
    if batch_size is None:
        batch_size = settings.embed_batch_size
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    return embeddings.tolist()


def store_chunks(chunks: list[Chunk], batch_size: int | None = None) -> int:
    """Embed chunks and upsert into ChromaDB.

    Args:
        chunks: List of Chunk objects to store.
        batch_size: Chunks per batch for embedding + upsert (None = use config).

    Returns:
        Number of chunks successfully stored.
    """
    if not chunks:
        logger.warning("No chunks to store.")
        return 0

    if batch_size is None:
        batch_size = settings.embed_batch_size
    collection = get_collection()
    stored = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]
        ids = [c.chunk_id for c in batch]
        metadatas = [c.metadata for c in batch]

        logger.info("Embedding batch %d–%d of %d…", i + 1, min(i + batch_size, len(chunks)), len(chunks))
        embeddings = embed_texts(texts, batch_size=batch_size)

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        stored += len(batch)

    logger.info("Stored %d chunks in collection '%s'.", stored, settings.chroma_collection)
    return stored


def collection_count() -> int:
    """Return the number of documents in the collection."""
    return get_collection().count()
