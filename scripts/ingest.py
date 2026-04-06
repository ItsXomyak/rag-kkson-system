#!/usr/bin/env python3
"""CLI script to ingest PDF files into the ChromaDB vector store.

Usage:
    python -m scripts.ingest                  # ingest new PDFs only
    python -m scripts.ingest --force           # re-ingest everything
    python -m scripts.ingest /path/to/pdfs/    # custom directory
    python -m scripts.ingest /path/ --force    # custom dir + force
"""

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.ingestion.pdf_parser import extract_pdf
from app.ingestion.chunker import chunk_pages
from app.ingestion.embedder import store_chunks, collection_count, get_indexed_files

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ingest")

PROGRESS_FILE = settings.chroma_dir / ".ingest_progress.json"


def load_progress() -> set[str]:
    """Load set of filenames from progress tracker."""
    if PROGRESS_FILE.exists():
        try:
            return set(json.loads(PROGRESS_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_progress(processed: set[str]) -> None:
    """Persist processed filenames to disk."""
    PROGRESS_FILE.write_text(
        json.dumps(sorted(processed), ensure_ascii=False), encoding="utf-8"
    )


def _parse_single_pdf(pdf_path: str) -> tuple[str, list | None]:
    """Worker function for multiprocessing PDF extraction."""
    from app.ingestion.pdf_parser import extract_pdf as _extract
    path = Path(pdf_path)
    try:
        pages = _extract(path)
        return (path.name, pages)
    except (RuntimeError, FileNotFoundError) as exc:
        return (path.name, None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDFs into ChromaDB")
    parser.add_argument("pdf_dir", nargs="?", default=None, help="PDF directory")
    parser.add_argument("--force", action="store_true", help="Re-ingest all files")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else settings.pdf_dir
    if not pdf_dir.exists():
        logger.error("Directory not found: %s", pdf_dir)
        sys.exit(1)

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        logger.error("No PDF files in '%s'.", pdf_dir)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("RAG KKSON — Ingestion Pipeline (optimized)")
    logger.info("PDF directory: %s (%d files)", pdf_dir, len(pdf_files))
    logger.info("ChromaDB path: %s", settings.chroma_dir)
    logger.info("Batch size: %d | Force: %s", settings.embed_batch_size, args.force)
    logger.info("=" * 60)

    t0 = time.time()

    # Determine which files to skip
    if args.force:
        PROGRESS_FILE.unlink(missing_ok=True)
        skip_files: set[str] = set()
    else:
        indexed = get_indexed_files()
        progress = load_progress()
        skip_files = indexed | progress

    to_process = [f for f in pdf_files if f.name not in skip_files]
    skipped = len(pdf_files) - len(to_process)

    if skipped:
        logger.info("⏭ Skipped %d already indexed files.", skipped)

    if not to_process:
        logger.info("✅ Nothing to ingest. All %d files already indexed.", len(pdf_files))
        logger.info("   Total in DB: %d chunks", collection_count())
        return

    logger.info("📄 Processing %d new files…", len(to_process))

    # Parallel PDF parsing
    workers = min(cpu_count() or 1, 4, len(to_process))
    parsed: dict[str, list] = {}
    failed = 0

    logger.info("🔄 Parsing PDFs with %d workers…", workers)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = pool.map(_parse_single_pdf, [str(f) for f in to_process])
        for name, pages in results:
            if pages is None:
                logger.error("  ✗ %s — parse failed", name)
                failed += 1
            elif not pages:
                logger.warning("  ⚠ %s — no text extracted", name)
                failed += 1
            else:
                parsed[name] = pages
                logger.info("  ✓ %s — %d pages", name, len(pages))

    # Per-file: chunk → embed → store → free
    processed = load_progress() if not args.force else set()
    total_pages = 0
    total_chunks = 0
    total_stored = 0

    for i, (name, pages) in enumerate(parsed.items(), 1):
        file_t0 = time.time()

        chunks = chunk_pages(pages)
        if not chunks:
            logger.warning("  ⚠ %s — 0 chunks, skipping", name)
            continue

        stored = store_chunks(chunks)

        total_pages += len(pages)
        total_chunks += len(chunks)
        total_stored += stored

        processed.add(name)
        save_progress(processed)

        elapsed_file = time.time() - file_t0
        logger.info(
            "  [%d/%d] %s — %d pages, %d chunks, %.1fs",
            i, len(parsed), name, len(pages), len(chunks), elapsed_file,
        )

    elapsed = time.time() - t0
    logger.info("\n" + "=" * 60)
    logger.info("✅ Ingestion complete!")
    logger.info("   Files processed: %d (skipped: %d, failed: %d)", len(parsed), skipped, failed)
    logger.info("   Pages extracted: %d", total_pages)
    logger.info("   Chunks created:  %d", total_chunks)
    logger.info("   Chunks stored:   %d", total_stored)
    logger.info("   Total in DB:     %d", collection_count())
    logger.info("   Time elapsed:    %.1f seconds", elapsed)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
