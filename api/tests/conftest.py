"""Pytest configuration and shared fixtures for the GPT Object Store API tests."""

import asyncio
import pytest
import os
import hashlib
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import asyncpg
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.main import create_app
from src.config import Settings, get_settings
from src.db.connection import db_manager, get_db_pool
from src.models.collections import Collection
from src.models.objects import Object


# Disable logging for cleaner test output
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("asyncpg").setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Override settings for testing."""
    return Settings(
        database_url="postgresql://gptstore:change-me@localhost:5432/gptstore_test",
        host="127.0.0.1",
        port=8001,  # Different port for tests
        debug=True,
        log_level="ERROR",  # Reduce log noise during tests
        rate_limits="key:1000/m,write:500/m,ip:5000/5m",  # Higher limits for tests
        cors_origins=["*"],
        cors_allow_credentials=True,
        cors_allow_methods=["*"],
        cors_allow_headers=["*"]
    )


@pytest.fixture(scope="session")
async def test_db_pool(test_settings: Settings) -> AsyncGenerator[asyncpg.Pool, None]:
    """Create a test database connection pool."""
    # Use regular database URL for integration tests
    # This assumes PostgreSQL is running via docker-compose
    db_url = "postgresql://gptstore:change-me@localhost:5432/gptstore"
    
    try:
        pool = await asyncpg.create_pool(
            db_url,
            min_size=1,
            max_size=5,
            command_timeout=5
        )
        yield pool
    except Exception:
        # If can't connect, yield None - tests will be skipped
        yield None
    finally:
        if 'pool' in locals() and pool:
            await pool.close()


@pytest.fixture(scope="session")
async def setup_test_database(test_db_pool: Optional[asyncpg.Pool]):
    """Set up test database schema and sample data."""
    if not test_db_pool:
        pytest.skip("Database not available for integration tests")
    
    async with test_db_pool.acquire() as conn:
        # Clean up any existing test data
        await conn.execute("DELETE FROM objects WHERE gpt_id = 'test-gpt'")
        await conn.execute("DELETE FROM collections WHERE gpt_id = 'test-gpt'")
        await conn.execute("DELETE FROM api_keys WHERE gpt_id = 'test-gpt'")
        await conn.execute("DELETE FROM gpts WHERE id = 'test-gpt'")
        
        # Insert test GPT
        await conn.execute(
            "INSERT INTO gpts (id, name, created_at) VALUES ($1, $2, $3)",
            "test-gpt", "Test GPT", datetime.now(timezone.utc)
        )
        
        # Insert test API key (hash of "test-api-key")
        test_key_hash = hashlib.sha256(b"test-api-key").digest()
        await conn.execute(
            "INSERT INTO api_keys (token_hash, gpt_id, created_at) VALUES ($1, $2, $3)",
            test_key_hash, "test-gpt", datetime.now(timezone.utc)
        )
        
        # Insert test collection
        await conn.execute(
            """INSERT INTO collections (id, gpt_id, name, schema, created_at) 
               VALUES ($1, $2, $3, $4, $5)""",
            uuid4(), "test-gpt", "notes", 
            '{"type": "object", "properties": {"title": {"type": "string"}}}',
            datetime.now(timezone.utc)
        )
    
    yield
    
    # Cleanup after tests
    async with test_db_pool.acquire() as conn:
        await conn.execute("DELETE FROM objects WHERE gpt_id = 'test-gpt'")
        await conn.execute("DELETE FROM collections WHERE gpt_id = 'test-gpt'")
        await conn.execute("DELETE FROM api_keys WHERE gpt_id = 'test-gpt'")
        await conn.execute("DELETE FROM gpts WHERE id = 'test-gpt'")


@pytest.fixture
def mock_settings(test_settings: Settings):
    """Mock settings for unit tests."""
    with patch('src.config.get_settings', return_value=test_settings):
        yield test_settings


@pytest.fixture
def app(mock_settings: Settings) -> FastAPI:
    """Create FastAPI application instance for testing."""
    return create_app()


@pytest.fixture
def test_client(app: FastAPI) -> TestClient:
    """Create test client for API testing."""
    return TestClient(app)


@pytest.fixture
async def integration_app(test_db_pool: Optional[asyncpg.Pool], test_settings: Settings) -> AsyncGenerator[FastAPI, None]:
    """Create FastAPI application with real database for integration tests."""
    if not test_db_pool:
        pytest.skip("Database not available for integration tests")
    
    # Override the database connection to use our test pool
    original_get_settings = get_settings
    
    def mock_get_settings():
        return test_settings
    
    with patch('src.config.get_settings', mock_get_settings):
        # Mock the db_manager to use our test pool
        with patch('src.db.connection.get_db_pool', return_value=test_db_pool):
            app = create_app()
            yield app


@pytest.fixture
async def integration_client(integration_app: FastAPI, setup_test_database) -> TestClient:
    """Create test client for integration testing with real database."""
    return TestClient(integration_app)


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Standard authorization headers for API testing."""
    return {"Authorization": "Bearer test-api-key"}


@pytest.fixture
def problem_json_headers() -> Dict[str, str]:
    """Headers expecting Problem Details JSON responses."""
    return {"Accept": "application/problem+json"}


@pytest.fixture
def json_headers() -> Dict[str, str]:
    """Standard JSON headers for API requests."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


@pytest.fixture
def full_headers(auth_headers: Dict[str, str], json_headers: Dict[str, str]) -> Dict[str, str]:
    """Combined auth and JSON headers."""
    return {**auth_headers, **json_headers}


# Mock fixtures for unit testing
@pytest.fixture
def mock_auth_middleware():
    """Mock authentication middleware."""
    with patch('src.auth.middleware.auth_middleware') as mock:
        mock.return_value = AsyncMock()
        yield mock


@pytest.fixture
def mock_get_current_gpt_id():
    """Mock current GPT ID dependency."""
    with patch('src.auth.dependencies.get_current_gpt_id_from_state') as mock:
        mock.return_value = "test-gpt"
        yield mock


@pytest.fixture
def mock_db_pool():
    """Mock database pool for unit tests."""
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch('src.db.connection.get_db_pool', return_value=mock_pool):
        yield mock_pool, mock_conn


# Sample data fixtures
@pytest.fixture
def sample_collection() -> Dict[str, Any]:
    """Sample collection data for testing."""
    return {
        "id": str(uuid4()),
        "gpt_id": "test-gpt",
        "name": "test-collection",
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["title"]
        },
        "created_at": datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
def sample_collection_model(sample_collection: Dict[str, Any]) -> Collection:
    """Sample collection model instance."""
    data = sample_collection.copy()
    data["created_at"] = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    return Collection(**data)


@pytest.fixture
def sample_object() -> Dict[str, Any]:
    """Sample object data for testing."""
    return {
        "id": str(uuid4()),
        "gpt_id": "test-gpt",
        "collection": "notes",
        "body": {
            "title": "Test Note",
            "content": "This is a test note content",
            "tags": ["test", "sample"]
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
def sample_object_model(sample_object: Dict[str, Any]) -> Object:
    """Sample object model instance."""
    data = sample_object.copy()
    data["created_at"] = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    data["updated_at"] = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
    return Object(**data)


@pytest.fixture
def multiple_objects() -> list[Dict[str, Any]]:
    """Multiple object data for pagination testing."""
    base_time = datetime.now(timezone.utc)
    objects = []
    
    for i in range(5):
        obj_time = base_time.replace(microsecond=i * 100000)
        objects.append({
            "id": str(uuid4()),
            "gpt_id": "test-gpt",
            "collection": "notes",
            "body": {
                "title": f"Test Note {i+1}",
                "content": f"Content for note {i+1}",
                "index": i + 1
            },
            "created_at": obj_time.isoformat(),
            "updated_at": obj_time.isoformat()
        })
    
    # Sort by created_at DESC, id DESC for testing
    objects.sort(key=lambda x: (x["created_at"], x["id"]), reverse=True)
    return objects


# Database state management fixtures
@pytest.fixture
async def clean_database(test_db_pool: Optional[asyncpg.Pool]):
    """Ensure clean database state for each test."""
    if not test_db_pool:
        pytest.skip("Database not available")
    
    # Clean up before test
    async with test_db_pool.acquire() as conn:
        await conn.execute("DELETE FROM objects WHERE gpt_id LIKE 'test-%'")
        await conn.execute("DELETE FROM collections WHERE gpt_id LIKE 'test-%'")
    
    yield
    
    # Clean up after test
    async with test_db_pool.acquire() as conn:
        await conn.execute("DELETE FROM objects WHERE gpt_id LIKE 'test-%'")
        await conn.execute("DELETE FROM collections WHERE gpt_id LIKE 'test-%'")


# Performance testing fixtures
@pytest.fixture
def performance_timer():
    """Timer fixture for performance testing."""
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        @property
        def elapsed(self) -> float:
            if self.start_time is None or self.end_time is None:
                return 0.0
            return self.end_time - self.start_time
    
    return Timer()


# Rate limiting test fixtures
@pytest.fixture
def rate_limit_override():
    """Override rate limits for testing."""
    original_limits = os.environ.get('RATE_LIMITS', '')
    os.environ['RATE_LIMITS'] = 'key:5/m,write:2/m,ip:10/m'  # Very low limits for testing
    
    yield
    
    # Restore original limits
    if original_limits:
        os.environ['RATE_LIMITS'] = original_limits
    else:
        os.environ.pop('RATE_LIMITS', None)


# Pytest markers for test categorization
def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, mocked)")
    config.addinivalue_line("markers", "integration: Integration tests (slower, real database)")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "slow: Slow running tests")


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location and name patterns."""
    for item in items:
        # Mark integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        # Mark unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        
        # Mark performance tests
        if "performance" in item.name or "perf" in item.name:
            item.add_marker(pytest.mark.performance)
        
        # Mark slow tests
        if "slow" in item.name or item.get_closest_marker("slow"):
            item.add_marker(pytest.mark.slow)


# Skip integration tests if database is not available
def pytest_runtest_setup(item):
    """Skip tests that require database if it's not available."""
    if item.get_closest_marker("integration"):
        try:
            # Quick check if database is reachable
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 5432))
            sock.close()
            if result != 0:
                pytest.skip("PostgreSQL database not available for integration tests")
        except Exception:
            pytest.skip("Cannot verify database availability for integration tests")