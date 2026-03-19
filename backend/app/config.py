"""PDFtoDeck backend configuration."""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Limits
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
MAX_PAGES_FREE = int(os.getenv("MAX_PAGES_FREE", "10"))
MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "3"))

# Icon extraction
DEFAULT_ICON_THRESHOLD = float(os.getenv("DEFAULT_ICON_THRESHOLD", "0.05"))
ICON_NODE_LIMIT = int(os.getenv("ICON_NODE_LIMIT", "50"))

# File cleanup
FILE_TTL_SECONDS = int(os.getenv("FILE_TTL_SECONDS", "3600"))
