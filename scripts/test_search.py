#!/usr/bin/env python3
"""Quick test: search the ChromaDB collection and print results.

Usage:
    python -m scripts.test_search "ваш вопрос здесь"
    python -m scripts.test_search "machine learning in medicine"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.embedder import collection_count
from app.retrieval.search import semantic_search


def main() -> None:
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "методы машинного обучения"

    count = collection_count()
    print(f"\n📊 Collection has {count} chunks.\n")

    if count == 0:
        print("⚠️  Collection is empty. Run ingestion first:")
        print("   python -m scripts.ingest")
        return

    print(f"🔍 Searching for: «{query}»\n")
    results = semantic_search(query, top_k=5)

    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results, 1):
        print(f"--- Result {i} (score: {r.score:.4f}) ---")
        print(f"Source: {r.citation}")
        print(f"Text:   {r.text[:300]}…\n")


if __name__ == "__main__":
    main()
