import logging
import random
import time
from typing import Callable

from app.llm.base import LLMError, LLMProvider, LLMRateLimitError, LLMResponse

log = logging.getLogger("flowdesk.llm")


def backoff_delay(attempt: int, base: float, cap: float,
                  retry_after: float | None = None,
                  rand: Callable[[], float] = random.random) -> float:
    """Exponential backoff with full jitter; honours a provider Retry-After."""
    exp = min(cap, base * (2 ** attempt))
    delay = rand() * exp
    if retry_after is not None:
        delay = max(delay, min(retry_after, cap))
    return delay


def call_with_retry(
    provider: LLMProvider,
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    max_retries: int = 2,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs,
) -> LLMResponse:
    """Call the provider, retrying only errors marked `retryable`.

    Raises the last LLMError once retries are exhausted (or immediately for
    non-retryable errors). Callers decide the fallback; this layer never
    swallows a failure silently.
    """
    attempt = 0
    while True:
        try:
            resp = provider.complete(system, user, json_mode=json_mode, **kwargs)
            resp.attempts = attempt + 1
            return resp
        except LLMError as e:
            if not e.retryable or attempt >= max_retries:
                log.warning("llm call failed (%s) after %d attempt(s)", e.code, attempt + 1)
                raise
            retry_after = e.retry_after if isinstance(e, LLMRateLimitError) else None
            delay = backoff_delay(attempt, base_delay, max_delay, retry_after)
            log.info("llm %s, retrying in %.2fs (attempt %d)", e.code, delay, attempt + 1)
            sleep(delay)
            attempt += 1
