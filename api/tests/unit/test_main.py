"""Tests for main FastAPI application."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from types import AsyncGeneratorType
from contextlib import asynccontextmanager

from src.main import create_app
from src.errors.problem_details import ServiceUnavailableError


class TestMainApp:
    """Test main FastAPI application."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager."""
        with patch("src.main.db_manager") as mock:
            mock.initialize = AsyncMock()
            mock.close = AsyncMock()
            yield mock
    
    @pytest.fixture
    def mock_get_db_pool(self):
        """Mock get_db_pool function."""
        with patch("src.main.get_db_pool") as mock:
            # Create a mock pool with proper context manager support
            mock_pool = AsyncMock()
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.fetchval = AsyncMock(return_value=5)  # Mock connection count
            
            # Create a proper async context manager
            @asynccontextmanager
            async def mock_acquire():
                yield mock_conn
            
            mock_pool.acquire = mock_acquire
            mock.return_value = mock_pool
            yield mock
    
    @pytest.fixture
    def app(self, mock_db_manager, mock_get_db_pool):
        """Create test app with mocked dependencies."""
        return create_app()
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    def test_create_app(self, mock_db_manager, mock_get_db_pool):
        """Test app creation."""
        app = create_app()
        
        assert app.title == "GPT Object Store API"
        assert app.version == "1.0.0"
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
        assert app.openapi_url == "/openapi.json"
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "GPT Object Store API"
        assert data["version"] == "1.0.0"
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"
    
    def test_liveness_check(self, client):
        """Test liveness endpoint."""
        response = client.get("/live")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert data["service"] == "GPT Object Store API"
    
    def test_health_check_success(self, client):
        """Test health check endpoint when database is healthy."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "GPT Object Store API"
        assert data["version"] == "1.0.0"
        assert data["database"] == "connected"
    
    def test_ready_check_success(self, client):
        """Test readiness check endpoint when database is ready."""
        response = client.get("/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["service"] == "GPT Object Store API"
        assert "database_connections" in data
    
    def test_health_check_database_failure(self, client, mock_get_db_pool):
        """Test health check when database fails."""
        # Mock database failure
        mock_get_db_pool.side_effect = Exception("Database connection failed")
        
        response = client.get("/health")
        
        assert response.status_code == 503
        assert response.headers["content-type"] == "application/problem+json"
        data = response.json()
        assert data["title"] == "Service Unavailable"
        assert data["status"] == 503
        assert "Database connection failed" in data["detail"]
    
    def test_ready_check_database_failure(self, client, mock_get_db_pool):
        """Test readiness check when database fails."""
        # Mock database failure
        mock_get_db_pool.side_effect = Exception("Database connection failed")
        
        response = client.get("/ready")
        
        assert response.status_code == 503
        assert response.headers["content-type"] == "application/problem+json"
        data = response.json()
        assert data["title"] == "Service Unavailable"
        assert data["status"] == 503
        assert "Service not ready" in data["detail"]
    
    def test_cors_middleware(self, client):
        """Test CORS middleware is configured."""
        response = client.options("/", headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET"
        })
        
        # The exact behavior depends on the CORS configuration
        # At minimum, we should get a valid response
        assert response.status_code in [200, 204]
    
    def test_openapi_docs_available(self, client):
        """Test that OpenAPI docs are available."""
        response = client.get("/docs")
        assert response.status_code == 200
        
        response = client.get("/redoc")
        assert response.status_code == 200
        
        response = client.get("/openapi.json")
        assert response.status_code == 200
        openapi_spec = response.json()
        assert openapi_spec["info"]["title"] == "GPT Object Store API"
    
    def test_exception_handlers_registered(self, app):
        """Test that exception handlers are registered."""
        # We can't easily test this directly, but we can verify
        # that the handlers are in the exception_handlers dict
        assert len(app.exception_handlers) > 0


class TestLifespan:
    """Test application lifespan events."""
    
    @pytest.mark.asyncio
    @patch("src.main.db_manager")
    @patch("src.main.get_db_pool")
    async def test_lifespan_startup_success(self, mock_get_db_pool, mock_db_manager):
        """Test successful startup."""
        # Mock database components
        mock_db_manager.initialize = AsyncMock()
        
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        
        # Create proper async context manager mock
        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn
        
        mock_pool.acquire = mock_acquire
        mock_get_db_pool.return_value = mock_pool
        
        # Import and test lifespan
        from src.main import lifespan
        app = create_app()
        
        # Test startup
        async with lifespan(app):
            mock_db_manager.initialize.assert_called_once()
            mock_get_db_pool.assert_called_once()
        
        # Test shutdown
        mock_db_manager.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch("src.main.db_manager")
    async def test_lifespan_startup_failure(self, mock_db_manager):
        """Test startup failure."""
        # Mock database initialization failure
        mock_db_manager.initialize = AsyncMock(side_effect=Exception("DB init failed"))
        
        from src.main import lifespan
        app = create_app()
        
        with pytest.raises(Exception, match="DB init failed"):
            async with lifespan(app):
                pass
    
    @pytest.mark.asyncio
    @patch("src.main.db_manager")
    @patch("src.main.get_db_pool")
    async def test_lifespan_shutdown_error(self, mock_get_db_pool, mock_db_manager):
        """Test shutdown error handling."""
        # Mock successful startup
        mock_db_manager.initialize = AsyncMock()
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        
        # Create proper async context manager mock
        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn
        
        mock_pool.acquire = mock_acquire
        mock_get_db_pool.return_value = mock_pool
        
        # Mock shutdown error
        mock_db_manager.close = AsyncMock(side_effect=Exception("Shutdown error"))
        
        from src.main import lifespan
        app = create_app()
        
        # Should not raise exception, just log the error
        async with lifespan(app):
            pass