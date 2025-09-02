"""Problem Details (RFC 9457) implementation for GPT Object Store API."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import Request
from fastapi.responses import JSONResponse


class ProblemDetail(BaseModel):
    """Problem Details as defined in RFC 9457."""
    
    type: str = Field(default="about:blank", description="A URI reference that identifies the problem type")
    title: str = Field(description="A short, human-readable summary of the problem type")
    status: int = Field(description="The HTTP status code")
    detail: Optional[str] = Field(default=None, description="A human-readable explanation specific to this occurrence")
    instance: Optional[str] = Field(default=None, description="A URI reference that identifies the specific occurrence")
    
    # Allow additional properties for extensions
    model_config = {"extra": "allow"}


class ProblemDetailException(Exception):
    """Base exception for Problem Details responses."""
    
    def __init__(
        self,
        status: int,
        title: str,
        detail: Optional[str] = None,
        type_uri: str = "about:blank",
        instance: Optional[str] = None,
        **extensions: Any
    ):
        self.status = status
        self.title = title
        self.detail = detail
        self.type_uri = type_uri
        self.instance = instance
        self.extensions = extensions
        super().__init__(detail or title)
    
    def to_problem_detail(self, request: Optional[Request] = None) -> ProblemDetail:
        """Convert to ProblemDetail model."""
        instance = self.instance
        if instance is None and request:
            instance = str(request.url.path)
        
        problem = ProblemDetail(
            type=self.type_uri,
            title=self.title,
            status=self.status,
            detail=self.detail,
            instance=instance
        )
        
        # Add any extensions
        for key, value in self.extensions.items():
            setattr(problem, key, value)
        
        return problem
    
    def to_response(self, request: Optional[Request] = None) -> JSONResponse:
        """Convert to JSONResponse with Problem Details format."""
        problem = self.to_problem_detail(request)
        return JSONResponse(
            status_code=self.status,
            content=problem.model_dump(exclude_none=True),
            headers={"Content-Type": "application/problem+json"}
        )


class BadRequestError(ProblemDetailException):
    """400 Bad Request error."""
    
    def __init__(self, detail: str, **extensions: Any):
        super().__init__(
            status=400,
            title="Bad Request",
            detail=detail,
            **extensions
        )


class UnauthorizedError(ProblemDetailException):
    """401 Unauthorized error."""
    
    def __init__(self, detail: str = "Authentication required", **extensions: Any):
        super().__init__(
            status=401,
            title="Unauthorized",
            detail=detail,
            **extensions
        )


class ForbiddenError(ProblemDetailException):
    """403 Forbidden error."""
    
    def __init__(self, detail: str = "Access denied", **extensions: Any):
        super().__init__(
            status=403,
            title="Forbidden",
            detail=detail,
            **extensions
        )


class NotFoundError(ProblemDetailException):
    """404 Not Found error."""
    
    def __init__(self, detail: str = "Resource not found", **extensions: Any):
        super().__init__(
            status=404,
            title="Not Found",
            detail=detail,
            **extensions
        )


class ConflictError(ProblemDetailException):
    """409 Conflict error."""
    
    def __init__(self, detail: str, **extensions: Any):
        super().__init__(
            status=409,
            title="Conflict",
            detail=detail,
            **extensions
        )


class UnprocessableEntityError(ProblemDetailException):
    """422 Unprocessable Entity error."""
    
    def __init__(self, detail: str, **extensions: Any):
        super().__init__(
            status=422,
            title="Unprocessable Entity",
            detail=detail,
            **extensions
        )


class TooManyRequestsError(ProblemDetailException):
    """429 Too Many Requests error."""
    
    def __init__(self, detail: str = "Rate limit exceeded", retry_after: Optional[int] = None, **extensions: Any):
        if retry_after:
            extensions["retry_after"] = retry_after
        super().__init__(
            status=429,
            title="Too Many Requests",
            detail=detail,
            **extensions
        )
    
    def to_response(self, request: Optional[Request] = None) -> JSONResponse:
        """Convert to JSONResponse with Retry-After header."""
        response = super().to_response(request)
        if "retry_after" in self.extensions:
            response.headers["Retry-After"] = str(self.extensions["retry_after"])
        return response


class InternalServerError(ProblemDetailException):
    """500 Internal Server Error."""
    
    def __init__(self, detail: str = "Internal server error", **extensions: Any):
        super().__init__(
            status=500,
            title="Internal Server Error",
            detail=detail,
            **extensions
        )


class ServiceUnavailableError(ProblemDetailException):
    """503 Service Unavailable error."""
    
    def __init__(self, detail: str = "Service temporarily unavailable", **extensions: Any):
        super().__init__(
            status=503,
            title="Service Unavailable",
            detail=detail,
            **extensions
        )


def create_problem_response(
    status: int,
    title: str,
    detail: Optional[str] = None,
    type_uri: str = "about:blank",
    instance: Optional[str] = None,
    request: Optional[Request] = None,
    **extensions: Any
) -> JSONResponse:
    """Create a Problem Details response."""
    if instance is None and request:
        instance = str(request.url.path)
    
    problem = ProblemDetail(
        type=type_uri,
        title=title,
        status=status,
        detail=detail,
        instance=instance
    )
    
    # Add any extensions
    for key, value in extensions.items():
        setattr(problem, key, value)
    
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(exclude_none=True),
        headers={"Content-Type": "application/problem+json"}
    )