import sys
import os

# Vercel serverless: set env for SQLite in /tmp
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/doc_replacer.db")
os.environ.setdefault("UPLOAD_DIR", "/tmp/uploads")

# Add parent directory to path so 'app' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402, F401
