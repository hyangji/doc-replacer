from app.routers.documents import router as documents_router
from app.routers.law import router as law_router
from app.routers.spellcheck import router as spellcheck_router

__all__ = ["documents_router", "law_router", "spellcheck_router"]
