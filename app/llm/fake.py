"""Deterministic provider for tests and the demo's failure case.

Script it with a list of outputs; each call pops the next one. A string is
returned as the model text, an Exception instance is raised. When the script
is empty it falls back to `default`.
"""
from collections import deque

from app.llm.base import LLMResponse


class FakeLLM:
    name = "fake"

    def __init__(self, script: list[str | Exception] | None = None,
                 default: str | Exception = "{}"):
        self._script = deque(script or [])
        self.default = default
        self.calls: list[dict] = []

    def complete(self, system: str, user: str, *, json_mode: bool = False,
                 temperature: float = 0.0, max_tokens: int = 600) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        item = self._script.popleft() if self._script else self.default
        if isinstance(item, Exception):
            raise item
        return LLMResponse(
            text=item,
            prompt_tokens=(len(system) + len(user)) // 4,
            completion_tokens=len(item) // 4,
            model="fake",
            latency_ms=1.0,
        )
