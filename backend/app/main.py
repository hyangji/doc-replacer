import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
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

try:
    from app.routers import documents_router, law_router, spellcheck_router
    app.include_router(documents_router)
    app.include_router(law_router)
    app.include_router(spellcheck_router)
except Exception:
    pass


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "doc-replacer"}
