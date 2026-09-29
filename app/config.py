import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Client PDF Unlocker"
    APP_ENV: str = "production"
    DEBUG: bool = False

    # Security & Session
    SECRET_KEY: str = "default-insecure-secret-key-change-in-production-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # File Upload & Processing limits
    MAX_FILE_SIZE_MB: int = 50
    MAX_FILES_PER_JOB: int = 500
    WORKER_COUNT: int = max(2, (os.cpu_count() or 2))
    RETENTION_MINUTES: int = 30
    TEMP_DIR: str = "temp_jobs"

    # Database
    DATABASE_URL: str = "sqlite:///./data/pdf_unlocker.db"

    # Rate Limiting
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_UNLOCK: str = "20/minute"

    # Default Users
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "Admin@12345"
    DEFAULT_STAFF_USERNAME: str = "staff"
    DEFAULT_STAFF_PASSWORD: str = "Staff@12345"

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


@lru_cache()
def get_settings() -> Settings:
    return Settings()
