"""Bridges our `LLMProvider` (Groq / fake) into LangChain.

Why an adapter instead of `langchain-groq`: the provider abstraction, retry/backoff
and typed errors from `app.llm` stay the single reliability layer, and chains
built with LangChain (prompt | model | parser) get them for free.
"""
import time
from typing import Any, Callable

from langchain_core.callbacks import BaseCallbackHandler, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.outputs import LLMResult

from app.llm.base import LLMProvider
from app.llm.retry import call_with_retry


class ProviderChatModel(BaseChatModel):
    provider: Any  # LLMProvider
    json_mode: bool = True
    max_retries: int = 2
    base_delay: float = 0.5
    max_delay: float = 8.0
    max_tokens: int = 600
    sleep: Callable[[float], None] = time.sleep

    @property
    def _llm_type(self) -> str:
        return f"flowdesk-{getattr(self.provider, 'name', 'provider')}"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        system = "\n\n".join(str(m.content) for m in messages if isinstance(m, SystemMessage))
        user = "\n\n".join(str(m.content) for m in messages if not isinstance(m, SystemMessage))
        resp = call_with_retry(
            self.provider, system, user,
            json_mode=self.json_mode,
            max_retries=self.max_retries,
            base_delay=self.base_delay,
            max_delay=self.max_delay,
            sleep=self.sleep,
            max_tokens=self.max_tokens,
        )
        msg = AIMessage(
            content=resp.text,
            usage_metadata={
                "input_tokens": resp.prompt_tokens,
                "output_tokens": resp.completion_tokens,
                "total_tokens": resp.prompt_tokens + resp.completion_tokens,
            },
        )
        return ChatResult(
            generations=[ChatGeneration(message=msg)],
            llm_output={"model": resp.model, "attempts": resp.attempts},
        )


class UsageCallback(BaseCallbackHandler):
    """Collects token usage and call count across every LLM call in one request."""

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for gens in response.generations:
            for g in gens:
                self.calls += 1
                usage = getattr(getattr(g, "message", None), "usage_metadata", None) or {}
                self.prompt_tokens += usage.get("input_tokens", 0)
                self.completion_tokens += usage.get("output_tokens", 0)
