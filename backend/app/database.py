from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# PostgreSQL은 SSL 관련 파라미터가 URL에 포함됨, SQLite는 check_same_thread 필요
_is_sqlite = settings.async_database_url.startswith("sqlite")

_connect_args: dict = {}
if _is_sqlite:
    _connect_args = {"check_same_thread": False}
elif "neon.tech" in settings.async_database_url:
    # Neon Postgres는 SSL 필수
    import ssl
    _ssl_ctx = ssl.create_default_context()
    _connect_args = {"ssl": _ssl_ctx}

engine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG,
    connect_args=_connect_args,
)

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
