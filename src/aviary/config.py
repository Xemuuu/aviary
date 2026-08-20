"""Application configuration loaded from the environment."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings.

    Values are read from environment variables, falling back to a local
    ``.env`` file. Construct via :func:`get_settings` rather than directly,
    so the instance is built once per process.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Base URL of the Qdrant instance.",
    )
    qdrant_collection: str = Field(
        default="statements",
        description="Collection holding indexed central bank statements.",
    )

    embedding_model: str = Field(
        default="intfloat/multilingual-e5-large",
        description="fastembed model identifier used for dense vectors.",
    )
    embedding_dim: int = Field(
        default=1024,
        gt=0,
        description="Dimensionality of the dense vectors, must match the model.",
    )

    llm_model: str = Field(
        default="gpt-4.1-mini",
        description="Chat model used by the graph nodes.",
    )
    openai_api_key: SecretStr = Field(
        description="API key for the chat model provider.",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Minimum severity emitted by the logger.",
    )
    log_json: bool = Field(
        default=False,
        description="Emit JSON logs instead of human-readable output.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
