"""Rate limiting middleware for FastAPI."""

import logging
import time
from typing import Optional, Dict, Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .token_bucket import RateLimitConfig, RateLimitResult
from .storage import get_rate_limit_storage
from ..config import get_settings
from ..errors.problem_details import TooManyRequestsError


logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce rate limiting using token bucket algorithm.
    
    This middleware:
    1. Extracts API key and client IP from requests
    2. Applies appropriate rate limits based on operation type
    3. Returns 429 with Retry-After header when limits exceeded
    4. Logs all rate limiting decisions for observability
    """
    
    def __init__(self, app, skip_paths: Optional[list[str]] = None):
        """
        Initialize rate limiting middleware.
        
        Args:
            app: The FastAPI application
            skip_paths: List of paths to skip rate limiting for
        """
        super().__init__(app)
        self.skip_paths = skip_paths or [
            "/health", "/ready", "/live", "/", "/docs", "/redoc", "/openapi.json"
        ]
        
        # Parse rate limits configuration
        settings = get_settings()
        self.rate_limits = RateLimitConfig.parse_rate_limits(settings.rate_limits)
        self.storage = get_rate_limit_storage()
        
        logger.info(f"Rate limiting initialized with limits: {self.rate_limits}")
    
    async def dispatch(self, request: Request, call_next):
        """Process the request through rate limiting middleware."""
        # Skip rate limiting for certain paths
        if request.url.path in self.skip_paths:
            return await call_next(request)
        
        try:
            # Check rate limits
            limit_result = await self._check_rate_limits(request)
            
            if not limit_result.allowed:
                # Rate limit exceeded
                retry_after = max(1, int(limit_result.retry_after))
                
                logger.warning(
                    "Rate limit exceeded",
                    extra={
                        "client_ip": self._get_client_ip(request),
                        "api_key_hash": self._get_api_key_hash(request),
                        "path": request.url.path,
                        "method": request.method,
                        "retry_after": retry_after
                    }
                )
                
                error = TooManyRequestsError(
                    detail="Rate limit exceeded. Please retry after the specified time.",
                    retry_after=retry_after
                )
                return error.to_response(request)
            
            # Log successful rate limit check
            logger.debug(
                "Rate limit check passed",
                extra={
                    "client_ip": self._get_client_ip(request),
                    "api_key_hash": self._get_api_key_hash(request),
                    "path": request.url.path,
                    "method": request.method
                }
            )
            
        except Exception as e:
            logger.error(f"Error in rate limiting middleware: {e}")
            # Continue request processing on rate limiting errors
            # This ensures the API remains available even if rate limiting fails
        
        return await call_next(request)
    
    async def _check_rate_limits(self, request: Request) -> RateLimitResult:
        """
        Check all applicable rate limits for the request.
        
        Args:
            request: The incoming FastAPI request
            
        Returns:
            RateLimitResult indicating if request should be allowed
        """
        # Get request identifiers
        api_key_hash = self._get_api_key_hash(request)
        client_ip = self._get_client_ip(request)
        is_write_operation = self._is_write_operation(request)
        
        # Check API key rate limits
        if api_key_hash:
            # Check general API key limit
            if "key" in self.rate_limits:
                capacity, refill_rate = self.rate_limits["key"]
                bucket_key = f"key:{api_key_hash}"
                bucket = self.storage.get_bucket(bucket_key, capacity, refill_rate)
                result = bucket.consume()
                
                if not result.allowed:
                    return result
            
            # Check write-specific limit for write operations
            if is_write_operation and "write" in self.rate_limits:
                capacity, refill_rate = self.rate_limits["write"]
                bucket_key = f"write:{api_key_hash}"
                bucket = self.storage.get_bucket(bucket_key, capacity, refill_rate)
                result = bucket.consume()
                
                if not result.allowed:
                    return result
        
        # Check IP-based rate limits (defense in depth)
        if client_ip and "ip" in self.rate_limits:
            capacity, refill_rate = self.rate_limits["ip"]
            bucket_key = f"ip:{client_ip}"
            bucket = self.storage.get_bucket(bucket_key, capacity, refill_rate)
            result = bucket.consume()
            
            if not result.allowed:
                return result
        
        # All rate limits passed
        return RateLimitResult(allowed=True, retry_after=0.0)
    
    def _get_api_key_hash(self, request: Request) -> Optional[str]:
        """
        Extract API key hash from request state.
        
        The API key hash is set by the authentication middleware
        and stored in request.state.
        
        Args:
            request: The FastAPI request
            
        Returns:
            API key hash if available, None otherwise
        """
        # Try to get from request state (set by auth middleware)
        if hasattr(request.state, "api_key_hash"):
            return request.state.api_key_hash
        
        # Fallback: extract from Authorization header and hash
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token:
                # Simple hash for rate limiting purposes
                # Note: This is not cryptographically secure, just for bucketing
                import hashlib
                return hashlib.md5(token.encode()).hexdigest()
        
        return None
    
    def _get_client_ip(self, request: Request) -> Optional[str]:
        """
        Extract client IP address from request.
        
        Handles common proxy headers for proper IP detection.
        
        Args:
            request: The FastAPI request
            
        Returns:
            Client IP address
        """
        # Check for forwarded headers (common in proxy setups)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        if request.client:
            return request.client.host
        
        return None
    
    def _is_write_operation(self, request: Request) -> bool:
        """
        Determine if the request is a write operation.
        
        Write operations typically have stricter rate limits.
        
        Args:
            request: The FastAPI request
            
        Returns:
            True if this is a write operation
        """
        write_methods = {"POST", "PUT", "PATCH", "DELETE"}
        return request.method.upper() in write_methods


class RateLimitInfo:
    """Utility class for rate limit information and debugging."""
    
    @staticmethod
    def get_rate_limit_status(
        api_key_hash: Optional[str] = None,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get current rate limit status for debugging.
        
        Args:
            api_key_hash: API key hash to check
            client_ip: Client IP to check
            
        Returns:
            Dictionary with rate limit information
        """
        storage = get_rate_limit_storage()
        settings = get_settings()
        rate_limits = RateLimitConfig.parse_rate_limits(settings.rate_limits)
        
        status = {
            "timestamp": time.time(),
            "buckets": {},
            "configuration": rate_limits
        }
        
        # Check API key buckets
        if api_key_hash:
            for limit_type in ["key", "write"]:
                if limit_type in rate_limits:
                    bucket_key = f"{limit_type}:{api_key_hash}"
                    bucket_info = storage.get_bucket_info(bucket_key)
                    if bucket_info:
                        status["buckets"][bucket_key] = bucket_info
        
        # Check IP bucket
        if client_ip:
            bucket_key = f"ip:{client_ip}"
            bucket_info = storage.get_bucket_info(bucket_key)
            if bucket_info:
                status["buckets"][bucket_key] = bucket_info
        
        return status