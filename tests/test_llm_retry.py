import httpx
import pytest

from app.llm.base import (
    LLMAuthError, LLMBadRequestError, LLMRateLimitError, LLMServerError, LLMTimeoutError,
)
from app.llm.fake import FakeLLM
from app.llm.groq_provider import GroqProvider
from app.llm.retry import backoff_delay, call_with_retry


def run(fake, **kw):
    sleeps: list[float] = []
    resp = call_with_retry(fake, "sys", "user", sleep=sleeps.append, **kw)
    return resp, sleeps


def test_success_first_try():
    resp, sleeps = run(FakeLLM(["ok"]))
    assert resp.text == "ok" and resp.attempts == 1 and sleeps == []


def test_retries_timeout_then_succeeds():
    fake = FakeLLM([LLMTimeoutError("t"), "ok"])
    resp, sleeps = run(fake)
    assert resp.text == "ok" and resp.attempts == 2 and len(sleeps) == 1


def test_retries_rate_limit_and_server_error():
    fake = FakeLLM([LLMRateLimitError(), LLMServerError("x"), "ok"])
    resp, sleeps = run(fake, max_retries=2)
    assert resp.attempts == 3 and len(sleeps) == 2


def test_gives_up_after_max_retries():
    fake = FakeLLM([LLMTimeoutError("t")] * 5)
    with pytest.raises(LLMTimeoutError):
        run(fake, max_retries=2)
    assert len(fake.calls) == 3  # first try + 2 retries


@pytest.mark.parametrize("err", [LLMBadRequestError("b"), LLMAuthError("a")])
def test_does_not_retry_non_retryable(err):
    fake = FakeLLM([err, "ok"])
    with pytest.raises(type(err)):
        run(fake)
    assert len(fake.calls) == 1


def test_backoff_grows_and_is_capped():
    no_jitter = lambda: 1.0
    assert backoff_delay(0, 0.5, 8, rand=no_jitter) == 0.5
    assert backoff_delay(2, 0.5, 8, rand=no_jitter) == 2.0
    assert backoff_delay(10, 0.5, 8, rand=no_jitter) == 8.0


def test_backoff_honours_retry_after():
    assert backoff_delay(0, 0.5, 8, retry_after=3.0, rand=lambda: 0.0) == 3.0
    assert backoff_delay(0, 0.5, 8, retry_after=99, rand=lambda: 0.0) == 8.0


def groq(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GroqProvider("key", "m", client=client)


def test_groq_parses_success_and_usage():
    def handler(req):
        return httpx.Response(200, json={
            "model": "m",
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        })
    r = groq(handler).complete("s", "u", json_mode=True)
    assert (r.text, r.prompt_tokens, r.completion_tokens) == ("hi", 7, 3)


def test_groq_maps_http_errors():
    cases = {429: LLMRateLimitError, 500: LLMServerError, 401: LLMAuthError, 400: LLMBadRequestError}
    for status, exc in cases.items():
        p = groq(lambda req, s=status: httpx.Response(s, headers={"retry-after": "2"}))
        with pytest.raises(exc):
            p.complete("s", "u")


def test_groq_maps_timeout_and_garbage():
    def boom(req):
        raise httpx.ReadTimeout("slow")
    with pytest.raises(LLMTimeoutError):
        groq(boom).complete("s", "u")
    with pytest.raises(LLMServerError):
        groq(lambda req: httpx.Response(200, json={"nope": 1})).complete("s", "u")


def test_groq_missing_key_fails_per_call_not_at_startup():
    provider = GroqProvider("", "m")  # must not raise here
    with pytest.raises(LLMAuthError):
        provider.complete("s", "u")
