"""PDFtoDeck backend configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Icon extraction
DEFAULT_ICON_THRESHOLD = float(os.getenv("DEFAULT_ICON_THRESHOLD", "0.05"))
ICON_NODE_LIMIT = int(os.getenv("ICON_NODE_LIMIT", "50"))

# File cleanup
FILE_TTL_SECONDS = int(os.getenv("FILE_TTL_SECONDS", "3600"))

# Concurrency
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "3"))

# ─── Tier Limits ───

TIERS = {
    "guest": {
        "daily_converts": 1,
        "max_pages": 5,
        "max_file_size_mb": 10,
        "history_days": 0,
    },
    "free": {
        "daily_converts": 5,
        "max_pages": 20,
        "max_file_size_mb": 50,
        "history_days": 7,
    },
    "paid": {
        "daily_converts": 999999,  # unlimited
        "max_pages": 200,
        "max_file_size_mb": 200,
        "history_days": 30,
    },
}

# ─── Credit Packages ───

CREDIT_PACKAGES = {
    "starter": {"credits": 5, "price_cents": 199, "label": "Starter"},
    "standard": {"credits": 30, "price_cents": 499, "label": "Standard"},
    "pro": {"credits": 100, "price_cents": 999, "label": "Pro"},
}

# Legacy compat
MAX_FILE_SIZE_MB = 200
MAX_PAGES_FREE = 200

# ─── PayPal Configuration ───

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox or live
PAYPAL_BASE_URL = (
    "https://api-m.sandbox.paypal.com"
    if PAYPAL_MODE == "sandbox"
    else "https://api-m.paypal.com"
)
