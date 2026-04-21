# TODO: add auth before production
"""Admin panel — PDF upload, document listing, and delete.

Exposes a small router that is mounted into the main FastAPI app. Uploads are
processed through the existing ingestion pipeline (parse → chunk → embed →
Chroma upsert) in the background, with per-file progress streamed over SSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import Counter
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, settings
from app.ingestion.chunker import chunk_pages
from app.ingestion.embedder import get_collection, store_chunks
from app.ingestion.pdf_parser import extract_pdf

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

UPLOADS_DIR = settings.pdf_dir / "uploads"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXT = ".pdf"

# In-memory progress fan-out. One queue per active job.
JOBS: dict[str, asyncio.Queue] = {}


# ── Pages ──────────────────────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("admin.html", {"request": request})


# ── Upload + progress ──────────────────────────────────────────────────────

@router.post("/admin/upload")
async def admin_upload(files: list[UploadFile] = File(...)) -> JSONResponse:
    """Accept PDFs, save to uploads dir, kick off background processing.

    Returns a job_id; connect to /admin/progress/{job_id} for live updates.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    errors: list[dict] = []

    for upload in files:
        name = (upload.filename or "").strip()
        if not name.lower().endswith(ALLOWED_EXT):
            errors.append({"file": name, "reason": "not a .pdf file"})
            continue

        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            errors.append({"file": name, "reason": f"exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MB"})
            continue
        if len(data) == 0:
            errors.append({"file": name, "reason": "empty file"})
            continue

        dest = UPLOADS_DIR / Path(name).name  # strip any path components
        dest.write_bytes(data)
        saved.append(dest)

    if not saved:
        raise HTTPException(status_code=400, detail={"errors": errors})

    job_id = uuid.uuid4().hex
    JOBS[job_id] = asyncio.Queue()
    asyncio.create_task(_process_job(job_id, saved))

    return JSONResponse({
        "job_id": job_id,
        "files": [p.name for p in saved],
        "rejected": errors,
    })


@router.get("/admin/progress/{job_id}")
async def admin_progress(job_id: str) -> StreamingResponse:
    """SSE stream of per-file progress events. Closes when the job finishes."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Unknown job.")

    async def stream() -> AsyncIterator[str]:
        queue = JOBS[job_id]
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: [DONE]\n\n"
        finally:
            JOBS.pop(job_id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _process_job(job_id: str, files: list[Path]) -> None:
    """Run all files through the ingestion pipeline, emit progress events."""
    queue = JOBS[job_id]
    total = len(files)
    try:
        for idx, path in enumerate(files, 1):
            await _process_one(path, queue, idx, total)
    except Exception:
        logger.exception("Job %s crashed.", job_id)
    finally:
        await queue.put(None)  # sentinel: stream end


async def _process_one(path: Path, queue: asyncio.Queue, idx: int, total: int) -> None:
    name = path.name

    async def emit(stage: str, detail: str = "") -> None:
        await queue.put({
            "file": name,
            "stage": stage,
            "current": idx,
            "total": total,
            "detail": detail,
        })

    try:
        await emit("parsing")
        pages = await asyncio.to_thread(extract_pdf, path)
        if not pages:
            await emit("error", "не удалось извлечь текст (возможно, скан)")
            return

        await emit("chunking", f"{len(pages)} стр.")
        chunks = await asyncio.to_thread(chunk_pages, pages)
        if not chunks:
            await emit("error", "не получилось сформировать чанки")
            return

        await emit("embedding", f"{len(chunks)} чанков")
        stored = await asyncio.to_thread(store_chunks, chunks)

        await emit("storing", f"upsert {stored}")
        await asyncio.sleep(0.05)  # brief pause so UI can render the transition

        await emit("done", f"{stored} чанков сохранено")
    except Exception as exc:
        logger.exception("Ingestion failed for %s", name)
        await emit("error", str(exc))


# ── Documents listing + delete ─────────────────────────────────────────────

@router.get("/admin/documents")
async def admin_documents(q: str = "") -> JSONResponse:
    """List ingested documents with chunk counts, filtered by substring on source_file."""
    collection = get_collection()
    if collection.count() == 0:
        return JSONResponse([])

    result = collection.get(include=["metadatas"])
    metas = result.get("metadatas") or []

    counts: Counter[str] = Counter()
    for m in metas:
        sf = m.get("source_file") if m else None
        if sf:
            counts[sf] += 1

    needle = q.strip().lower()
    rows = [
        {"source_file": sf, "chunk_count": n}
        for sf, n in counts.items()
        if not needle or needle in sf.lower()
    ]
    rows.sort(key=lambda r: r["source_file"].lower())
    return JSONResponse(rows)


@router.get("/admin/download/{source_file:path}")
async def admin_download(source_file: str) -> FileResponse:
    """Serve a stored PDF for download. Checks both the main PDF dir and the uploads dir."""
    safe_name = Path(source_file).name  # strip any path components (traversal safety)
    for candidate in (settings.pdf_dir / safe_name, UPLOADS_DIR / safe_name):
        if candidate.is_file():
            return FileResponse(
                path=str(candidate),
                filename=safe_name,
                media_type="application/pdf",
            )
    raise HTTPException(status_code=404, detail="Файл не найден на диске.")


@router.delete("/admin/documents/{source_file:path}")
async def admin_delete_document(source_file: str) -> JSONResponse:
    """Delete all chunks belonging to a given source_file."""
    collection = get_collection()
    before = collection.get(where={"source_file": source_file}, include=[])
    ids = before.get("ids") or []
    if not ids:
        raise HTTPException(status_code=404, detail="Document not found.")

    collection.delete(where={"source_file": source_file})
    return JSONResponse({"deleted": len(ids), "source_file": source_file})
