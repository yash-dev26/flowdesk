import json
import uuid
from datetime import datetime, timezone

from app.db import connection
from app.schemas import (
    Category, Entities, Priority, Sentiment, Status, TicketOut, TriageResult,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    message TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    entities TEXT NOT NULL,
    language TEXT NOT NULL,
    injection_suspected INTEGER NOT NULL,
    needs_human_review INTEGER NOT NULL,
    suggested_reply TEXT,
    article_ids TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    review_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category);
CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
"""


class TicketRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with connection(db_path) as c:
            c.executescript(SCHEMA)
            # tiny migration for DBs created before review_reason existed
            cols = {r["name"] for r in c.execute("PRAGMA table_info(tickets)")}
            if "review_reason" not in cols:
                c.execute("ALTER TABLE tickets ADD COLUMN review_reason TEXT")

    def create(self, message: str, result: TriageResult) -> TicketOut:
        ticket_id = uuid.uuid4().hex[:12]
        status = Status.needs_review if result.needs_human_review else Status.open
        row = {
            "id": ticket_id,
            "message": message,
            "category": result.category.value,
            "priority": result.priority.value,
            "sentiment": result.sentiment.value,
            "entities": result.entities.model_dump_json(),
            "language": result.language,
            "injection_suspected": int(result.injection_suspected),
            "needs_human_review": int(result.needs_human_review),
            "suggested_reply": result.suggested_reply,
            "article_ids": json.dumps(result.article_ids),
            "status": status.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "review_reason": result.review_reason,
        }
        cols = ", ".join(row)
        marks = ", ".join(f":{k}" for k in row)
        with connection(self.db_path) as c:
            c.execute(f"INSERT INTO tickets ({cols}) VALUES ({marks})", row)
        return self.get(ticket_id)  # type: ignore[return-value]

    def get(self, ticket_id: str) -> TicketOut | None:
        with connection(self.db_path) as c:
            row = c.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return self._row(row) if row else None

    def list(
        self,
        category: Category | None = None,
        priority: Priority | None = None,
        status: Status | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TicketOut]:
        clauses, params = [], []
        for col, val in (("category", category), ("priority", priority), ("status", status)):
            if val is not None:
                clauses.append(f"{col} = ?")
                params.append(val.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM tickets {where} ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?"
        with connection(self.db_path) as c:
            rows = c.execute(sql, (*params, limit, offset)).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(r) -> TicketOut:
        return TicketOut(
            id=r["id"],
            message=r["message"],
            category=Category(r["category"]),
            priority=Priority(r["priority"]),
            sentiment=Sentiment(r["sentiment"]),
            entities=Entities.model_validate_json(r["entities"]),
            language=r["language"],
            injection_suspected=bool(r["injection_suspected"]),
            needs_human_review=bool(r["needs_human_review"]),
            review_reason=r["review_reason"],
            suggested_reply=r["suggested_reply"],
            article_ids=json.loads(r["article_ids"]),
            status=Status(r["status"]),
            created_at=datetime.fromisoformat(r["created_at"]),
        )
