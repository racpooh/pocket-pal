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


def create_app(settings: Settings | None = None, *, db=None, storage=None, chat_model=None, extraction_provider=None) -> FastAPI:
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

    @app.on_event("startup")
    def _redact_server_logs() -> None:
        install_redaction()  # again at startup: uvicorn configures its own handlers after the app is created

    test_mode = settings.model_provider == "fake"

    @app.get("/v1/health")
    def health() -> dict:
        # test_mode lets the client show a visible "TEST MODE: fake extraction" banner (never silent).
        return {"status": "ok", "version": __version__, "test_mode": test_mode, "env": settings.env}

    if db is not None:
        from finassist.api.routes import router

        app.include_router(router)
    if settings.embedded_worker and db is not None:
        _start_embedded_worker(app, settings, extraction_provider)
    return app


def _start_embedded_worker(app: FastAPI, settings: Settings, extraction_provider=None) -> None:
    import threading
    import time

    from finassist.worker import build_provider, run_step

    from finassist.infra import Database

    provider = build_provider(settings)  # fails closed on bad config even when a provider is injected
    if extraction_provider is not None:  # dev/test only: e.g. a fake provider preloaded with synthetic fixtures
        if settings.model_provider != "fake":
            from finassist.settings import ConfigError

            raise ConfigError("an injected extraction provider is only allowed with model_provider=fake")
        provider = extraction_provider
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


def __getattr__(name: str):
    """`uvicorn finassist.api.app:app` entry point, built on first access (PEP 562). Importing this module (tests,
    tooling) does not build an app; serving it does, and a missing/invalid provider config then raises ConfigError
    and the server exits (fail closed, CP3a: there is no default provider)."""
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
