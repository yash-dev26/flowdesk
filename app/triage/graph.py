"""LangGraph workflow for one ticket.

    screen -> triage -> retrieve -> reply -> finalize
                 |          |__________________^   (no relevant article: skip reply)
                 |_________________________________^   (triage failed: skip retrieval)

Every LLM step is a LangChain chain (prompt | model | PydanticOutputParser). The graph
itself never raises: each node degrades to "needs human review" with a reason.
"""
import logging
import time
from dataclasses import dataclass
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.vectorstores import VectorStore
from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.llm.base import LLMError, LLMProvider
from app.llm.langchain_adapter import ProviderChatModel, UsageCallback
from app.schemas import (
    Category, Entities, Priority, ReplyLLMOutput, Sentiment, TriageLLMOutput, TriageResult,
)
from app.triage import prompts
from app.triage.security import (
    detect_injection, reconcile_entities, reply_claims_action, sanitize,
)

log = logging.getLogger("flowdesk.triage")


class TriageState(TypedDict, total=False):
    message: str
    safe_message: str
    injection_flags: list[str]
    triage: TriageLLMOutput | None
    docs: list[tuple[Document, float]]
    reply: str | None
    article_ids: list[str]
    review_reasons: list[str]
    fallback_used: bool
    result: TriageResult


@dataclass
class RunStats:
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0
    fallback_used: bool = False


@dataclass
class PipelineOutput:
    result: TriageResult
    stats: RunStats


class TriagePipeline:
    def __init__(self, provider: LLMProvider, vectorstore: VectorStore | None, settings: Settings,
                 sleep=time.sleep):
        self.vectorstore = vectorstore
        self.settings = settings
        model = ProviderChatModel(
            provider=provider, json_mode=True,
            max_retries=settings.llm_max_retries,
            base_delay=settings.llm_base_delay_seconds,
            max_delay=settings.llm_max_delay_seconds,
            sleep=sleep,
        )
        self.triage_chain, self.triage_repair = self._chains(
            model, prompts.TRIAGE_SYSTEM, prompts.TRIAGE_HUMAN, TriageLLMOutput)
        self.reply_chain, self.reply_repair = self._chains(
            model, prompts.REPLY_SYSTEM, prompts.REPLY_HUMAN, ReplyLLMOutput)
        self.graph = self._build_graph()

    # ---------- chains ----------

    @staticmethod
    def _chains(model, system: str, human: str, schema):
        parser = PydanticOutputParser(pydantic_object=schema)
        main = ChatPromptTemplate.from_messages([("system", system), ("human", human)]) | model | parser
        repair = ChatPromptTemplate.from_messages(
            [("system", system), ("human", human + prompts.REPAIR_SUFFIX)]) | model | parser
        return main, repair

    @staticmethod
    def _invoke_with_repair(chain, repair_chain, inputs: dict, config: RunnableConfig):
        """Validate the model output; on invalid JSON/schema retry once with the error fed back."""
        try:
            return chain.invoke(inputs, config)
        except OutputParserException as e:
            log.info("invalid model output, attempting one repair: %s", str(e)[:200])
            return repair_chain.invoke(
                {**inputs, "error": str(e)[:400], "bad_output": (e.llm_output or "")[:1500]}, config)

    # ---------- graph ----------

    def _build_graph(self):
        g = StateGraph(TriageState)
        g.add_node("screen", self._screen)
        g.add_node("triage", self._triage)
        g.add_node("retrieve", self._retrieve)
        g.add_node("reply", self._reply)
        g.add_node("finalize", self._finalize)
        g.add_edge(START, "screen")
        g.add_edge("screen", "triage")
        g.add_conditional_edges(
            "triage", lambda s: "retrieve" if s.get("triage") else "finalize",
            {"retrieve": "retrieve", "finalize": "finalize"})
        g.add_conditional_edges(
            "retrieve", lambda s: "reply" if s.get("docs") else "finalize",
            {"reply": "reply", "finalize": "finalize"})
        g.add_edge("reply", "finalize")
        g.add_edge("finalize", END)
        return g.compile()

    def _screen(self, state: TriageState) -> dict:
        flags = detect_injection(state["message"])
        if flags:
            log.warning("prompt injection heuristics matched: %s", flags)
        return {"safe_message": sanitize(state["message"]), "injection_flags": flags,
                "review_reasons": []}

    def _triage(self, state: TriageState, config: RunnableConfig) -> dict:
        try:
            out = self._invoke_with_repair(
                self.triage_chain, self.triage_repair, {"message": state["safe_message"]}, config)
        except (LLMError, OutputParserException) as e:
            log.warning("triage failed, using fallback: %s", e)
            return {"triage": None, "fallback_used": True,
                    "review_reasons": state["review_reasons"] + ["triage_failed"]}
        out.entities = reconcile_entities(out.entities, state["message"])
        return {"triage": out}

    def _retrieve(self, state: TriageState) -> dict:
        reasons = list(state["review_reasons"])
        if self.vectorstore is None:
            return {"docs": [], "review_reasons": reasons + ["kb_unavailable"]}
        queries = state["triage"].search_queries or [state["safe_message"][:300]]
        best: dict[str, tuple[Document, float]] = {}
        try:
            for q in queries:
                for doc, score in self.vectorstore.similarity_search_with_score(
                        q, k=self.settings.retrieval_top_k):
                    if score >= self.settings.retrieval_min_score and \
                            score > best.get(doc.metadata["id"], (None, -1.0))[1]:
                        best[doc.metadata["id"]] = (doc, float(score))
        except Exception as e:  # embedding/vector store failure must not break the ticket
            log.exception("retrieval failed: %s", e)
            return {"docs": [], "review_reasons": reasons + ["retrieval_failed"]}
        docs = sorted(best.values(), key=lambda x: x[1], reverse=True)[: self.settings.retrieval_top_k]
        if not docs:
            reasons.append("no_relevant_article")
        return {"docs": docs, "review_reasons": reasons}

    def _reply(self, state: TriageState, config: RunnableConfig) -> dict:
        reasons = list(state["review_reasons"])
        articles = "\n\n".join(
            f"[id: {d.metadata['id']}]\n{d.page_content}" for d, _ in state["docs"])
        try:
            out = self._invoke_with_repair(
                self.reply_chain, self.reply_repair,
                {"articles": articles, "message": state["safe_message"]}, config)
        except (LLMError, OutputParserException) as e:
            log.warning("reply generation failed: %s", e)
            return {"reply": None, "article_ids": [], "review_reasons": reasons + ["reply_failed"]}

        allowed = {d.metadata["id"] for d, _ in state["docs"]}
        if not out.answerable:
            reasons.append("no_relevant_article")
        elif not set(out.article_ids) <= allowed:
            log.warning("reply cited unknown articles %s", set(out.article_ids) - allowed)
            reasons.append("reply_not_grounded")
        elif reply_claims_action(out.reply):
            log.warning("reply claimed an action; discarded")
            reasons.append("reply_claims_action")
        else:
            return {"reply": out.reply.strip(), "article_ids": list(dict.fromkeys(out.article_ids))}
        return {"reply": None, "article_ids": [], "review_reasons": reasons}

    def _finalize(self, state: TriageState) -> dict:
        t = state.get("triage")
        reasons = list(state["review_reasons"])
        injection = bool(state["injection_flags"]) or bool(t and t.injection_suspected)
        if injection:
            reasons.append("injection_suspected")
        result = TriageResult(
            category=t.category if t else Category.other,
            priority=t.priority if t else Priority.medium,
            sentiment=t.sentiment if t else Sentiment.neutral,
            entities=t.entities if t else reconcile_entities(Entities(), state["message"]),
            language=t.language if t else "unknown",
            injection_suspected=injection,
            needs_human_review=bool(reasons),
            review_reason=",".join(dict.fromkeys(reasons)) or None,
            suggested_reply=state.get("reply"),
            article_ids=state.get("article_ids", []),
        )
        return {"result": result}

    # ---------- public ----------

    def run(self, message: str) -> PipelineOutput:
        usage = UsageCallback()
        start = time.perf_counter()
        try:
            final = self.graph.invoke({"message": message}, config={"callbacks": [usage]})
            result, fallback = final["result"], bool(final.get("fallback_used"))
        except Exception:  # last line of defence: the API must never crash on a ticket
            log.exception("triage pipeline crashed; returning safe fallback")
            result = TriageResult(
                category=Category.other, priority=Priority.medium, sentiment=Sentiment.neutral,
                injection_suspected=bool(detect_injection(message)),
                needs_human_review=True, review_reason="pipeline_error")
            fallback = True
        s = self.settings
        cost = (usage.prompt_tokens * s.price_per_1m_input_usd
                + usage.completion_tokens * s.price_per_1m_output_usd) / 1_000_000
        stats = RunStats(
            latency_ms=(time.perf_counter() - start) * 1000,
            prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens,
            cost_usd=cost, llm_calls=usage.calls, fallback_used=fallback)
        return PipelineOutput(result, stats)
