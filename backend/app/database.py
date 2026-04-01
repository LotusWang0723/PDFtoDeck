"""Database module for PDFtoDeck user system."""

import uuid
import aiosqlite
from pathlib import Path
from datetime import datetime, date, timedelta

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "pdftodeck.db"
DB_PATH.parent.mkdir(exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    avatar_url TEXT,
    provider TEXT DEFAULT 'google',
    provider_id TEXT,
    credits INTEGER DEFAULT 0,
    daily_free_used INTEGER DEFAULT 0,
    daily_free_reset_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    guest_token TEXT,
    filename TEXT,
    pages INTEGER,
    status TEXT DEFAULT 'pending',
    download_url TEXT,
    cost_credits INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS credit_orders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    package TEXT,
    credits INTEGER,
    amount_cents INTEGER,
    payment_method TEXT,
    payment_id TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        await db.commit()
    finally:
        await db.close()


# ─── User Operations ───

async def sync_user(email: str, name: str = None, avatar_url: str = None,
                    provider: str = "google", provider_id: str = None) -> dict:
    """Create or update user from OAuth login."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = await cursor.fetchone()

        if user:
            await db.execute(
                "UPDATE users SET name=?, avatar_url=?, updated_at=? WHERE email=?",
                (name or user["name"], avatar_url or user["avatar_url"],
                 datetime.utcnow().isoformat(), email)
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
            user = await cursor.fetchone()
        else:
            user_id = str(uuid.uuid4())[:12]
            await db.execute(
                """INSERT INTO users (id, email, name, avatar_url, provider, provider_id,
                   credits, daily_free_used, daily_free_reset_at)
                   VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)""",
                (user_id, email, name, avatar_url, provider, provider_id,
                 date.today().isoformat())
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
            user = await cursor.fetchone()

        return dict(user)
    finally:
        await db.close()


async def get_user(email: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = await cursor.fetchone()
        return dict(user) if user else None
    finally:
        await db.close()


async def reset_daily_free_if_needed(email: str):
    """Reset daily free count if it's a new day."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT daily_free_reset_at FROM users WHERE email = ?", (email,))
        row = await cursor.fetchone()
        if row and row["daily_free_reset_at"] != date.today().isoformat():
            await db.execute(
                "UPDATE users SET daily_free_used=0, daily_free_reset_at=? WHERE email=?",
                (date.today().isoformat(), email)
            )
            await db.commit()
    finally:
        await db.close()


async def increment_daily_free(email: str):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET daily_free_used = daily_free_used + 1 WHERE email = ?",
            (email,)
        )
        await db.commit()
    finally:
        await db.close()


async def deduct_credit(email: str) -> bool:
    """Deduct 1 credit. Returns True if successful."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT credits FROM users WHERE email = ?", (email,))
        row = await cursor.fetchone()
        if not row or row["credits"] <= 0:
            return False
        await db.execute(
            "UPDATE users SET credits = credits - 1 WHERE email = ?",
            (email,)
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def add_credits(email: str, amount: int):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET credits = credits + ? WHERE email = ?",
            (amount, email)
        )
        await db.commit()
    finally:
        await db.close()


# ─── Conversion Operations ───

async def create_conversion(user_id: str = None, guest_token: str = None,
                            filename: str = "", pages: int = 0,
                            cost_credits: int = 0, expires_days: int = 7) -> str:
    conv_id = str(uuid.uuid4())[:8]
    expires_at = (datetime.utcnow() + timedelta(days=expires_days)).isoformat()
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO conversions (id, user_id, guest_token, filename, pages,
               status, cost_credits, expires_at) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (conv_id, user_id, guest_token, filename, pages, cost_credits, expires_at)
        )
        await db.commit()
        return conv_id
    finally:
        await db.close()


async def update_conversion_status(conv_id: str, status: str, download_url: str = None):
    db = await get_db()
    try:
        if download_url:
            await db.execute(
                "UPDATE conversions SET status=?, download_url=? WHERE id=?",
                (status, download_url, conv_id)
            )
        else:
            await db.execute(
                "UPDATE conversions SET status=? WHERE id=?",
                (status, conv_id)
            )
        await db.commit()
    finally:
        await db.close()


async def get_user_history(email: str, limit: int = 50) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT c.* FROM conversions c
               JOIN users u ON c.user_id = u.id
               WHERE u.email = ?
               ORDER BY c.created_at DESC LIMIT ?""",
            (email, limit)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_user_stats(email: str) -> dict:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT
                 COUNT(*) as total_conversions,
                 COALESCE(SUM(pages), 0) as total_pages
               FROM conversions c
               JOIN users u ON c.user_id = u.id
               WHERE u.email = ? AND c.status = 'done'""",
            (email,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else {"total_conversions": 0, "total_pages": 0}
    finally:
        await db.close()


# ─── Guest tracking ───

_guest_daily: dict[str, dict] = {}  # ip -> {"date": "2026-01-01", "count": 1}


def check_guest_limit(ip: str) -> bool:
    """Check if guest IP has exceeded daily limit (1/day)."""
    today = date.today().isoformat()
    entry = _guest_daily.get(ip)
    if not entry or entry["date"] != today:
        return True  # allowed
    return entry["count"] < 1


def record_guest_use(ip: str):
    today = date.today().isoformat()
    entry = _guest_daily.get(ip)
    if not entry or entry["date"] != today:
        _guest_daily[ip] = {"date": today, "count": 1}
    else:
        entry["count"] += 1


# ─── Credit Orders ───

async def create_credit_order(user_id: str, package: str,
                              credits: int, amount_cents: int) -> str:
    order_id = str(uuid.uuid4())[:12]
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO credit_orders (id, user_id, package, credits, amount_cents, status)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (order_id, user_id, package, credits, amount_cents)
        )
        await db.commit()
        return order_id
    finally:
        await db.close()


async def get_credit_order(order_id: str) -> dict | None:
    """Get a credit order by ID."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM credit_orders WHERE id = ?", (order_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def update_credit_order(order_id: str, status: str = None,
                               payment_method: str = None,
                               payment_id: str = None):
    """Update credit order fields."""
    db = await get_db()
    try:
        updates = []
        params = []
        if status:
            updates.append("status = ?")
            params.append(status)
        if payment_method:
            updates.append("payment_method = ?")
            params.append(payment_method)
        if payment_id:
            updates.append("payment_id = ?")
            params.append(payment_id)

        if not updates:
            return

        params.append(order_id)
        await db.execute(
            f"UPDATE credit_orders SET {', '.join(updates)} WHERE id = ?",
            tuple(params)
        )
        await db.commit()
    finally:
        await db.close()
