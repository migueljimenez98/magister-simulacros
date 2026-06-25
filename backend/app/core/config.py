from functools import lru_cache
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Service
    api_port: int = 8000
    environment: str = "development"  # development | production

    # Comma-separated string (NOT list) so pydantic-settings doesn't try to
    # JSON-decode the env value. The parsed list is exposed via `cors_origins`.
    cors_origins_raw: str = Field(
        default="http://localhost:3000,http://localhost:3020",
        validation_alias="CORS_ORIGINS",
    )

    # Postgres. On Render, set a single standard DATABASE_URL — _normalize_db_urls
    # converts it to asyncpg and derives the psycopg DSN for the checkpointer.
    # checkpoint_dsn MUST default to "" so the derivation kicks in when
    # CHECKPOINT_DSN isn't set (e.g. on Render); a non-empty default would make
    # the checkpointer connect to localhost and time out. Locally, docker-compose
    # sets CHECKPOINT_DSN explicitly to the postgres service.
    database_url: str = "postgresql+asyncpg://magister:magister@localhost:5432/magister_simulacros"
    checkpoint_dsn: str = ""

    redis_url: str = "redis://localhost:6379/0"

    # Default chat LLM endpoint (OpenAI-compatible).
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o-mini"
    default_llm_base_url: str = "https://api.openai.com/v1"
    default_llm_api_key: str = ""

    # Embedding endpoint (KB grounding). "" → reuse default_llm_*.
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    # Audit graph concurrency
    score_param_concurrency: int = 8

    # ── Simulacros (Retell) ─────────────────────────────────────────────────
    retell_api_key: str = ""
    retell_agent_id: str = ""
    retell_from_number: str = ""
    retell_base_url: str = "https://api.retellai.com"
    retell_webhook_secret: str = ""
    simulacros_project_id: str = "proj-simulacros"
    # Token server-to-server para que el CRM avise (POST /api/retell/announce).
    crm_announce_token: str = ""

    @property
    def cors_origins(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]
        if self.environment.lower() == "production":
            origins = [o for o in origins if "localhost" not in o and "127.0.0.1" not in o]
        return origins

    @model_validator(mode="after")
    def _normalize_db_urls(self) -> Self:
        url = (self.database_url or "").strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]
        self.database_url = url
        if not (self.checkpoint_dsn or "").strip():
            if url.startswith("postgresql+asyncpg://"):
                self.checkpoint_dsn = "postgresql://" + url[len("postgresql+asyncpg://"):]
            else:
                self.checkpoint_dsn = url
        return self

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("JWT_SECRET must not be empty")
        if v.strip().lower().startswith("change-me"):
            raise ValueError("JWT_SECRET still has the example value. Set a random secret >= 32 chars.")
        if len(v.strip()) < 32:
            raise ValueError(f"JWT_SECRET is too short ({len(v.strip())} chars). Minimum 32.")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
