"""Small, deterministic retry boundary for transient GigaChat transport limits."""

from __future__ import annotations

from collections.abc import Callable
from time import sleep as _sleep
from typing import TypeVar


T = TypeVar("T")
_RETRYABLE_NAMES = frozenset({"RateLimitError", "TimeoutError", "ConnectTimeout"})


class GigaChatRetryError(RuntimeError):
    """A bounded transient retry budget was exhausted without exposing provider data."""


def bounded_gigachat_call(
    call: Callable[[], T], *, max_retries: int = 2, sleep: Callable[[float], None] = _sleep
) -> T:
    """Retry only transient limit/timeout failures with short deterministic waits."""
    if not 0 <= max_retries <= 2:
        raise ValueError("max_retries must be between zero and two")
    for attempt in range(max_retries + 1):
        try:
            return call()
        except Exception as error:
            if error.__class__.__name__ not in _RETRYABLE_NAMES:
                raise
            if attempt == max_retries:
                raise GigaChatRetryError("GigaChat is temporarily unavailable after bounded retry") from None
            sleep(float(2 ** (attempt + 1)))
    raise AssertionError("unreachable")
