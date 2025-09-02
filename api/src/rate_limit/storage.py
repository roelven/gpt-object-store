"""In-memory storage for rate limiting state."""

import threading
import time
from typing import Dict, Optional
from .token_bucket import TokenBucket


class RateLimitStorage:
    """
    Thread-safe in-memory storage for rate limiting buckets.
    
    Maintains separate buckets for different rate limit types and keys.
    Automatically cleans up expired buckets to prevent memory leaks.
    """
    
    def __init__(self, cleanup_interval: int = 300):  # 5 minutes
        """
        Initialize storage with optional cleanup interval.
        
        Args:
            cleanup_interval: Seconds between cleanup runs (default: 300)
        """
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.RLock()
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
    
    def _cleanup_expired_buckets(self) -> None:
        """Remove buckets that haven't been used recently."""
        now = time.time()
        
        # Only cleanup if enough time has passed
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        expired_keys = []
        cutoff_time = now - (self._cleanup_interval * 2)  # Keep buckets for 2x cleanup interval
        
        for key, bucket in self._buckets.items():
            # Remove buckets that haven't been accessed recently and are empty
            if bucket.last_refill < cutoff_time and bucket.tokens >= bucket.capacity * 0.9:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._buckets[key]
        
        self._last_cleanup = now
    
    def get_bucket(self, key: str, capacity: int, refill_rate: float) -> TokenBucket:
        """
        Get or create a token bucket for the given key.
        
        Args:
            key: Unique identifier for the bucket
            capacity: Maximum tokens in bucket
            refill_rate: Tokens per second refill rate
            
        Returns:
            TokenBucket instance for the key
        """
        with self._lock:
            self._cleanup_expired_buckets()
            
            if key not in self._buckets:
                self._buckets[key] = TokenBucket.create(capacity, refill_rate)
            else:
                # Update bucket parameters if they've changed
                bucket = self._buckets[key]
                if bucket.capacity != capacity or bucket.refill_rate != refill_rate:
                    # Create new bucket with updated parameters, preserving some tokens
                    old_ratio = bucket.tokens / bucket.capacity if bucket.capacity > 0 else 1.0
                    new_tokens = min(capacity, capacity * old_ratio)
                    
                    self._buckets[key] = TokenBucket(
                        capacity=capacity,
                        refill_rate=refill_rate,
                        tokens=new_tokens,
                        last_refill=bucket.last_refill
                    )
            
            return self._buckets[key]
    
    def remove_bucket(self, key: str) -> bool:
        """
        Remove a bucket from storage.
        
        Args:
            key: Bucket key to remove
            
        Returns:
            True if bucket was removed, False if not found
        """
        with self._lock:
            return self._buckets.pop(key, None) is not None
    
    def clear_all(self) -> None:
        """Clear all buckets from storage."""
        with self._lock:
            self._buckets.clear()
    
    def get_bucket_count(self) -> int:
        """Get the current number of buckets in storage."""
        with self._lock:
            return len(self._buckets)
    
    def get_bucket_info(self, key: str) -> Optional[Dict[str, float]]:
        """
        Get information about a specific bucket.
        
        Args:
            key: Bucket key
            
        Returns:
            Dictionary with bucket info or None if not found
        """
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return None
            
            # Update tokens before reporting
            now = time.time()
            bucket._refill_tokens(now)
            
            return {
                "capacity": bucket.capacity,
                "refill_rate": bucket.refill_rate,
                "tokens": bucket.tokens,
                "last_refill": bucket.last_refill
            }


# Global storage instance
_storage_instance: Optional[RateLimitStorage] = None
_storage_lock = threading.Lock()


def get_rate_limit_storage() -> RateLimitStorage:
    """Get the global rate limit storage instance."""
    global _storage_instance
    
    if _storage_instance is None:
        with _storage_lock:
            if _storage_instance is None:
                _storage_instance = RateLimitStorage()
    
    return _storage_instance


def reset_rate_limit_storage() -> None:
    """Reset the global storage instance (useful for testing)."""
    global _storage_instance
    
    with _storage_lock:
        if _storage_instance is not None:
            _storage_instance.clear_all()
        _storage_instance = None