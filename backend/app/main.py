import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # UPLOAD_DIR은 로컬 개발 시에만 필요 (DB 바이너리 저장 모드에서는 불필요)
    try:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    except OSError:
        pass  # Vercel 등 읽기전용 파일시스템에서는 무시
    try:
        from app.database import engine
        from app.models.document import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        pass
    yield


app = FastAPI(
    title="DocReplacer API",
    description="도시계획 제안서 문서 관리 시스템",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import documents_router

app.include_router(documents_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "doc-replacer"}
