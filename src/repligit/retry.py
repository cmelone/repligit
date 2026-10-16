import http.client
import logging
import time
import urllib.error
from collections.abc import Callable
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_RETRIES = 3

# rate limited, or gateway/availability errors
RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})


def retry_delay(name: str, attempt: int, retries: int, reason: str) -> float:
    """Calculate the delay for a retry attempt (exponential backoff) and log it."""
    delay = 2**attempt
    log.warning(
        "%s failed, retrying (attempt %d of %d, in %ds): %s",
        name,
        attempt + 1,
        retries,
        delay,
        reason,
    )
    return delay


def retry_reason(e: BaseException) -> str | None:
    """Return why a synchronous (urllib) error is worth retrying, else None."""
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}" if e.code in RETRYABLE_STATUSES else None
    if isinstance(
        e,
        (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.HTTPException,
        ),
    ):
        return repr(e)
    return None


def retry_sync(func: Callable[[], T], retries: int, name: str) -> T:
    """
    Call func() and retry on connection errors, timeouts, and HTTP 429/502/503/504,
    up to `retries` extra attempts with exponential backoff. Applies to all HTTP
    methods.
    """
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            reason = retry_reason(e)
            if reason is None:
                raise
        time.sleep(retry_delay(name, attempt, retries, reason))
    return func()
