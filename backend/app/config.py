from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database - Vercel에서는 환경변수로 자동 주입됨
    DATABASE_URL: str = "sqlite+aiosqlite:///./doc_replacer.db"

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
        if url.startswith("postgresql://") or url.startswith("postgres://"):
            # asyncpg 드라이버로 변경
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            else:
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            # asyncpg가 지원하지 않는 URL 파라미터 제거
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            # channel_binding, sslmode 등 asyncpg 비호환 파라미터 제거
            for key in ["channel_binding", "sslmode"]:
                params.pop(key, None)
            clean_query = urlencode(params, doseq=True)
            url = urlunparse(parsed._replace(query=clean_query))
            return url
        return url  # sqlite는 그대로


settings = Settings()
