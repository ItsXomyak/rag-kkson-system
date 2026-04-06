"""Split extracted page text into overlapping chunks for embedding."""

import logging
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.ingestion.pdf_parser import PageContent

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A text chunk ready for embedding, with full provenance."""

    text: str
    source_file: str
    page_number: int
    chunk_index: int

    @property
    def chunk_id(self) -> str:
        """Unique ID for ChromaDB: filename__p3__c2."""
        stem = self.source_file.rsplit(".", 1)[0]
        return f"{stem}__p{self.page_number}__c{self.chunk_index}"

    @property
    def metadata(self) -> dict:
        """Metadata dict for ChromaDB storage."""
        return {
            "source_file": self.source_file,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
        }


def create_splitter() -> RecursiveCharacterTextSplitter:
    """Create a text splitter tuned for Russian/Kazakh academic text.

    Uses paragraph → sentence → word boundaries, with ~500-token chunks.
    For Cyrillic text, 1 token ≈ 3 chars, so 1500 chars ≈ 500 tokens.
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""],
        length_function=len,
        is_separator_regex=False,
    )


def chunk_pages(pages: list[PageContent]) -> list[Chunk]:
    """Split a list of pages into overlapping chunks.

    Args:
        pages: Extracted page contents from pdf_parser.

    Returns:
        List of Chunk objects with provenance metadata.
    """
    if not pages:
        logger.warning("No pages to chunk.")
        return []

    splitter = create_splitter()
    chunks: list[Chunk] = []
    global_index = 0

    for page in pages:
        splits = splitter.split_text(page.text)

        for i, text in enumerate(splits):
            if len(text.strip()) < 30:
                continue

            chunks.append(
                Chunk(
                    text=text.strip(),
                    source_file=page.source_file,
                    page_number=page.page_number,
                    chunk_index=global_index,
                )
            )
            global_index += 1

    logger.info(
        "Chunking complete: %d pages → %d chunks (avg %d chars/chunk).",
        len(pages),
        len(chunks),
        sum(len(c.text) for c in chunks) // max(len(chunks), 1),
    )
    return chunks
