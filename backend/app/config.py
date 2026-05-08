from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database - Vercel에서는 환경변수로 자동 주입됨
    DATABASE_URL: str = "sqlite+aiosqlite:///./doc_replacer.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # 국가법령정보 Open API
    LAW_API_KEY: str = ""

    # File upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB

    # App
    DEBUG: bool = False

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @property
    def async_database_url(self) -> str:
        """DATABASE_URL을 async 드라이버로 변환."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url  # sqlite는 그대로


settings = Settings()
