"""Provider-agnostic LLM interface and a typed error hierarchy.

The rest of the app only ever sees `LLMProvider` and `LLMError` subclasses, so
swapping Groq for another provider (or a fake in tests) touches one file.
"""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    latency_ms: float = 0.0
    attempts: int = 1


class LLMError(Exception):
    """Base class. `retryable` tells the retry wrapper whether to try again."""

    retryable = False
    code = "llm_error"


class LLMTimeoutError(LLMError):
    retryable = True
    code = "llm_timeout"


class LLMRateLimitError(LLMError):
    retryable = True
    code = "llm_rate_limited"

    def __init__(self, message: str = "rate limited", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMServerError(LLMError):
    retryable = True
    code = "llm_server_error"


class LLMBadRequestError(LLMError):
    """4xx other than 429: retrying the same request will not help."""

    code = "llm_bad_request"


class LLMAuthError(LLMError):
    code = "llm_auth_error"


class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int = 600,
    ) -> LLMResponse: ...
