"""Worker process: `uv run python -m finassist.worker` (polls the job table; no broker)."""

from __future__ import annotations

import logging
import time

from finassist.infra import Database
from finassist.providers import AnthropicExtractionProvider, FakeExtractionProvider
from finassist.services.imports import make_storage, run_once
from finassist.settings import get_settings

log = logging.getLogger("finassist.worker")


def build_provider(settings):
    """Explicit choice only: 'fake' or a fully configured real provider. Anything else raises ConfigError."""
    settings.require_real_provider()
    if settings.model_provider == "anthropic":
        return AnthropicExtractionProvider(settings.model_api_key.get_secret_value(), settings.extraction_model,
                                           max_output_tokens=settings.extraction_max_output_tokens, max_retries=0)
    return FakeExtractionProvider()


def run_step(db, storage, provider) -> str | None:
    """One worker iteration. Never raises: errors are logged without exception messages (they may contain slip
    text or row values) and the loop continues. Used by the standalone worker and the API's embedded worker."""
    from finassist.logsafe import log_exception

    try:
        with db.connect() as conn:
            return run_once(conn, storage, provider)
    except Exception as e:  # noqa: BLE001 - a worker loop must survive any single job failure
        log_exception(log, "worker_step_error", e)
        return None


def main(poll_s: float = 1.0) -> None:
    s = get_settings()
    provider = build_provider(s)  # raises ConfigError first if the provider is misconfigured
    url = s.worker_database_url or s.database_url
    if not url:
        from finassist.settings import ConfigError

        raise ConfigError("FINASSIST_WORKER_DATABASE_URL or FINASSIST_DATABASE_URL is required")
    db, storage, _ = Database(url.get_secret_value()), make_storage(s), provider
    logging.basicConfig(level=logging.INFO)
    from finassist.logsafe import install_redaction

    install_redaction()
    while True:
        outcome = run_step(db, storage, provider)
        if outcome:
            log.info("job outcome=%s", outcome)  # no ids, amounts or content in logs
        else:
            time.sleep(poll_s)


if __name__ == "__main__":
    main()
