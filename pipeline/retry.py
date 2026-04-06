"""Retry with exponential backoff and jitter for transient failures.

Every external call in the engine (Slack API, Docker API, gh CLI, Claude
SDK) should go through this wrapper so transient network blips, rate
limits, and brief service outages are handled uniformly rather than
crashing the session.

Usage::

    from pipeline.retry import retry_on_transient

    @retry_on_transient(max_retries=3, base_delay=1.0)
    def call_slack_api(channel, text):
        client.chat_postMessage(channel=channel, text=text)

    # Or as a context-manager-style wrapper for inline calls:
    result = retry_on_transient(max_retries=3)(lambda: client.chat_postMessage(...))()
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

# Default transient exception classes. Callers can override via the
# `retryable_exceptions` parameter.
_DEFAULT_RETRYABLE = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def retry_on_transient(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple[type[BaseException], ...] = _DEFAULT_RETRYABLE,
    retryable_check: Callable[[BaseException], bool] | None = None,
) -> Callable:
    """Decorator that retries a function on transient errors.

    Args:
        max_retries: Maximum number of retry attempts (0 = no retries).
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Maximum delay between retries (caps the exponential growth).
        retryable_exceptions: Tuple of exception types considered transient.
        retryable_check: Optional callable that receives the exception and
            returns True if it should be retried. Use this for exceptions
            where only certain subtypes are transient (e.g., Slack rate
            limits vs auth errors).

    Returns:
        A decorator that wraps the target function with retry logic.

    Backoff formula:
        delay = min(base_delay * 2^attempt + jitter, max_delay)
        where jitter is uniform [0, base_delay)
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            last_exc: BaseException | None = None

            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except retryable_exceptions as exc:
                    if retryable_check is not None and not retryable_check(exc):
                        raise

                    last_exc = exc

                    if attempt == max_retries:
                        log.warning(
                            "Retry exhausted for %s after %d attempts: %s",
                            getattr(fn, "__qualname__", repr(fn)),
                            max_retries + 1,
                            exc,
                        )
                        raise

                    delay = min(
                        base_delay * (2 ** attempt) + random.uniform(0, base_delay),
                        max_delay,
                    )
                    log.info(
                        "Retrying %s (attempt %d/%d) after %.1fs: %s",
                        getattr(fn, "__qualname__", repr(fn)),
                        attempt + 2,
                        max_retries + 1,
                        delay,
                        exc,
                    )
                    time.sleep(delay)

            # Should not reach here, but defensive.
            if last_exc is not None:
                raise last_exc  # pragma: no cover

        # Preserve function metadata when wrapping real functions.
        # MagicMock and other non-function callables may not have
        # __qualname__, so we guard against AttributeError.
        try:
            wrapper = functools.wraps(fn)(wrapper)
        except (TypeError, AttributeError):
            pass

        return wrapper

    return decorator
