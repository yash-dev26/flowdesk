"""Demo-only helpers (enabled with DEMO_MODE=true): inject LLM failures on demand."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.llm.base import LLMProvider, LLMRateLimitError, LLMResponse, LLMServerError, LLMTimeoutError

MODES = ("off", "timeout", "rate_limit", "server_error", "invalid_json")


class FaultInjectingProvider:
    """Wraps the real provider so failures travel through the real retry/fallback path."""

    name = "fault-injector"

    def __init__(self, inner: LLMProvider):
        self.inner, self.mode = inner, "off"

    def complete(self, system: str, user: str, **kw) -> LLMResponse:
        if self.mode == "timeout":
            raise LLMTimeoutError("simulated timeout")
        if self.mode == "rate_limit":
            raise LLMRateLimitError("simulated 429")
        if self.mode == "server_error":
            raise LLMServerError("simulated provider outage")
        if self.mode == "invalid_json":
            return LLMResponse(text="Sorry, I can't help with that.", model="simulated")
        return self.inner.complete(system, user, **kw)


class FaultBody(BaseModel):
    mode: str


router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/fault")
def get_fault(request: Request):
    return {"mode": request.app.state.llm.mode, "modes": MODES}


@router.post("/fault")
def set_fault(body: FaultBody, request: Request):
    if body.mode not in MODES:
        raise HTTPException(422, f"mode must be one of {', '.join(MODES)}")
    request.app.state.llm.mode = body.mode
    return {"mode": body.mode}


@router.get("/kb")
def kb(request: Request):
    return [{"id": d.metadata["id"], "title": d.metadata["title"]} for d in request.app.state.kb_articles]
