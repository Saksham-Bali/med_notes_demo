"""Typed application errors + FastAPI handlers. No raw 500s leak; every error becomes
JSON ``{"error": {"code", "message"}}``. Also a request-id middleware that feeds
``app.core.logging.request_id_var`` so every log line and audit row correlates."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger, request_id_var

log = get_logger("findingframe.errors")


class AppError(Exception):
    """Base for all typed application errors."""

    code = "internal_error"
    status_code = 500

    def __init__(self, message: str | None = None, *, code: str | None = None):
        self.message = message or self.__class__.__doc__ or "error"
        if code:
            self.code = code
        super().__init__(self.message)


class BadRequest(AppError):
    code = "bad_request"
    status_code = 400


class Unauthorized(AppError):
    code = "unauthorized"
    status_code = 401


class Forbidden(AppError):
    code = "forbidden"
    status_code = 403


class NotFound(AppError):
    code = "not_found"
    status_code = 404


class Conflict(AppError):
    code = "conflict"
    status_code = 409


class UnprocessableEntity(AppError):
    """Semantically invalid request (e.g. RECIST with no confirmed tracks)."""

    code = "unprocessable_entity"
    status_code = 422


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = rid
        return response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError):
        if exc.status_code >= 500:
            log.error("app_error", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_error_body("validation_error", _summarize_validation(exc)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception):
        log.error("unhandled_exception", error=str(exc), exc_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=_error_body("internal_error", "An unexpected error occurred."),
        )


def _summarize_validation(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return "; ".join(parts) or "invalid request"
