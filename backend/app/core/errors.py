"""Unified error response envelope (design §api_spec).

Every error leaves the API as: {"error": {"code": "...", "message": "..."}}.
500s hide internals from the client and log the traceback server-side. Routers
keep raising FastAPI's HTTPException as usual — handlers do the translation."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import i18n

log = logging.getLogger(__name__)

# HTTP status code → stable machine-readable error code.
_STATUS_CODE_MAP: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    422: "VALIDATION_ERROR",  # Unprocessable Content (literal avoids deprecated constant)
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL",
}


def _envelope(code: str, message: str, status_code: int, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODE_MAP.get(exc.status_code, "ERROR")
    # detail carries a message KEY (i18n.MESSAGES) or literal text; translate it.
    raw = exc.detail if isinstance(exc.detail, str) else "request_failed"
    message = i18n.translate(raw)
    return _envelope(code, message, exc.status_code, getattr(exc, "headers", None))


async def _validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Surface the first field error compactly; full detail stays in logs.
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    detail = first.get("msg") or i18n.translate("invalid_input")
    message = f"{loc}: {detail}".strip(": ")
    return _envelope("VALIDATION_ERROR", message, 422)


async def _unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error: %s", exc)  # traceback to logs, not to client
    return _envelope(
        "INTERNAL", i18n.translate("internal_error"), status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
