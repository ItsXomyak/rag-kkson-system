"""Centralized configuration for the RAG-KKSON application."""

import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env BEFORE reading any os.getenv calls
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables with sensible defaults."""

    # Paths
    base_dir: Path = field(default=BASE_DIR)
    pdf_dir: Path = field(default_factory=lambda: BASE_DIR / "data" / "pdfs")
    chroma_dir: Path = field(
        default_factory=lambda: Path(os.getenv("CHROMA_PATH", str(BASE_DIR / "chroma_db")))
    )

    # Embedding model
    embedding_model: str = "BAAI/bge-m3"
    embedding_cache_dir: str = field(
        default_factory=lambda: os.getenv("MODEL_CACHE_DIR", "./model_cache")
    )

    # ChromaDB
    chroma_collection: str = "kkson_articles"

    # Chunking
    chunk_size: int = 1500  # ~500 tokens ≈ 1500 chars for ru/kz text
    chunk_overlap: int = 150  # ~50 tokens overlap

    # Ingestion
    embed_batch_size: int = field(
        default_factory=lambda: int(os.getenv("EMBED_BATCH_SIZE", "64"))
    )

    # Retrieval
    search_top_k: int = 10
    score_threshold: float = 0.3  # min cosine similarity to keep

    # Reranker (cross-encoder)
    reranker_enabled: bool = field(
        default_factory=lambda: os.getenv("RERANKER_ENABLED", "true").lower() in ("true", "1", "yes")
    )
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_top_k: int = 5  # return top-5 after reranking top-10
    reranker_device: str = field(
        default_factory=lambda: os.getenv("RERANKER_DEVICE", "cpu")
    )

    # LLM (OpenAI-compatible API — Alem AI / Qwen 3)
    llm_api_key: str = field(
        default_factory=lambda: os.getenv("LLM_API_KEY", "")
    )
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "https://llm.alem.ai/v1")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "qwen3")
    )
    llm_max_tokens: int = 4096

    # Server
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    def __post_init__(self) -> None:
        """Ensure required directories exist."""
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)


# Singleton
settings = Settings()
