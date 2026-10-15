"""HTTP entry point."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request

from finassist import __version__
from finassist.api.errors import install_error_handlers
from finassist.settings import Settings, get_settings


def build_chat_model(settings: Settings):
    """Fail closed: a requested real provider with missing config raises ConfigError at startup.
    With provider 'fake' there is no chat model and /chat returns 503 MODEL_UNAVAILABLE (never a fake answer)."""
    settings.require_real_provider()
    if settings.model_provider == "anthropic":
        from finassist.providers import AnthropicChatModel

        return AnthropicChatModel(settings.model_api_key.get_secret_value(), settings.chat_model,
                                  max_output_tokens=settings.chat_max_output_tokens)
    return None


def create_app(settings: Settings | None = None, *, db=None, storage=None, chat_model=None) -> FastAPI:
    settings = settings or get_settings()
    from finassist.logsafe import install_redaction

    install_redaction()
    app = FastAPI(title="FinAssist backend (prototype)", version=__version__)
    app.state.settings = settings
    if db is None and settings.database_url:
        from finassist.infra import Database

        db = Database(settings.database_url.get_secret_value())
    app.state.db = db
    if storage is None:
        from finassist.services.imports import make_storage

        storage = make_storage(settings)
    app.state.storage = storage
    app.state.chat_model = chat_model if chat_model is not None else build_chat_model(settings)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    install_error_handlers(app)

    @app.get("/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    if db is not None:
        from finassist.api.routes import router

        app.include_router(router)
    if settings.embedded_worker and db is not None:
        _start_embedded_worker(app, settings)
    return app


def _start_embedded_worker(app: FastAPI, settings: Settings) -> None:
    import threading
    import time

    from finassist.worker import build_provider, run_step

    from finassist.infra import Database

    provider = build_provider(settings)
    worker_db = Database((settings.worker_database_url or settings.database_url).get_secret_value())
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            if not run_step(worker_db, app.state.storage, provider):  # logs errors without exception messages
                time.sleep(1.0)

    @app.on_event("startup")
    def _start() -> None:
        threading.Thread(target=loop, name="finassist-worker", daemon=True).start()

    @app.on_event("shutdown")
    def _stop() -> None:
        stop.set()


def _module_app() -> FastAPI:
    # `uvicorn finassist.api.app:app` entry point. Import-time construction must not crash tooling that only
    # imports this module, but a misconfigured real provider must stop a real server: uvicorn imports `app`,
    # so the ConfigError propagates and the server exits with the message.
    return create_app()


app = _module_app()
