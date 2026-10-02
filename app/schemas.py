from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    billing = "billing"
    technical = "technical"
    account = "account"
    other = "other"


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class Sentiment(str, Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class Status(str, Enum):
    open = "open"
    needs_review = "needs_review"
    resolved = "resolved"


class TicketCreate(BaseModel):
    message: str = Field(..., max_length=20000)

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


class Entities(BaseModel):
    order_id: str | None = None
    email: str | None = None


class TriageResult(BaseModel):
    """What the triage step produces. The real LLM version arrives in Phase 3."""

    category: Category
    priority: Priority
    sentiment: Sentiment
    entities: Entities = Entities()
    language: str = "en"
    injection_suspected: bool = False
    needs_human_review: bool = False
    suggested_reply: str | None = None
    article_ids: list[str] = []


class TicketOut(TriageResult):
    id: str
    message: str
    status: Status
    created_at: datetime
