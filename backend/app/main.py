"""PDFtoDeck API server."""

import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import (
    UPLOAD_DIR, OUTPUT_DIR,
    MAX_FILE_SIZE_MB, MAX_PAGES_FREE,
    MAX_CONCURRENT_TASKS, DEFAULT_ICON_THRESHOLD,
)
from .converter import parse_pdf, build_pptx

app = FastAPI(title="PDFtoDeck", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory task store (replace with Redis in production)
tasks: dict[str, dict] = {}
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)


class ConvertRequest(BaseModel):
    task_id: str
    icon_threshold: float = DEFAULT_ICON_THRESHOLD


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload a PDF file for conversion."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(413, f"File too large. Max {MAX_FILE_SIZE_MB}MB")

    task_id = str(uuid.uuid4())[:8]
    pdf_path = UPLOAD_DIR / f"{task_id}.pdf"
    pdf_path.write_bytes(content)

    # Quick page count check
    import fitz
    doc = fitz.open(str(pdf_path))
    page_count = len(doc)
    doc.close()

    if page_count > MAX_PAGES_FREE:
        pdf_path.unlink(missing_ok=True)
        raise HTTPException(
            413, f"Free tier limited to {MAX_PAGES_FREE} pages. "
                 f"This file has {page_count} pages."
        )

    tasks[task_id] = {
        "status": "uploaded",
        "progress": 0,
        "pages": page_count,
        "size_mb": round(size_mb, 2),
        "pdf_path": str(pdf_path),
        "original_filename": file.filename or "",
    }

    return {"task_id": task_id, "pages": page_count, "size_mb": round(size_mb, 2)}


@app.post("/api/convert")
async def convert(req: ConvertRequest):
    """Start PDF → PPTX conversion."""
    task = tasks.get(req.task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task["status"] == "processing":
        raise HTTPException(409, "Already processing")

    task["status"] = "processing"
    task["progress"] = 0

    # Run conversion in background
    asyncio.create_task(_do_convert(req.task_id, req.icon_threshold))
    return {"status": "processing"}


async def _do_convert(task_id: str, icon_threshold: float):
    """Background conversion task."""
    async with semaphore:
        task = tasks[task_id]
        try:
            pdf_path = task["pdf_path"]
            output_path = str(OUTPUT_DIR / f"{task_id}.pptx")

            # Run CPU-bound work in thread pool
            loop = asyncio.get_event_loop()
            pages = await loop.run_in_executor(
                None, parse_pdf, pdf_path, icon_threshold,
            )

            task["progress"] = 50

            await loop.run_in_executor(
                None, build_pptx, pages, output_path,
                task.get("original_filename", ""),
                pdf_path,
            )

            task["status"] = "done"
            task["progress"] = 100
            task["output_path"] = output_path

        except Exception as e:
            task["status"] = "error"
            task["error"] = str(e)


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """Check conversion progress."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {
        "status": task["status"],
        "progress": task.get("progress", 0),
        "pages": task.get("pages", 0),
        "error": task.get("error"),
    }


@app.get("/api/download/{task_id}")
async def download(task_id: str):
    """Download converted PPTX file."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task["status"] != "done":
        raise HTTPException(400, f"Task status: {task['status']}")

    output_path = task.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(404, "Output file not found")

    # Build download filename from original PDF name
    original = task.get("original_filename", "")
    if original.lower().endswith(".pdf"):
        download_name = original[:-4] + ".pptx"
    else:
        download_name = f"PDFtoDeck-{task_id}.pptx"

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=download_name,
    )
