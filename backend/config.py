import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Read .env if present
env_file = BASE_DIR / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://localhost:8000")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "finances.db")
UPLOAD_DIR = BASE_DIR / "uploads" / "receipts"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
