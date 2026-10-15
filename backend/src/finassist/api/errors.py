"""Error envelope (docs/design/05-api-contracts.md §2)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        fields: list[dict[str, str]] | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or []
        self.retryable = retryable
        self.details = details or {}


def _envelope(request: Request, status: int, code: str, message: str, *, fields=None, retryable=False, details=None):
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    body = {
        "error": {
            "code": code,
            "message": message,
            "fields": fields or [],
            "retryable": retryable,
            "request_id": request_id,
            "details": details or {},
        }
    }
    return JSONResponse(status_code=status, content=body)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return _envelope(request, exc.status, exc.code, exc.message, fields=exc.fields,
                         retryable=exc.retryable, details=exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        # Report paths and issue types only; never echo submitted values (may be sensitive).
        fields = [{"path": ".".join(str(p) for p in e["loc"][1:]), "issue": e["type"]} for e in exc.errors()]
        return _envelope(request, 400, "VALIDATION_FAILED", "Some fields are invalid.", fields=fields)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHENTICATED"}.get(exc.status_code, "HTTP_ERROR")
        return _envelope(request, exc.status_code, code, "Request failed.")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Do not leak exception text (could contain data); log separately with redaction (CP1).
        return _envelope(request, 500, "INTERNAL", "Something went wrong.", retryable=True)
