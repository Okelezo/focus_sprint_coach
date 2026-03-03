from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Focus Sprint Coach", alias="APP_NAME")
    environment: str = Field(default="local", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/focus_sprint_coach",
        alias="DATABASE_URL",
    )

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        url = (v or "").strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]

        # Ensure async SQLAlchemy URL.
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]
        return url

    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60 * 24, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")

    ai_strict: bool = Field(default=False, alias="AI_STRICT")

    posthog_api_key: str | None = Field(default=None, alias="POSTHOG_API_KEY")
    posthog_host: str | None = Field(default=None, alias="POSTHOG_HOST")

    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")

    git_sha: str | None = Field(default=None, alias="GIT_SHA")
    railway_git_commit_sha: str | None = Field(default=None, alias="RAILWAY_GIT_COMMIT_SHA")
    build_time: str | None = Field(default=None, alias="BUILD_TIME")

    cors_allow_origins: str | None = Field(default=None, alias="CORS_ALLOW_ORIGINS")

    ui_cookie_secure: bool | None = Field(default=None, alias="UI_COOKIE_SECURE")
    ui_cookie_samesite: str = Field(default="lax", alias="UI_COOKIE_SAMESITE")

    def ui_cookie_secure_effective(self) -> bool:
        if self.ui_cookie_secure is not None:
            return self.ui_cookie_secure
        return self.environment == "production"

    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_pro: str | None = Field(default=None, alias="STRIPE_PRICE_PRO")
    app_base_url: str = Field(default="http://localhost:8000", alias="APP_BASE_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
