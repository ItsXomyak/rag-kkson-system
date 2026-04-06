"""Tests for embedding and search (requires model download).

Run: python -m pytest tests/test_search.py -v -m "not slow"
Run all: python -m pytest tests/test_search.py -v
"""

from pathlib import Path

import pytest

from app.ingestion.chunker import Chunk


# Mark all tests in this module as slow (they need the embedding model)
pytestmark = pytest.mark.slow


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    return [
        Chunk(
            text="Методы машинного обучения применяются в медицинской диагностике",
            source_file="article1.pdf",
            page_number=1,
            chunk_index=0,
        ),
        Chunk(
            text="Нейронные сети показывают высокую точность классификации изображений",
            source_file="article1.pdf",
            page_number=2,
            chunk_index=1,
        ),
        Chunk(
            text="Казахстанские университеты развивают исследования в области ИИ",
            source_file="article2.pdf",
            page_number=1,
            chunk_index=2,
        ),
    ]


@pytest.fixture
def temp_chroma(tmp_path):
    """Override chroma_dir to use a temp directory."""
    from app.config import settings
    import app.ingestion.embedder as emb

    old_dir = settings.chroma_dir
    # Settings is a frozen dataclass — bypass via object.__setattr__
    object.__setattr__(settings, "chroma_dir", tmp_path / "chroma")
    (tmp_path / "chroma").mkdir()
    emb._client = None
    yield tmp_path / "chroma"
    object.__setattr__(settings, "chroma_dir", old_dir)
    emb._client = None


class TestEmbedder:
    def test_embed_texts(self):
        from app.ingestion.embedder import embed_texts

        vectors = embed_texts(["тестовый текст"])
        assert len(vectors) == 1
        assert len(vectors[0]) == 1024  # bge-m3 dimension

    def test_embed_multilingual(self):
        from app.ingestion.embedder import embed_texts

        texts = [
            "Привет мир",           # Russian
            "Hello world",          # English
            "Сәлем әлем",           # Kazakh
        ]
        vectors = embed_texts(texts)
        assert len(vectors) == 3
        assert all(len(v) == 1024 for v in vectors)

    def test_store_and_count(self, sample_chunks, temp_chroma):
        from app.ingestion.embedder import store_chunks, collection_count

        stored = store_chunks(sample_chunks)
        assert stored == 3
        assert collection_count() == 3

    def test_store_empty(self, temp_chroma):
        from app.ingestion.embedder import store_chunks

        assert store_chunks([]) == 0


class TestSearch:
    def test_semantic_search(self, sample_chunks, temp_chroma):
        from app.ingestion.embedder import store_chunks
        from app.retrieval.search import semantic_search

        store_chunks(sample_chunks)
        results = semantic_search("машинное обучение в медицине", top_k=2)

        assert len(results) == 2
        assert results[0].score > 0
        assert "article1.pdf" in results[0].citation

    def test_hybrid_search_with_keyword(self, sample_chunks, temp_chroma):
        from app.ingestion.embedder import store_chunks
        from app.retrieval.search import hybrid_search

        store_chunks(sample_chunks)
        results = hybrid_search("исследования", keyword="Казахстан")

        assert len(results) >= 1
        assert any("Казахстан" in r.text for r in results)

    def test_search_empty_collection(self, temp_chroma):
        from app.retrieval.search import semantic_search

        results = semantic_search("test query")
        assert results == []
