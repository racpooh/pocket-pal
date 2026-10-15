"""Runtime configuration. One loader for API, worker and scripts.

Sources, highest priority first: process environment, then the repository-root `.env`
(`<repo>/.env`), then `backend/.env`. Secrets have no defaults and are never logged.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
ENV_FILES = (str(BACKEND_DIR / ".env"), str(REPO_ROOT / ".env"))  # later files win; env vars win over both

REAL_PROVIDERS = ("anthropic",)
ALL_PROVIDERS = ("fake",) + REAL_PROVIDERS


class ConfigError(RuntimeError):
    """Raised when a requested configuration cannot be satisfied. Never silently downgraded."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FINASSIST_", env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"  # dev | test | sandbox
    database_url: SecretStr | None = None  # API role (RLS enforced)
    worker_database_url: SecretStr | None = None  # worker role (finassist_worker membership); falls back to database_url
    storage_dir: str = "./var/uploads"  # dev only; deployed builds use a private bucket (D4)
    storage_backend: str = "local"  # local | gcs
    gcs_bucket: str | None = None
    embedded_worker: bool = False  # run the job loop inside the API process (single Cloud Run service)
    model_provider: str = "fake"  # fake | anthropic (D2)
    extraction_model: str = "claude-haiku-5-5"
    chat_model: str = "claude-sonnet-5-5"
    model_api_key: SecretStr | None = None
    max_upload_bytes: int = 8 * 1024 * 1024
    default_timezone: str = "Asia/Bangkok"
    # cost controls for real model calls
    budget_usd: float = 1.0
    max_model_requests: int = 120
    extraction_max_output_tokens: int = 400
    chat_max_output_tokens: int = 700

    def require_real_provider(self) -> None:
        """Fail closed: if a real provider is requested, every piece must be present."""
        if self.model_provider not in ALL_PROVIDERS:
            raise ConfigError(f"unknown FINASSIST_MODEL_PROVIDER={self.model_provider!r}; expected one of {ALL_PROVIDERS}")
        if self.model_provider in REAL_PROVIDERS:
            if not self.model_api_key or not self.model_api_key.get_secret_value().strip():
                raise ConfigError("FINASSIST_MODEL_PROVIDER=anthropic but FINASSIST_MODEL_API_KEY is missing or empty")
            if not self.extraction_model or not self.chat_model:
                raise ConfigError("extraction/chat model ids must be set")

    def describe(self) -> dict:
        """Non-secret summary for evidence manifests."""
        key = self.model_api_key.get_secret_value() if self.model_api_key else ""
        return {"model_provider": self.model_provider, "extraction_model": self.extraction_model, "chat_model": self.chat_model,
                "api_key_present": bool(key), "budget_usd": self.budget_usd, "max_model_requests": self.max_model_requests,
                "extraction_max_output_tokens": self.extraction_max_output_tokens, "chat_max_output_tokens": self.chat_max_output_tokens,
                "env_files_considered": [f for f in ENV_FILES if Path(f).exists()]}


def get_settings() -> Settings:
    return Settings()
