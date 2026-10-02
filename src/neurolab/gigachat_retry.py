"""Small, deterministic retry boundary for transient GigaChat transport limits."""

from __future__ import annotations

from collections.abc import Callable
from time import sleep as _sleep
from typing import TypeVar


T = TypeVar("T")
_RETRYABLE_NAMES = frozenset({"RateLimitError", "TimeoutError", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout"})


class GigaChatRetryError(RuntimeError):
    """A bounded transient retry budget was exhausted without exposing provider data."""


def is_transient_gigachat_error(error: Exception) -> bool:
    """Inspect status/type only, never arbitrary provider bodies or messages."""
    if isinstance(error, GigaChatRetryError) or error.__class__.__name__ in _RETRYABLE_NAMES:
        return True
    response = getattr(error, "response", None)
    status = getattr(error, "status_code", None) or getattr(response, "status_code", None)
    return status in {429, 502, 503, 504}


def run_redacted_cli(main: Callable[[], None], *, component: str) -> None:
    """A stable exit-code protocol for wrappers; do not print raw exceptions."""
    if component not in {"document_card", "diagram_cards", "response_replay", "experimental_spec", "code_candidate"}:
        raise ValueError("unknown CLI component")
    try:
        main()
    except Exception as error:
        import sys
        transient = is_transient_gigachat_error(error)
        category = 'provider_temporarily_unavailable' if transient else {
            'ValidationError':'schema_validation_failure','CodeContractError':'code_contract_failure',
            'LengthFinishReasonError':'provider_output_truncated','AuthenticationError':'provider_authentication_failure',
            'TemporaryUploadCleanupError':'temporary_upload_cleanup_failure',
        }.get(type(error).__name__,'contract_or_runtime_failure')
        print(f"{component}_failed: {category}", file=sys.stderr)
        raise SystemExit(75 if transient else 1) from None


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
            if not is_transient_gigachat_error(error):
                raise
            if attempt == max_retries:
                raise GigaChatRetryError("GigaChat is temporarily unavailable after bounded retry") from None
            sleep(float(2 ** (attempt + 1)))
    raise AssertionError("unreachable")
