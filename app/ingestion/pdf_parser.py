"""Extract text and metadata from PDF files using PyMuPDF (fitz)."""

import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    """A single page extracted from a PDF."""

    text: str
    page_number: int
    source_file: str


def extract_pdf(pdf_path: Path) -> list[PageContent]:
    """Extract text from each page of a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of PageContent objects, one per page with text.

    Raises:
        FileNotFoundError: If the PDF file doesn't exist.
        RuntimeError: If the PDF is corrupted or unreadable.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages: list[PageContent] = []
    source = pdf_path.name

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        raise RuntimeError(f"Cannot open PDF '{source}': {exc}") from exc

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").strip()

            if not text:
                logger.debug("Page %d of '%s' is empty (possibly scanned).", page_num + 1, source)
                continue

            # Preserve paragraph structure (double newlines) but clean up within paragraphs
            paragraphs = text.split("\n\n")
            cleaned_parts = []
            for para in paragraphs:
                clean_para = " ".join(para.split())
                if clean_para:
                    cleaned_parts.append(clean_para)
            cleaned = "\n\n".join(cleaned_parts)

            if len(cleaned) < 20:
                logger.debug("Page %d of '%s' has too little text, skipping.", page_num + 1, source)
                continue

            pages.append(
                PageContent(
                    text=cleaned,
                    page_number=page_num + 1,  # 1-indexed
                    source_file=source,
                )
            )
    finally:
        doc.close()

    if not pages:
        logger.warning("No extractable text found in '%s'. Might be a scanned PDF.", source)

    return pages


def extract_all_pdfs(pdf_dir: Path) -> list[PageContent]:
    """Extract text from every PDF in a directory.

    Args:
        pdf_dir: Directory containing PDF files.

    Returns:
        Flat list of PageContent from all PDFs.
    """
    pdf_files = sorted(pdf_dir.glob("*.pdf"))

    if not pdf_files:
        logger.warning("No PDF files found in '%s'.", pdf_dir)
        return []

    logger.info("Found %d PDF files in '%s'.", len(pdf_files), pdf_dir)

    all_pages: list[PageContent] = []
    failed = 0

    for pdf_path in pdf_files:
        try:
            pages = extract_pdf(pdf_path)
            all_pages.extend(pages)
            logger.info("  ✓ %s — %d pages extracted.", pdf_path.name, len(pages))
        except (RuntimeError, FileNotFoundError) as exc:
            logger.error("  ✗ %s — %s", pdf_path.name, exc)
            failed += 1

    logger.info(
        "Extraction complete: %d pages from %d files (%d failed).",
        len(all_pages),
        len(pdf_files) - failed,
        failed,
    )
    return all_pages
