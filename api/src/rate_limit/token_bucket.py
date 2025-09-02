"""Token bucket algorithm implementation for rate limiting."""

import time
from typing import NamedTuple
from dataclasses import dataclass


class RateLimitResult(NamedTuple):
    """Result of a rate limit check."""
    allowed: bool
    retry_after: float  # seconds until next allowed request


@dataclass
class TokenBucket:
    """
    Token bucket implementation for rate limiting.
    
    The bucket is filled with tokens at a constant rate up to a maximum capacity.
    Each request consumes one token. If no tokens are available, the request is denied.
    """
    capacity: int  # Maximum number of tokens
    refill_rate: float  # Tokens per second
    tokens: float  # Current number of tokens
    last_refill: float  # Last time tokens were added
    
    def __post_init__(self):
        """Initialize bucket with full capacity."""
        if self.tokens is None:
            self.tokens = float(self.capacity)
        if self.last_refill is None:
            self.last_refill = time.time()
    
    @classmethod
    def create(cls, capacity: int, refill_rate: float) -> "TokenBucket":
        """Create a new token bucket with full capacity."""
        now = time.time()
        return cls(
            capacity=capacity,
            refill_rate=refill_rate,
            tokens=float(capacity),
            last_refill=now
        )
    
    def _refill_tokens(self, now: float) -> None:
        """Refill tokens based on elapsed time."""
        time_elapsed = now - self.last_refill
        tokens_to_add = time_elapsed * self.refill_rate
        
        # Update tokens, capped at capacity
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def consume(self, tokens: int = 1) -> RateLimitResult:
        """
        Attempt to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume (default: 1)
            
        Returns:
            RateLimitResult indicating if request is allowed and retry time
        """
        now = time.time()
        self._refill_tokens(now)
        
        if self.tokens >= tokens:
            # Request allowed
            self.tokens -= tokens
            return RateLimitResult(allowed=True, retry_after=0.0)
        else:
            # Request denied - calculate when next token will be available
            tokens_needed = tokens - self.tokens
            retry_after = tokens_needed / self.refill_rate
            return RateLimitResult(allowed=False, retry_after=retry_after)
    
    def peek(self) -> RateLimitResult:
        """
        Check if a request would be allowed without consuming tokens.
        
        Returns:
            RateLimitResult indicating if request would be allowed
        """
        now = time.time()
        temp_tokens = self.tokens
        temp_last_refill = self.last_refill
        
        # Temporarily refill to check availability
        time_elapsed = now - temp_last_refill
        tokens_to_add = time_elapsed * self.refill_rate
        temp_tokens = min(self.capacity, temp_tokens + tokens_to_add)
        
        if temp_tokens >= 1:
            return RateLimitResult(allowed=True, retry_after=0.0)
        else:
            tokens_needed = 1 - temp_tokens
            retry_after = tokens_needed / self.refill_rate
            return RateLimitResult(allowed=False, retry_after=retry_after)
    
    def get_available_tokens(self) -> float:
        """Get the current number of available tokens."""
        now = time.time()
        self._refill_tokens(now)
        return self.tokens


class RateLimitConfig:
    """Configuration for rate limiting."""
    
    @staticmethod
    def parse_rate_string(rate_str: str) -> tuple[int, float]:
        """
        Parse rate string like '60/m' or '10/s' into capacity and refill rate.
        
        Args:
            rate_str: Rate string in format 'capacity/period'
            
        Returns:
            Tuple of (capacity, refill_rate_per_second)
            
        Raises:
            ValueError: If rate string is invalid
        """
        try:
            capacity_str, period = rate_str.split('/')
            capacity = int(capacity_str)
            
            # Convert period to seconds
            if period == 's':
                period_seconds = 1
            elif period == 'm':
                period_seconds = 60
            elif period == 'h':
                period_seconds = 3600
            elif period.endswith('s'):
                period_seconds = int(period[:-1])
            elif period.endswith('m'):
                period_seconds = int(period[:-1]) * 60
            elif period.endswith('h'):
                period_seconds = int(period[:-1]) * 3600
            else:
                raise ValueError(f"Unknown period format: {period}")
            
            # Calculate refill rate (tokens per second)
            refill_rate = capacity / period_seconds
            
            return capacity, refill_rate
            
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid rate string '{rate_str}': {e}")
    
    @staticmethod
    def parse_rate_limits(rate_limits_str: str) -> dict[str, tuple[int, float]]:
        """
        Parse rate limits configuration string.
        
        Args:
            rate_limits_str: String like "key:60/m,write:10/m,ip:600/5m"
            
        Returns:
            Dictionary mapping limit types to (capacity, refill_rate)
        """
        limits = {}
        
        for limit_spec in rate_limits_str.split(','):
            limit_spec = limit_spec.strip()
            if ':' not in limit_spec:
                continue
                
            limit_type, rate_str = limit_spec.split(':', 1)
            limit_type = limit_type.strip()
            rate_str = rate_str.strip()
            
            capacity, refill_rate = RateLimitConfig.parse_rate_string(rate_str)
            limits[limit_type] = (capacity, refill_rate)
        
        return limits