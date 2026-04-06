"""FastAPI application — RAG search over KKSON journal articles."""

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings, BASE_DIR
from app.ingestion.embedder import collection_count
from app.retrieval.search import hybrid_search, SearchResult
from app.retrieval.reranker import rerank
from app.generation.answerer import stream_answer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="RAG KKSON", description="Поиск по научным журналам ККСОН")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the main search page."""
    count = collection_count()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "doc_count": count},
    )


@app.get("/api/search")
async def api_search(q: str, keyword: str = "") -> dict:
    """Search endpoint — returns matching chunks as JSON."""
    if not q.strip():
        return {"results": [], "query": q}

    results = hybrid_search(query=q, keyword=keyword or None)
    if settings.reranker_enabled:
        results = rerank(query=q, results=results)
    return {
        "query": q,
        "results": [
            {
                "text": r.text[:500],
                "source_file": r.source_file,
                "page_number": r.page_number,
                "score": r.score,
                "citation": r.citation,
            }
            for r in results
        ],
    }


@app.get("/api/answer")
async def api_answer(q: str, keyword: str = "") -> StreamingResponse:
    """Streaming answer endpoint for HTMX SSE.

    Returns Server-Sent Events with the generated text.
    """
    results = hybrid_search(query=q, keyword=keyword or None)
    if settings.reranker_enabled:
        results = rerank(query=q, results=results)

    def event_stream():
        # First send sources as a JSON event
        sources = _unique_sources(results)
        yield f"event: sources\ndata: {json.dumps(sources, ensure_ascii=False)}\n\n"

        # Then stream the answer text
        try:
            for chunk in stream_answer(question=q, results=results):
                # SSE format: replace newlines for safe transport
                safe = chunk.replace("\n", "\ndata: ")
                yield f"data: {safe}\n\n"
        except Exception as exc:
            logger.error("Streaming error: %s", exc)
            yield f"event: error\ndata: Ошибка генерации: {exc}\n\n"

        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/stats")
async def api_stats() -> dict:
    """Return collection statistics."""
    return {"total_chunks": collection_count()}


def _unique_sources(results: list[SearchResult]) -> list[dict]:
    """Deduplicate sources for display."""
    seen = set()
    sources = []
    for r in results:
        key = (r.source_file, r.page_number)
        if key not in seen:
            seen.add(key)
            sources.append({
                "file": r.source_file,
                "page": r.page_number,
                "score": r.score,
                "text": r.text[:300],
                "citation": r.citation,
            })
    return sources
