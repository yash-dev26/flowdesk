from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.fake import FakeLLM
from app.llm.groq_provider import GroqProvider


def build_provider(settings: Settings) -> LLMProvider:
    name = settings.llm_provider.lower()
    if name == "fake":
        return FakeLLM()
    if name == "groq":
        return GroqProvider(settings.groq_api_key, settings.groq_model,
                            timeout=settings.llm_timeout_seconds)
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
