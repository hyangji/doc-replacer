from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

_tables_created = False


async def ensure_tables() -> None:
    """Create all tables if they don't exist yet (idempotent)."""
    global _tables_created
    if _tables_created:
        return
    from app.models.document import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _tables_created = True


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    await ensure_tables()
    async with async_session_factory() as session:
        yield session
