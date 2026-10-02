import time

import httpx

from app.llm.base import (
    LLMAuthError, LLMBadRequestError, LLMError, LLMRateLimitError,
    LLMResponse, LLMServerError, LLMTimeoutError,
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    """Thin httpx client for Groq's OpenAI-compatible chat endpoint.

    No SDK on purpose: fewer dependencies, and every failure mode is mapped
    to our own error types in one place (`_raise_for_status`).
    """

    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float = 15.0,
                 client: httpx.Client | None = None):
        self.model = model
        self._key = api_key
        self._client = client or httpx.Client(timeout=timeout)

    def complete(self, system: str, user: str, *, json_mode: bool = False,
                 temperature: float = 0.0, max_tokens: int = 600) -> LLMResponse:
        if not self._key:
            # Raised per call (not at startup) so the API still boots without a
            # key and the triage fallback path handles it like any other failure.
            raise LLMAuthError("GROQ_API_KEY is not set")
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        start = time.perf_counter()
        try:
            r = self._client.post(
                GROQ_URL, json=payload,
                headers={"Authorization": f"Bearer {self._key}"},
            )
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(str(e) or "request timed out") from e
        except httpx.HTTPError as e:
            raise LLMServerError(f"network error: {e}") from e

        self._raise_for_status(r)
        try:
            data = r.json()
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise LLMServerError("malformed response from provider") from e

        return LLMResponse(
            text=text,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            model=data.get("model", self.model),
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    @staticmethod
    def _raise_for_status(r: httpx.Response) -> None:
        if r.status_code < 400:
            return
        if r.status_code == 429:
            ra = r.headers.get("retry-after")
            try:
                retry_after = float(ra) if ra else None
            except ValueError:
                retry_after = None
            raise LLMRateLimitError("rate limited by provider", retry_after)
        if r.status_code in (401, 403):
            raise LLMAuthError(f"auth failed ({r.status_code})")
        if r.status_code >= 500:
            raise LLMServerError(f"provider error ({r.status_code})")
        raise LLMBadRequestError(f"bad request ({r.status_code})")
