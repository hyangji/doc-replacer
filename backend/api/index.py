import sys
import os

# Vercel 환경변수로 DATABASE_URL이 자동 주입됨 (Neon Postgres)
# 로컬 개발 시에는 .env 파일에서 읽음

# Add parent directory to path so 'app' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402, F401
