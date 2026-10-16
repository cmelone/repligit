import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import aiohttp

from repligit.retry import RETRYABLE_STATUSES, retry_delay

log = logging.getLogger(__name__)

T = TypeVar("T")


def retry_reason(e: BaseException) -> str | None:
    """Return why an aiohttp error is worth retrying, else None."""
    if isinstance(e, aiohttp.ClientResponseError):
        return f"HTTP {e.status}" if e.status in RETRYABLE_STATUSES else None
    if isinstance(
        e,
        (
            aiohttp.ClientConnectionError,
            aiohttp.ClientPayloadError,
            asyncio.TimeoutError,
            asyncio.IncompleteReadError,
        ),
    ):
        return repr(e)
    return None


async def retry_async(func: Callable[[], Awaitable[T]], retries: int, name: str) -> T:
    """
    Await func() and retry on connection errors, timeouts, and HTTP 429/502/503/504,
    up to `retries` extra attempts with exponential backoff. Applies to all HTTP
    methods.
    """
    for attempt in range(retries):
        try:
            return await func()
        except Exception as e:
            reason = retry_reason(e)
            if reason is None:
                raise
        await asyncio.sleep(retry_delay(name, attempt, retries, reason))
    return await func()
