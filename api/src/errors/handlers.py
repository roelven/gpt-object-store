"""Exception handlers for GPT Object Store API."""

import logging
from typing import Union
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

from .problem_details import (
    ProblemDetailException,
    BadRequestError,
    InternalServerError,
    create_problem_response
)

logger = logging.getLogger(__name__)


async def problem_detail_exception_handler(
    request: Request, 
    exc: ProblemDetailException
) -> JSONResponse:
    """Handle ProblemDetailException instances."""
    logger.info(
        f"Problem detail exception: {exc.status} - {exc.title}",
        extra={
            "status_code": exc.status,
            "path": str(request.url.path),
            "method": request.method,
            "detail": exc.detail
        }
    )
    return exc.to_response(request)


async def http_exception_handler(
    request: Request, 
    exc: Union[HTTPException, StarletteHTTPException]
) -> JSONResponse:
    """Handle FastAPI HTTPException and Starlette HTTPException."""
    logger.info(
        f"HTTP exception: {exc.status_code} - {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "path": str(request.url.path),
            "method": request.method,
            "detail": exc.detail
        }
    )
    
    # Map common HTTP status codes to appropriate titles
    status_titles = {
        400: "Bad Request",
        401: "Unauthorized", 
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout"
    }
    
    title = status_titles.get(exc.status_code, "HTTP Error")
    detail = str(exc.detail) if exc.detail else None
    
    # Handle special cases
    headers = {}
    if hasattr(exc, "headers") and exc.headers:
        headers.update(exc.headers)
    
    response = create_problem_response(
        status=exc.status_code,
        title=title,
        detail=detail,
        request=request
    )
    
    # Add any custom headers
    for key, value in headers.items():
        response.headers[key] = value
    
    return response


async def validation_exception_handler(
    request: Request, 
    exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors."""
    # Log detailed validation errors for debugging
    logger.info(f"Validation error: {len(exc.errors())} errors")
    for i, error in enumerate(exc.errors()):
        logger.info(f"  Error {i+1}: {error}")
    
    logger.info(
        f"Full validation error context",
        extra={
            "path": str(request.url.path),
            "method": request.method,
            "errors": exc.errors()
        }
    )
    
    # Format validation errors in a user-friendly way
    error_messages = []
    for error in exc.errors():
        loc = " -> ".join(str(x) for x in error["loc"])
        msg = error["msg"]
        error_messages.append(f"{loc}: {msg}")
    
    detail = "Validation failed: " + "; ".join(error_messages)
    
    return create_problem_response(
        status=422,
        title="Validation Error",
        detail=detail,
        request=request,
        validation_errors=exc.errors()
    )


async def pydantic_validation_exception_handler(
    request: Request,
    exc: ValidationError
) -> JSONResponse:
    """Handle direct Pydantic validation errors."""
    logger.info(
        f"Pydantic validation error: {len(exc.errors())} errors",
        extra={
            "path": str(request.url.path),
            "method": request.method,
            "errors": exc.errors()
        }
    )
    
    # Format validation errors in a user-friendly way
    error_messages = []
    for error in exc.errors():
        loc = " -> ".join(str(x) for x in error["loc"])
        msg = error["msg"]
        error_messages.append(f"{loc}: {msg}")
    
    detail = "Data validation failed: " + "; ".join(error_messages)
    
    return create_problem_response(
        status=400,
        title="Validation Error",
        detail=detail,
        request=request,
        validation_errors=exc.errors()
    )


async def general_exception_handler(
    request: Request, 
    exc: Exception
) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.error(
        f"Unhandled exception: {type(exc).__name__} - {str(exc)}",
        extra={
            "path": str(request.url.path),
            "method": request.method,
            "exception_type": type(exc).__name__
        },
        exc_info=True
    )
    
    # Don't expose internal error details in production
    return create_problem_response(
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred",
        request=request
    )


def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app."""
    
    # Custom Problem Detail exceptions
    app.add_exception_handler(ProblemDetailException, problem_detail_exception_handler)
    
    # FastAPI and Starlette HTTP exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    
    # Validation exceptions
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
    
    # Catch-all for unexpected exceptions
    app.add_exception_handler(Exception, general_exception_handler)