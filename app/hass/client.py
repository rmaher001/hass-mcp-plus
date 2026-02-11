"""HTTP client management and rate limiting."""

import asyncio
import logging
from typing import Optional

import httpx

from app.config import HA_VERIFY_SSL

logger = logging.getLogger(__name__)

# HTTP client
_client: Optional[httpx.AsyncClient] = None

# Persistent HTTP client with granular timeout configuration
_timeout_config = httpx.Timeout(
    connect=5.0,    # Connection timeout - fail fast on unreachable hosts
    read=30.0,      # Read timeout - allow time for long-running queries (stats, history)
    write=5.0,      # Write timeout - service calls should be quick
    pool=5.0        # Pool timeout - waiting for available connection
)


class RateLimiter:
    """
    Simple async rate limiter using token bucket algorithm.
    Limits requests to max_rate per second.
    """

    def __init__(self, max_rate: float = 10.0):
        """
        Initialize rate limiter.

        Args:
            max_rate: Maximum requests per second (default: 10)
        """
        self.max_rate = max_rate
        self.tokens = max_rate
        self.last_update: float = 0.0  # Will be set on first acquire()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request token is available."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()

            # On first call, just set last_update and use existing tokens
            if self.last_update == 0.0:
                self.last_update = now
            else:
                # Refill tokens based on time passed
                time_passed = now - self.last_update
                self.tokens = min(self.max_rate, self.tokens + time_passed * self.max_rate)
                self.last_update = now

            if self.tokens < 1:
                # Wait for token to become available
                wait_time = (1 - self.tokens) / self.max_rate
                await asyncio.sleep(wait_time)
                # Token is now available after waiting - deduct it
                self.tokens -= 1
            else:
                self.tokens -= 1


# Global rate limiter - 10 requests per second
_rate_limiter = RateLimiter(max_rate=10.0)


async def get_client() -> httpx.AsyncClient:
    """Get a persistent httpx client for Home Assistant API calls"""
    global _client
    if _client is None:
        logger.debug("Creating new HTTP client")
        _client = httpx.AsyncClient(timeout=_timeout_config, verify=HA_VERIFY_SSL)
    return _client


async def cleanup_client() -> None:
    """Close the HTTP client when shutting down"""
    global _client
    if _client:
        logger.debug("Closing HTTP client")
        await _client.aclose()
        _client = None
