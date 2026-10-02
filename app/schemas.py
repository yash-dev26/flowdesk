from datetime import datetime
from enum import Enum

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


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

    @field_validator("order_id", "email", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v):
        # a malformed email from the model is dropped rather than failing the ticket
        return v if v and EMAIL_RE.fullmatch(v) else None


class TriageResult(BaseModel):
    """Final outcome of the triage pipeline, as stored and returned by the API."""

    category: Category
    priority: Priority
    sentiment: Sentiment
    entities: Entities = Field(default_factory=Entities)
    language: str = "unknown"
    injection_suspected: bool = False
    needs_human_review: bool = False
    review_reason: str | None = None
    suggested_reply: str | None = None
    article_ids: list[str] = []


class TicketOut(TriageResult):
    id: str
    message: str
    status: Status
    created_at: datetime


# ---- Shapes the LLM is asked to produce (validated before use) ----

class TriageLLMOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: Category
    priority: Priority
    sentiment: Sentiment
    entities: Entities = Field(default_factory=Entities)
    language: str = "unknown"
    injection_suspected: bool = False
    search_queries: list[str] = Field(default_factory=list)

    @field_validator("category", "priority", "sentiment", mode="before")
    @classmethod
    def _normalise_enum(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("entities", mode="before")
    @classmethod
    def _null_entities(cls, v):
        return {} if v is None else v

    @field_validator("language", mode="before")
    @classmethod
    def _language(cls, v):
        return str(v).strip().lower()[:20] if v else "unknown"

    @field_validator("search_queries", mode="before")
    @classmethod
    def _clean_queries(cls, v):
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            return []
        return [q.strip()[:200] for q in v if isinstance(q, str) and q.strip()][:3]


class ReplyLLMOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answerable: bool
    reply: str = ""
    article_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self):
        if self.answerable and (not self.reply.strip() or not self.article_ids):
            raise ValueError("answerable=true requires a non-empty reply and article_ids")
        return self
