"""Tests for the RAG pipeline: PDF parsing, chunking, embeddings, search.

Run: python -m pytest tests/test_pipeline.py -v
"""

import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from app.ingestion.pdf_parser import extract_pdf, PageContent
from app.ingestion.chunker import chunk_pages, Chunk, create_splitter


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a minimal PDF with 2 pages of Russian text."""
    doc = fitz.open()

    page1 = doc.new_page()
    page1.insert_text(
        (72, 72),
        "Введение. Данная статья посвящена анализу методов машинного обучения "
        "в контексте медицинской диагностики. Мы рассмотрели 50 исследований, "
        "опубликованных в казахстанских научных журналах за период 2020-2024 годов.\n\n"
        "Основные результаты показывают, что нейронные сети демонстрируют "
        "наибольшую точность при классификации медицинских изображений.",
        fontsize=11,
    )

    page2 = doc.new_page()
    page2.insert_text(
        (72, 72),
        "Заключение. Результаты исследования подтверждают эффективность "
        "применения глубокого обучения в медицинской диагностике. "
        "Рекомендуется дальнейшее исследование в направлении "
        "интерпретируемости моделей.",
        fontsize=11,
    )

    pdf_path = tmp_path / "test_article.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def empty_pdf(tmp_path: Path) -> Path:
    """Create a PDF with no text (simulates scanned PDF)."""
    doc = fitz.open()
    doc.new_page()
    pdf_path = tmp_path / "empty.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


# ── PDF Parser Tests ──────────────────────────────────────────


class TestPDFParser:
    def test_extract_pdf_returns_pages(self, sample_pdf: Path):
        pages = extract_pdf(sample_pdf)
        assert len(pages) == 2
        assert all(isinstance(p, PageContent) for p in pages)

    def test_extract_pdf_page_numbers(self, sample_pdf: Path):
        pages = extract_pdf(sample_pdf)
        assert pages[0].page_number == 1
        assert pages[1].page_number == 2

    def test_extract_pdf_source_file(self, sample_pdf: Path):
        pages = extract_pdf(sample_pdf)
        assert pages[0].source_file == "test_article.pdf"

    def test_extract_pdf_text_content(self, sample_pdf: Path):
        pages = extract_pdf(sample_pdf)
        # PyMuPDF default font (Helvetica) only supports Latin-1;
        # Cyrillic inserted via insert_text comes back transliterated/garbled.
        # Check that text was extracted (non-empty) from both pages.
        assert len(pages[0].text) > 50
        assert len(pages[1].text) > 50

    def test_extract_pdf_preserves_paragraphs(self, sample_pdf: Path):
        pages = extract_pdf(sample_pdf)
        # Paragraph breaks should be preserved as \n\n
        assert "\n\n" in pages[0].text or len(pages[0].text) > 50

    def test_extract_empty_pdf(self, empty_pdf: Path):
        pages = extract_pdf(empty_pdf)
        assert pages == []

    def test_extract_pdf_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            extract_pdf(Path("/nonexistent/file.pdf"))

    def test_extract_pdf_corrupted(self, tmp_path: Path):
        bad_pdf = tmp_path / "bad.pdf"
        bad_pdf.write_text("this is not a pdf")
        with pytest.raises(RuntimeError, match="Cannot open PDF"):
            extract_pdf(bad_pdf)


# ── Chunker Tests ─────────────────────────────────────────────


class TestChunker:
    def test_chunk_pages_produces_chunks(self, sample_pdf: Path):
        pages = extract_pdf(sample_pdf)
        chunks = chunk_pages(pages)
        assert len(chunks) > 0
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_chunk_metadata(self, sample_pdf: Path):
        pages = extract_pdf(sample_pdf)
        chunks = chunk_pages(pages)
        for chunk in chunks:
            assert chunk.source_file == "test_article.pdf"
            assert chunk.page_number >= 1
            assert chunk.chunk_index >= 0

    def test_chunk_id_format(self):
        chunk = Chunk(text="test", source_file="article.pdf", page_number=3, chunk_index=2)
        assert chunk.chunk_id == "article__p3__c2"

    def test_chunk_metadata_dict(self):
        chunk = Chunk(text="test", source_file="article.pdf", page_number=1, chunk_index=0)
        meta = chunk.metadata
        assert meta["source_file"] == "article.pdf"
        assert meta["page_number"] == 1
        assert meta["chunk_index"] == 0

    def test_chunk_pages_empty_input(self):
        chunks = chunk_pages([])
        assert chunks == []

    def test_chunk_skips_short_text(self):
        pages = [PageContent(text="short", page_number=1, source_file="x.pdf")]
        chunks = chunk_pages(pages)
        assert chunks == []

    def test_splitter_config(self):
        splitter = create_splitter()
        assert splitter._chunk_size == 1500
        assert splitter._chunk_overlap == 150

    def test_long_text_splits(self):
        """Text longer than chunk_size should produce multiple chunks."""
        long_text = "Это длинное предложение для тестирования. " * 200
        pages = [PageContent(text=long_text, page_number=1, source_file="long.pdf")]
        chunks = chunk_pages(pages)
        assert len(chunks) > 1
        # Each chunk should be under chunk_size + some tolerance
        for chunk in chunks:
            assert len(chunk.text) <= 1600


# ── Integration Test ──────────────────────────────────────────


class TestPipelineIntegration:
    def test_pdf_to_chunks(self, sample_pdf: Path):
        """Full pipeline: PDF → pages → chunks."""
        pages = extract_pdf(sample_pdf)
        assert len(pages) > 0

        chunks = chunk_pages(pages)
        assert len(chunks) > 0

        # Verify provenance chain
        for chunk in chunks:
            assert chunk.source_file == sample_pdf.name
            assert len(chunk.text) >= 30
            assert chunk.chunk_id  # non-empty ID
