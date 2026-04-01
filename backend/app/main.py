"""PDFtoDeck API server."""

import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from .config import (
    UPLOAD_DIR, OUTPUT_DIR,
    MAX_CONCURRENT_TASKS, DEFAULT_ICON_THRESHOLD,
    TIERS, CREDIT_PACKAGES,
)
from .converter import parse_pdf, build_pptx
from . import database as db
from .paypal import router as paypal_router

app = FastAPI(title="PDFtoDeck", version="0.3.0")
app.include_router(paypal_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register PayPal routes
app.include_router(paypal_router)


@app.on_event("startup")
async def startup():
    await db.init_db()


# ─── Priority queues ───
free_semaphore = asyncio.Semaphore(1)      # free/guest: 1 concurrent
paid_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)  # paid: full concurrency

# In-memory task store
tasks: dict[str, dict] = {}


# ─── Models ───

class ConvertRequest(BaseModel):
    task_id: str
    icon_threshold: float = DEFAULT_ICON_THRESHOLD


class UserSyncRequest(BaseModel):
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    provider: str = "google"
    provider_id: Optional[str] = None


# ─── Helper: determine user tier ───

async def get_user_tier(email: str | None) -> tuple[str, dict | None]:
    """Returns (tier_name, user_dict_or_None)."""
    if not email:
        return "guest", None

    user = await db.get_user(email)
    if not user:
        return "guest", None

    await db.reset_daily_free_if_needed(email)
    user = await db.get_user(email)  # refresh

    if user["credits"] > 0:
        return "paid", user
    return "free", user


# ─── Health ───

@app.get("/health")
async def health():
    return {"status": "ok"}


# ─── User APIs ───

@app.post("/api/user/sync")
async def user_sync(req: UserSyncRequest):
    """Sync user from NextAuth session."""
    user = await db.sync_user(
        email=req.email,
        name=req.name,
        avatar_url=req.avatar_url,
        provider=req.provider,
        provider_id=req.provider_id,
    )
    return user


@app.get("/api/user/me")
async def user_me(email: str):
    """Get user profile + stats."""
    user = await db.get_user(email)
    if not user:
        raise HTTPException(404, "User not found")

    await db.reset_daily_free_if_needed(email)
    user = await db.get_user(email)

    stats = await db.get_user_stats(email)
    tier_name = "paid" if user["credits"] > 0 else "free"
    tier_limits = TIERS[tier_name]

    return {
        **user,
        "tier": tier_name,
        "limits": tier_limits,
        "stats": stats,
        "daily_free_remaining": max(0, TIERS["free"]["daily_converts"] - user["daily_free_used"]),
    }


@app.get("/api/user/history")
async def user_history(email: str, limit: int = 50):
    """Get conversion history."""
    user = await db.get_user(email)
    if not user:
        raise HTTPException(404, "User not found")
    history = await db.get_user_history(email, limit)
    return {"history": history}


@app.get("/api/user/credits")
async def user_credits(email: str):
    """Get credit balance."""
    user = await db.get_user(email)
    if not user:
        raise HTTPException(404, "User not found")
    return {
        "credits": user["credits"],
        "daily_free_used": user["daily_free_used"],
        "daily_free_remaining": max(0, TIERS["free"]["daily_converts"] - user["daily_free_used"]),
    }


@app.get("/api/packages")
async def get_packages():
    """Get available credit packages."""
    return {"packages": CREDIT_PACKAGES}


# ─── Upload ───

@app.post("/api/upload")
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    """Upload a PDF file for conversion."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    # Step 1: Accept upload unconditionally
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)

    task_id = str(uuid.uuid4())[:8]
    pdf_path = UPLOAD_DIR / f"{task_id}.pdf"
    pdf_path.write_bytes(content)

    import fitz
    doc = fitz.open(str(pdf_path))
    page_count = len(doc)
    doc.close()

    # Step 2: Determine user tier after upload
    email = request.headers.get("X-User-Email")
    tier_name, user = await get_user_tier(email)

    # Determine limits based on user state
    if user and user["credits"] > 0:
        # Logged in + has credits → paid limits
        tier_name = "paid"
        max_pages = 200
        max_size_mb = 200
    elif user:
        # Logged in + no credits → free limits
        tier_name = "free"
        max_pages = 20
        max_size_mb = 50
    else:
        # Not logged in → guest limits
        tier_name = "guest"
        max_pages = 5
        max_size_mb = 10

    # Step 3: Validate against limits
    if size_mb > max_size_mb:
        pdf_path.unlink(missing_ok=True)
        if tier_name == "guest":
            hint = " Sign in for higher limits."
        elif tier_name == "free":
            hint = " Purchase credits for higher limits."
        else:
            hint = ""
        raise HTTPException(
            413,
            f"File too large ({size_mb:.1f}MB). Max {max_size_mb}MB for {tier_name} tier.{hint}"
        )

    if page_count > max_pages:
        pdf_path.unlink(missing_ok=True)
        if tier_name == "guest":
            hint = " Sign in for higher limits."
        elif tier_name == "free":
            hint = " Purchase credits for higher limits."
        else:
            hint = ""
        raise HTTPException(
            413,
            f"Too many pages ({page_count}). Max {max_pages} pages for {tier_name} tier.{hint}"
        )

    # Step 4: Check daily limits (guest/free only)
    cost_credits = 0
    if tier_name == "paid":
        cost_credits = 1
    elif tier_name == "guest":
        client_ip = request.client.host if request.client else "unknown"
        if not db.check_guest_limit(client_ip):
            pdf_path.unlink(missing_ok=True)
            raise HTTPException(
                429,
                "Guest limit reached (1 conversion per day). Sign in for 5 free daily conversions."
            )
    elif tier_name == "free":
        if user["daily_free_used"] >= TIERS["free"]["daily_converts"]:
            pdf_path.unlink(missing_ok=True)
            raise HTTPException(
                429,
                "Daily free limit reached (5/day). Purchase credits for unlimited conversions."
            )

    # Step 5: Record conversion
    tier = TIERS[tier_name]
    expires_days = tier["history_days"] if tier["history_days"] > 0 else 1
    conv_id = await db.create_conversion(
        user_id=user["id"] if user else None,
        guest_token=request.client.host if tier_name == "guest" else None,
        filename=file.filename or "",
        pages=page_count,
        cost_credits=cost_credits,
        expires_days=expires_days,
    )

    tasks[task_id] = {
        "status": "uploaded",
        "progress": 0,
        "pages": page_count,
        "size_mb": round(size_mb, 2),
        "pdf_path": str(pdf_path),
        "original_filename": file.filename or "",
        "tier": tier_name,
        "user_email": email,
        "cost_credits": cost_credits,
        "conv_id": conv_id,
    }

    return {
        "task_id": task_id,
        "pages": page_count,
        "size_mb": round(size_mb, 2),
        "tier": tier_name,
    }


# ─── Convert ───

@app.post("/api/convert")
async def convert(req: ConvertRequest):
    """Start PDF → PPTX conversion."""
    task = tasks.get(req.task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task["status"] == "processing":
        raise HTTPException(409, "Already processing")

    # Check credits availability (but don't deduct yet)
    email = task.get("user_email")
    cost = task.get("cost_credits", 0)

    if cost > 0 and email:
        user = await db.get_user(email)
        if not user or user["credits"] <= 0:
            raise HTTPException(402, "Insufficient credits")

    # Track guest usage
    tier = task.get("tier", "guest")
    if tier == "guest":
        guest_ip = task.get("user_email") or "unknown"
        db.record_guest_use(guest_ip)
    elif tier == "free" and cost == 0 and email:
        await db.increment_daily_free(email)

    task["status"] = "processing"
    task["progress"] = 0

    # Priority: paid users use paid_semaphore (more slots), free/guest use free_semaphore
    sem = paid_semaphore if tier == "paid" else free_semaphore
    asyncio.create_task(_do_convert(req.task_id, req.icon_threshold, sem))
    return {"status": "processing"}


async def _do_convert(task_id: str, icon_threshold: float, sem: asyncio.Semaphore):
    """Background conversion task with priority queuing."""
    async with sem:
        task = tasks[task_id]
        conv_id = task.get("conv_id")
        try:
            pdf_path = task["pdf_path"]
            output_path = str(OUTPUT_DIR / f"{task_id}.pptx")

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

            # Deduct credits only after successful conversion
            email = task.get("user_email")
            cost = task.get("cost_credits", 0)
            if cost > 0 and email:
                await db.deduct_credit(email)

            if conv_id:
                await db.update_conversion_status(
                    conv_id, "done",
                    download_url=f"/api/download/{task_id}"
                )

        except Exception as e:
            task["status"] = "error"
            task["error"] = str(e)
            if conv_id:
                await db.update_conversion_status(conv_id, "error")


# ─── Status & Download ───

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
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
    # Try memory first
    task = tasks.get(task_id)
    if task and task["status"] == "done":
        output_path = task.get("output_path")
        original = task.get("original_filename", "")
    else:
        # Fallback: check if file exists on disk
        output_path = str(OUTPUT_DIR / f"{task_id}.pptx")
        if not Path(output_path).exists():
            raise HTTPException(404, "File not found")
        original = f"{task_id}.pptx"

    if not Path(output_path).exists():
        raise HTTPException(404, "Output file not found")

    if original.lower().endswith(".pdf"):
        download_name = original[:-4] + ".pptx"
    else:
        download_name = f"PDFtoDeck-{task_id}.pptx"

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=download_name,
    )
