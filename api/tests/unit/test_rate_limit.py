"""Tests for rate limiting functionality."""

import asyncio
import time
import pytest
from unittest.mock import Mock, patch
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.rate_limit.token_bucket import TokenBucket, RateLimitConfig, RateLimitResult
from src.rate_limit.storage import RateLimitStorage, get_rate_limit_storage, reset_rate_limit_storage
from src.rate_limit.middleware import RateLimitMiddleware, RateLimitInfo


class TestTokenBucket:
    """Tests for TokenBucket implementation."""
    
    def test_create_bucket(self):
        """Test creating a token bucket."""
        bucket = TokenBucket.create(capacity=10, refill_rate=1.0)
        
        assert bucket.capacity == 10
        assert bucket.refill_rate == 1.0
        assert bucket.tokens == 10.0
        assert bucket.last_refill <= time.time()
    
    def test_consume_tokens_success(self):
        """Test successful token consumption."""
        bucket = TokenBucket.create(capacity=10, refill_rate=1.0)
        
        result = bucket.consume(1)
        
        assert result.allowed is True
        assert result.retry_after == 0.0
        assert bucket.tokens == 9.0
    
    def test_consume_tokens_multiple(self):
        """Test consuming multiple tokens."""
        bucket = TokenBucket.create(capacity=10, refill_rate=1.0)
        
        result = bucket.consume(5)
        
        assert result.allowed is True
        assert bucket.tokens == 5.0
    
    def test_consume_tokens_insufficient(self):
        """Test token consumption when insufficient tokens available."""
        bucket = TokenBucket.create(capacity=2, refill_rate=1.0)
        initial_tokens = 1.0
        bucket.tokens = initial_tokens  # Only 1 token available
        
        result = bucket.consume(2)
        
        assert result.allowed is False
        assert result.retry_after == pytest.approx(1.0, rel=1e-2)  # Need 1 second to get 1 more token
        # Tokens should be close to initial value (small refill due to timing)
        assert bucket.tokens >= initial_tokens
        assert bucket.tokens <= initial_tokens + 0.01  # Allow small refill
    
    def test_token_refill(self):
        """Test token refill over time."""
        bucket = TokenBucket.create(capacity=10, refill_rate=2.0)  # 2 tokens per second
        bucket.tokens = 5.0
        
        # Simulate 1 second passing
        bucket.last_refill = time.time() - 1.0
        bucket._refill_tokens(time.time())
        
        assert bucket.tokens == pytest.approx(7.0, rel=1e-3)  # 5 + 2 tokens added
    
    def test_token_refill_capped_at_capacity(self):
        """Test that token refill is capped at bucket capacity."""
        bucket = TokenBucket.create(capacity=10, refill_rate=2.0)
        bucket.tokens = 9.0
        
        # Simulate 2 seconds passing (would add 4 tokens)
        bucket.last_refill = time.time() - 2.0
        bucket._refill_tokens(time.time())
        
        assert bucket.tokens == 10.0  # Capped at capacity
    
    def test_peek_doesnt_consume_tokens(self):
        """Test that peek doesn't actually consume tokens."""
        bucket = TokenBucket.create(capacity=10, refill_rate=1.0)
        initial_tokens = bucket.tokens
        
        result = bucket.peek()
        
        assert result.allowed is True
        assert bucket.tokens == initial_tokens  # Unchanged


class TestRateLimitConfig:
    """Tests for RateLimitConfig utilities."""
    
    def test_parse_rate_string_per_second(self):
        """Test parsing rate string with per-second format."""
        capacity, refill_rate = RateLimitConfig.parse_rate_string("60/s")
        
        assert capacity == 60
        assert refill_rate == 60.0  # 60 tokens per second
    
    def test_parse_rate_string_per_minute(self):
        """Test parsing rate string with per-minute format."""
        capacity, refill_rate = RateLimitConfig.parse_rate_string("60/m")
        
        assert capacity == 60
        assert refill_rate == 1.0  # 60 tokens per 60 seconds = 1 per second
    
    def test_parse_rate_string_per_hour(self):
        """Test parsing rate string with per-hour format."""
        capacity, refill_rate = RateLimitConfig.parse_rate_string("3600/h")
        
        assert capacity == 3600
        assert refill_rate == 1.0  # 3600 tokens per 3600 seconds = 1 per second
    
    def test_parse_rate_string_custom_periods(self):
        """Test parsing rate string with custom periods."""
        # 100 requests per 5 minutes
        capacity, refill_rate = RateLimitConfig.parse_rate_string("100/5m")
        
        assert capacity == 100
        assert refill_rate == pytest.approx(100 / 300)  # 100 per 300 seconds
    
    def test_parse_rate_string_invalid(self):
        """Test parsing invalid rate strings."""
        with pytest.raises(ValueError):
            RateLimitConfig.parse_rate_string("invalid")
        
        with pytest.raises(ValueError):
            RateLimitConfig.parse_rate_string("60/x")
    
    def test_parse_rate_limits_multiple(self):
        """Test parsing multiple rate limits."""
        limits = RateLimitConfig.parse_rate_limits("key:60/m,write:10/m,ip:600/5m")
        
        assert "key" in limits
        assert "write" in limits
        assert "ip" in limits
        
        assert limits["key"] == (60, 1.0)
        assert limits["write"] == (10, pytest.approx(10/60))
        assert limits["ip"] == (600, pytest.approx(600/300))


class TestRateLimitStorage:
    """Tests for RateLimitStorage."""
    
    def setup_method(self):
        """Set up test storage."""
        self.storage = RateLimitStorage(cleanup_interval=1)  # Short interval for testing
    
    def test_get_bucket_creates_new(self):
        """Test that get_bucket creates new buckets."""
        bucket = self.storage.get_bucket("test:key", 10, 1.0)
        
        assert isinstance(bucket, TokenBucket)
        assert bucket.capacity == 10
        assert bucket.refill_rate == 1.0
    
    def test_get_bucket_returns_existing(self):
        """Test that get_bucket returns existing buckets."""
        bucket1 = self.storage.get_bucket("test:key", 10, 1.0)
        bucket2 = self.storage.get_bucket("test:key", 10, 1.0)
        
        assert bucket1 is bucket2
    
    def test_get_bucket_updates_parameters(self):
        """Test that get_bucket updates parameters when they change."""
        bucket1 = self.storage.get_bucket("test:key", 10, 1.0)
        bucket1.tokens = 5.0
        
        bucket2 = self.storage.get_bucket("test:key", 20, 2.0)
        
        assert bucket2.capacity == 20
        assert bucket2.refill_rate == 2.0
        # Should preserve some tokens proportionally
        assert bucket2.tokens > 0
        assert bucket2.tokens <= 20
    
    def test_remove_bucket(self):
        """Test removing buckets."""
        self.storage.get_bucket("test:key", 10, 1.0)
        
        removed = self.storage.remove_bucket("test:key")
        assert removed is True
        
        removed = self.storage.remove_bucket("nonexistent")
        assert removed is False
    
    def test_clear_all(self):
        """Test clearing all buckets."""
        self.storage.get_bucket("test:key1", 10, 1.0)
        self.storage.get_bucket("test:key2", 10, 1.0)
        
        assert self.storage.get_bucket_count() == 2
        
        self.storage.clear_all()
        
        assert self.storage.get_bucket_count() == 0
    
    def test_get_bucket_info(self):
        """Test getting bucket information."""
        bucket = self.storage.get_bucket("test:key", 10, 1.0)
        
        info = self.storage.get_bucket_info("test:key")
        
        assert info is not None
        assert info["capacity"] == 10
        assert info["refill_rate"] == 1.0
        assert "tokens" in info
        assert "last_refill" in info
    
    def test_cleanup_expired_buckets(self):
        """Test cleanup of expired buckets."""
        # Create bucket and make it look old
        bucket = self.storage.get_bucket("test:key", 10, 1.0)
        bucket.last_refill = time.time() - 1000  # Very old
        bucket.tokens = 10.0  # Full bucket (unused)
        
        # Force cleanup
        self.storage._last_cleanup = 0
        self.storage._cleanup_expired_buckets()
        
        # Bucket should be removed
        assert self.storage.get_bucket_count() == 0


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""
    
    def setup_method(self):
        """Set up test middleware."""
        # Reset storage before each test
        reset_rate_limit_storage()
        
        self.app = FastAPI()
        self.middleware = RateLimitMiddleware(self.app)
        
        # Mock settings
        self.settings_patcher = patch('src.rate_limit.middleware.get_settings')
        mock_settings = self.settings_patcher.start()
        mock_settings.return_value.rate_limits = "key:60/m,write:10/m,ip:600/5m"
    
    def teardown_method(self):
        """Clean up after test."""
        self.settings_patcher.stop()
    
    @pytest.mark.asyncio
    async def test_skip_paths(self):
        """Test that middleware skips configured paths."""
        request = Mock(spec=Request)
        request.url.path = "/health"
        
        async def mock_call_next(req):
            return "response"
        
        # Should skip rate limiting
        result = await self.middleware.dispatch(request, mock_call_next)
        assert result == "response"
    
    @pytest.mark.asyncio
    async def test_skip_paths_v1_variants(self):
        """Test that middleware skips v1-prefixed health endpoints."""
        v1_skip_paths = ["/v1/health", "/v1/ready", "/v1/live", "/v1/"]
        
        async def mock_call_next(req):
            return f"response_for_{req.url.path}"
        
        for path in v1_skip_paths:
            request = Mock(spec=Request)
            request.url.path = path
            
            result = await self.middleware.dispatch(request, mock_call_next)
            assert result == f"response_for_{path}", f"Path {path} should skip rate limiting"
    
    @pytest.mark.asyncio
    async def test_skip_paths_comprehensive(self):
        """Test that middleware skips all configured skip paths."""
        # Use the same skip paths as configured in main.py
        skip_paths = [
            "/health", "/ready", "/live", "/", "/docs", "/redoc", "/openapi.json",
            "/v1/health", "/v1/ready", "/v1/live", "/v1/"
        ]
        
        # Create middleware with explicit skip paths
        from src.rate_limit.middleware import RateLimitMiddleware
        middleware = RateLimitMiddleware(None, skip_paths=skip_paths)
        
        async def mock_call_next(req):
            return "response"
        
        for path in skip_paths:
            request = Mock(spec=Request)
            request.url.path = path
            
            result = await middleware.dispatch(request, mock_call_next)
            assert result == "response", f"Path {path} should skip rate limiting"
    
    def test_skip_paths_consistency_with_auth_middleware(self):
        """Test that rate limiting skip paths match auth middleware skip paths."""
        # Import both middleware classes to compare their default skip paths
        from src.rate_limit.middleware import RateLimitMiddleware
        from src.auth.middleware import AuthenticationMiddleware
        
        # Create instances and check their default skip paths
        rate_limit_middleware = RateLimitMiddleware(None)
        auth_middleware = AuthenticationMiddleware(None)
        
        # Both should have the same default skip paths
        assert rate_limit_middleware.skip_paths == auth_middleware.skip_paths, \
            "Rate limiting and authentication middleware should have identical skip paths"
    
    def test_get_client_ip_forwarded(self):
        """Test client IP extraction from X-Forwarded-For header."""
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        
        ip = self.middleware._get_client_ip(request)
        assert ip == "192.168.1.1"
    
    def test_get_client_ip_real_ip(self):
        """Test client IP extraction from X-Real-IP header."""
        request = Mock(spec=Request)
        request.headers = {"X-Real-IP": "192.168.1.1"}
        
        ip = self.middleware._get_client_ip(request)
        assert ip == "192.168.1.1"
    
    def test_get_client_ip_direct(self):
        """Test client IP extraction from request.client."""
        request = Mock(spec=Request)
        request.headers = {}
        request.client = Mock()
        request.client.host = "192.168.1.1"
        
        ip = self.middleware._get_client_ip(request)
        assert ip == "192.168.1.1"
    
    def test_get_api_key_hash_from_header(self):
        """Test API key hash extraction from Authorization header."""
        request = Mock(spec=Request)
        request.headers = {"Authorization": "Bearer test-api-key"}
        
        # Create a state object that raises AttributeError for api_key_hash
        class MockState:
            def __getattr__(self, name):
                if name == 'api_key_hash':
                    raise AttributeError("'MockState' object has no attribute 'api_key_hash'")
                return Mock()
        
        request.state = MockState()
        
        api_key_hash = self.middleware._get_api_key_hash(request)
        assert api_key_hash is not None
        assert len(api_key_hash) == 32  # MD5 hash length
    
    def test_get_api_key_hash_from_state(self):
        """Test API key hash extraction from request state."""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.api_key_hash = "test-hash"
        
        api_key_hash = self.middleware._get_api_key_hash(request)
        assert api_key_hash == "test-hash"
    
    def test_is_write_operation(self):
        """Test write operation detection."""
        # Test write methods
        for method in ["POST", "PUT", "PATCH", "DELETE"]:
            request = Mock(spec=Request)
            request.method = method
            assert self.middleware._is_write_operation(request) is True
        
        # Test read methods
        for method in ["GET", "HEAD", "OPTIONS"]:
            request = Mock(spec=Request)
            request.method = method
            assert self.middleware._is_write_operation(request) is False


class TestRateLimitInfo:
    """Tests for RateLimitInfo utility class."""
    
    def setup_method(self):
        """Set up test environment."""
        reset_rate_limit_storage()
        
        # Mock settings
        self.settings_patcher = patch('src.rate_limit.middleware.get_settings')
        mock_settings = self.settings_patcher.start()
        mock_settings.return_value.rate_limits = "key:60/m,write:10/m,ip:600/5m"
    
    def teardown_method(self):
        """Clean up after test."""
        self.settings_patcher.stop()
    
    def test_get_rate_limit_status_empty(self):
        """Test getting rate limit status with no buckets."""
        status = RateLimitInfo.get_rate_limit_status()
        
        assert "timestamp" in status
        assert "buckets" in status
        assert "configuration" in status
        assert len(status["buckets"]) == 0
    
    def test_get_rate_limit_status_with_buckets(self):
        """Test getting rate limit status with existing buckets."""
        storage = get_rate_limit_storage()
        storage.get_bucket("key:test-hash", 60, 1.0)
        storage.get_bucket("ip:192.168.1.1", 600, 2.0)
        
        status = RateLimitInfo.get_rate_limit_status(
            api_key_hash="test-hash",
            client_ip="192.168.1.1"
        )
        
        assert "key:test-hash" in status["buckets"]
        assert "ip:192.168.1.1" in status["buckets"]


class TestRateLimitIntegration:
    """Integration tests for rate limiting."""
    
    def setup_method(self):
        """Set up integration test environment."""
        reset_rate_limit_storage()
    
    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self):
        """Test that rate limits are actually enforced."""
        # Create a bucket with very low limit for testing
        storage = get_rate_limit_storage()
        bucket = storage.get_bucket("test:key", capacity=2, refill_rate=0.1)  # Very slow refill
        
        # First request should succeed
        result1 = bucket.consume()
        assert result1.allowed is True
        
        # Second request should succeed
        result2 = bucket.consume()
        assert result2.allowed is True
        
        # Third request should fail
        result3 = bucket.consume()
        assert result3.allowed is False
        assert result3.retry_after > 0
    
    def test_concurrent_access(self):
        """Test that storage handles concurrent access correctly."""
        storage = get_rate_limit_storage()
        
        def consume_tokens():
            bucket = storage.get_bucket("test:concurrent", 100, 10.0)
            return bucket.consume().allowed
        
        # Run multiple threads concurrently
        import threading
        results = []
        threads = []
        
        for _ in range(10):
            thread = threading.Thread(target=lambda: results.append(consume_tokens()))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All should succeed (bucket has enough capacity)
        assert all(results)
        
        # Verify final state (allowing for some refill due to timing)
        bucket = storage.get_bucket("test:concurrent", 100, 10.0)
        assert bucket.tokens <= 90.1  # 10 tokens consumed (plus small refill allowance)
        assert bucket.tokens >= 89.9