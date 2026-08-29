"""Structured HTTP error model (Phase 7). Every error response has the same
shape -- `{"error": {"code", "message", "request_id"}}` -- and NEVER leaks a
stack trace, filesystem path, database credential, API key, or provider
secret. Stable, named codes so a client can branch on `code`, not on the
prose `message`.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.run_registry import ExceptionNotFoundError, RunNotFoundError
from app.policy.authorization import AuthorizationError


class ApiError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class InvalidDatasetError(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_DATASET"


class ConflictingStateError(ApiError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICTING_STATE"


class ServiceUnavailableError(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"


def _error_body(code: str, message: str, request_id: str | None) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(RunNotFoundError)
    async def _run_not_found_handler(request: Request, exc: RunNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_error_body("RUN_NOT_FOUND", "Reconciliation run was not found.", getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(ExceptionNotFoundError)
    async def _exception_not_found_handler(request: Request, exc: ExceptionNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_error_body("EXCEPTION_NOT_FOUND", "Exception was not found.", getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(AuthorizationError)
    async def _authorization_error_handler(request: Request, exc: AuthorizationError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=_error_body("FORBIDDEN", "The caller is not authorized to perform this action.", getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError):
        # Pydantic's own error detail is safe (field names/types), never a
        # stack trace or internal path -- included as the message for a
        # useful 422, per Phase 7.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("VALIDATION_ERROR", "Request validation failed.", getattr(request.state, "request_id", None))
            | {"details": exc.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
        # Milestone 13, Phase 7 finding: a request to a path that matches NO
        # route at all (e.g. an unmatched/normalized path, or a wrong HTTP
        # method on a real path) is raised by Starlette's OWN routing layer
        # as a plain HTTPException, before any of our route functions or
        # their handlers run -- FastAPI's built-in default handler for it
        # returns `{"detail": ...}`, a different, inconsistent shape from
        # every other error this API returns. Reshaping it here (preserving
        # the real status code, e.g. 404/405) makes every error response --
        # matched-route failure or unmatched-path/method -- the same
        # structured `{"error": {...}}` contract. No new leak surface: only
        # the status code and a generic phrase are used, never exc.detail
        # verbatim (which could otherwise echo back a raw internal path).
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        message = {
            404: "The requested resource was not found.",
            405: "This HTTP method is not supported for this resource.",
        }.get(exc.status_code, "The request could not be completed.")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, message, getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        # Deliberately generic: never include str(exc), the exception type,
        # or any traceback detail in the response body -- that could leak a
        # filesystem path, a query fragment, or other internal detail. The
        # real detail belongs in server-side logs, not the HTTP response.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("INTERNAL_ERROR", "An unexpected internal error occurred.", getattr(request.state, "request_id", None)),
        )
