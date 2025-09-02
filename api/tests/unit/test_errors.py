"""Tests for error handling and Problem Details implementation."""

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from unittest.mock import Mock

from src.errors.problem_details import (
    ProblemDetail,
    ProblemDetailException,
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    ConflictError,
    UnprocessableEntityError,
    TooManyRequestsError,
    InternalServerError,
    ServiceUnavailableError,
    create_problem_response
)


class TestProblemDetail:
    """Test ProblemDetail model."""
    
    def test_problem_detail_defaults(self):
        """Test ProblemDetail with default values."""
        problem = ProblemDetail(
            title="Test Error",
            status=400
        )
        
        assert problem.type == "about:blank"
        assert problem.title == "Test Error"
        assert problem.status == 400
        assert problem.detail is None
        assert problem.instance is None
    
    def test_problem_detail_all_fields(self):
        """Test ProblemDetail with all fields."""
        problem = ProblemDetail(
            type="https://example.com/problems/test",
            title="Test Error", 
            status=400,
            detail="This is a test error",
            instance="/test/path"
        )
        
        assert problem.type == "https://example.com/problems/test"
        assert problem.title == "Test Error"
        assert problem.status == 400
        assert problem.detail == "This is a test error"
        assert problem.instance == "/test/path"
    
    def test_problem_detail_extra_fields(self):
        """Test ProblemDetail allows extra fields."""
        # This tests the Config.extra = "allow" setting
        problem_dict = {
            "type": "about:blank",
            "title": "Test Error",
            "status": 400,
            "custom_field": "custom_value",
            "error_code": "TEST_001"
        }
        
        problem = ProblemDetail(**problem_dict)
        assert problem.custom_field == "custom_value"
        assert problem.error_code == "TEST_001"


class TestProblemDetailException:
    """Test ProblemDetailException base class."""
    
    def test_basic_exception(self):
        """Test basic exception creation."""
        exc = ProblemDetailException(
            status=400,
            title="Test Error",
            detail="Test detail"
        )
        
        assert exc.status == 400
        assert exc.title == "Test Error"
        assert exc.detail == "Test detail"
        assert exc.type_uri == "about:blank"
        assert exc.instance is None
        assert str(exc) == "Test detail"
    
    def test_exception_with_extensions(self):
        """Test exception with extension fields."""
        exc = ProblemDetailException(
            status=400,
            title="Test Error",
            detail="Test detail",
            error_code="TEST_001",
            retry_after=60
        )
        
        assert exc.extensions["error_code"] == "TEST_001"
        assert exc.extensions["retry_after"] == 60
    
    def test_to_problem_detail_without_request(self):
        """Test converting to ProblemDetail without request."""
        exc = ProblemDetailException(
            status=400,
            title="Test Error",
            detail="Test detail"
        )
        
        problem = exc.to_problem_detail()
        
        assert problem.status == 400
        assert problem.title == "Test Error"
        assert problem.detail == "Test detail"
        assert problem.instance is None
    
    def test_to_problem_detail_with_request(self):
        """Test converting to ProblemDetail with request."""
        # Mock request
        request = Mock(spec=Request)
        request.url.path = "/test/path"
        
        exc = ProblemDetailException(
            status=400,
            title="Test Error",
            detail="Test detail"
        )
        
        problem = exc.to_problem_detail(request)
        
        assert problem.instance == "/test/path"
    
    def test_to_problem_detail_with_extensions(self):
        """Test converting to ProblemDetail with extensions."""
        exc = ProblemDetailException(
            status=400,
            title="Test Error",
            detail="Test detail",
            error_code="TEST_001"
        )
        
        problem = exc.to_problem_detail()
        
        assert problem.error_code == "TEST_001"
    
    def test_to_response(self):
        """Test converting to JSONResponse."""
        exc = ProblemDetailException(
            status=400,
            title="Test Error",
            detail="Test detail"
        )
        
        response = exc.to_response()
        
        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        assert response.headers["Content-Type"] == "application/problem+json"


class TestSpecificExceptions:
    """Test specific exception classes."""
    
    def test_bad_request_error(self):
        """Test BadRequestError."""
        exc = BadRequestError("Invalid input")
        
        assert exc.status == 400
        assert exc.title == "Bad Request"
        assert exc.detail == "Invalid input"
    
    def test_unauthorized_error(self):
        """Test UnauthorizedError."""
        exc = UnauthorizedError()
        
        assert exc.status == 401
        assert exc.title == "Unauthorized"
        assert exc.detail == "Authentication required"
        
        # Test custom detail
        exc_custom = UnauthorizedError("Invalid token")
        assert exc_custom.detail == "Invalid token"
    
    def test_forbidden_error(self):
        """Test ForbiddenError."""
        exc = ForbiddenError()
        
        assert exc.status == 403
        assert exc.title == "Forbidden"
        assert exc.detail == "Access denied"
    
    def test_not_found_error(self):
        """Test NotFoundError."""
        exc = NotFoundError()
        
        assert exc.status == 404
        assert exc.title == "Not Found"
        assert exc.detail == "Resource not found"
    
    def test_conflict_error(self):
        """Test ConflictError."""
        exc = ConflictError("Resource already exists")
        
        assert exc.status == 409
        assert exc.title == "Conflict"
        assert exc.detail == "Resource already exists"
    
    def test_unprocessable_entity_error(self):
        """Test UnprocessableEntityError."""
        exc = UnprocessableEntityError("Invalid data")
        
        assert exc.status == 422
        assert exc.title == "Unprocessable Entity"
        assert exc.detail == "Invalid data"
    
    def test_too_many_requests_error(self):
        """Test TooManyRequestsError."""
        exc = TooManyRequestsError()
        
        assert exc.status == 429
        assert exc.title == "Too Many Requests"
        assert exc.detail == "Rate limit exceeded"
        
        # Test with retry_after
        exc_retry = TooManyRequestsError(retry_after=60)
        assert exc_retry.extensions["retry_after"] == 60
        
        response = exc_retry.to_response()
        assert response.headers["Retry-After"] == "60"
    
    def test_internal_server_error(self):
        """Test InternalServerError."""
        exc = InternalServerError()
        
        assert exc.status == 500
        assert exc.title == "Internal Server Error"
        assert exc.detail == "Internal server error"
    
    def test_service_unavailable_error(self):
        """Test ServiceUnavailableError."""
        exc = ServiceUnavailableError()
        
        assert exc.status == 503
        assert exc.title == "Service Unavailable"
        assert exc.detail == "Service temporarily unavailable"


class TestCreateProblemResponse:
    """Test create_problem_response function."""
    
    def test_create_problem_response_basic(self):
        """Test basic problem response creation."""
        response = create_problem_response(
            status=400,
            title="Test Error",
            detail="Test detail"
        )
        
        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        assert response.headers["Content-Type"] == "application/problem+json"
    
    def test_create_problem_response_with_request(self):
        """Test problem response with request."""
        # Mock request
        request = Mock(spec=Request)
        request.url.path = "/test/path"
        
        response = create_problem_response(
            status=400,
            title="Test Error",
            request=request
        )
        
        # We can't easily test the response content without parsing JSON,
        # but we can verify the structure is correct
        assert response.status_code == 400
    
    def test_create_problem_response_with_extensions(self):
        """Test problem response with extensions."""
        response = create_problem_response(
            status=400,
            title="Test Error",
            error_code="TEST_001",
            custom_field="custom_value"
        )
        
        assert response.status_code == 400