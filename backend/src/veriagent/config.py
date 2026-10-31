"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from veriagent.schemas.models import RunBudget


class Settings(BaseSettings):
    """Typed environment configuration for VeriAgent."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./veriagent.db"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit_requests: int = Field(default=30, ge=1)
    rate_limit_window_seconds: float = Field(default=60.0, gt=0.0)
    demo_replay_enabled: bool = True

    # Curated corpus
    corpus_enabled: bool = True
    corpus_dir: str = "corpus"
    chroma_path: str = "chroma_data"
    corpus_collection: str = "veriagent_corpus"
    corpus_embedding_model: str = "BAAI/bge-small-en-v1.5"
    corpus_max_document_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    corpus_chunk_size: int = Field(default=1200, ge=200, le=10_000)
    corpus_chunk_overlap: int = Field(default=200, ge=0, le=5000)
    corpus_top_k: int = Field(default=3, ge=1, le=20)

    # LLM Provider Keys
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""

    # Model Routing
    cheap_model: str = "gemini/gemini-1.5-flash"
    strong_model: str = "gemini/gemini-1.5-pro"

    # Optional Tool Keys
    tavily_api_key: str = ""
    openalex_mailto: str = ""

    # Default Run Budget Caps
    quote_match_threshold: float = Field(default=85.0, ge=0.0, le=100.0)
    max_llm_tokens: int = Field(default=6000, ge=1)
    max_searches: int = Field(default=4, ge=1)
    max_fetches: int = Field(default=6, ge=1)
    max_loops: int = Field(default=1, ge=0)
    max_seconds: float = Field(default=45.0, gt=0.0)

    @model_validator(mode="after")
    def require_strict_production_cors(self) -> "Settings":
        """Production accepts only explicit HTTPS browser origins."""
        if self.corpus_chunk_overlap >= self.corpus_chunk_size:
            raise ValueError("CORPUS_CHUNK_OVERLAP must be smaller than CORPUS_CHUNK_SIZE")
        if self.app_env != "production":
            return self
        if not self.cors_origins:
            raise ValueError("CORS_ORIGINS must contain at least one production frontend origin")
        for origin in self.cors_origins:
            parsed = urlparse(origin)
            hostname = (parsed.hostname or "").lower()
            if (
                origin == "*"
                or parsed.scheme != "https"
                or not hostname
                or hostname in {"localhost", "127.0.0.1", "::1"}
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "Production CORS origins must be explicit HTTPS origins without paths"
                )
        return self

    def default_budget(self) -> RunBudget:
        """Build a RunBudget instance from configured default limits."""
        return RunBudget(
            max_llm_tokens=self.max_llm_tokens,
            max_searches=self.max_searches,
            max_fetches=self.max_fetches,
            max_loops=self.max_loops,
            max_seconds=self.max_seconds,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
