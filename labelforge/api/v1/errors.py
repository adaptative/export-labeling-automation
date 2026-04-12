"""Standardized error response models and exception handlers.

Provides consistent error format for frontend error boundaries:
  { "detail": "...", "error_code": "...", "status": 4xx/5xx }
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response returned by all API endpoints."""
    detail: str
    error_code: str
    status: int


# Error code constants
ERR_NOT_FOUND = "NOT_FOUND"
ERR_VALIDATION = "VALIDATION_ERROR"
ERR_UNAUTHORIZED = "UNAUTHORIZED"
ERR_FORBIDDEN = "FORBIDDEN"
ERR_CONFLICT = "CONFLICT"
ERR_INTERNAL = "INTERNAL_ERROR"
ERR_SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class AppError(Exception):
    """Application-level error with error code for frontend consumption."""

    def __init__(
        self,
        status: int,
        detail: str,
        error_code: str = ERR_INTERNAL,
    ):
        self.status = status
        self.detail = detail
        self.error_code = error_code


def register_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=ErrorResponse(
                detail=exc.detail,
                error_code=exc.error_code,
                status=exc.status,
            ).model_dump(),
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                detail="Resource not found",
                error_code=ERR_NOT_FOUND,
                status=404,
            ).model_dump(),
        )

    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                detail="Internal server error",
                error_code=ERR_INTERNAL,
                status=500,
            ).model_dump(),
        )
