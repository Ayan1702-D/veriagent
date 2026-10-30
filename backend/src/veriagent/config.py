"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
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
    rate_limit_requests: int = Field(default=60, ge=1)
    rate_limit_window_seconds: float = Field(default=60.0, gt=0.0)

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
    max_llm_tokens: int = Field(default=12000, ge=1)
    max_searches: int = Field(default=6, ge=1)
    max_fetches: int = Field(default=10, ge=1)
    max_loops: int = Field(default=2, ge=0)
    max_seconds: float = Field(default=60.0, gt=0.0)

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
