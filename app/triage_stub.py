"""Placeholder triage used until the LLM pipeline lands (Phase 3).

It is deliberately conservative: everything goes to human review, so the API
shape can be settled and tested without any model dependency.
"""
from app.schemas import Category, Priority, Sentiment, TriageResult


def triage(message: str) -> TriageResult:
    return TriageResult(
        category=Category.other,
        priority=Priority.medium,
        sentiment=Sentiment.neutral,
        needs_human_review=True,
    )
