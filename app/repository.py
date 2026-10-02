import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

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
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets(category);
CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
"""


class TicketRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA)

    def create(self, message: str, result: TriageResult) -> TicketOut:
        ticket_id = uuid.uuid4().hex[:12]
        status = Status.needs_review if result.needs_human_review else Status.open
        created = datetime.now(timezone.utc)
        with self._conn() as c:
            c.execute(
                "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ticket_id, message, result.category.value, result.priority.value,
                    result.sentiment.value, result.entities.model_dump_json(),
                    result.language, int(result.injection_suspected),
                    int(result.needs_human_review), result.suggested_reply,
                    json.dumps(result.article_ids), status.value, created.isoformat(),
                ),
            )
        return self.get(ticket_id)  # type: ignore[return-value]

    def get(self, ticket_id: str) -> TicketOut | None:
        with self._conn() as c:
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
        with self._conn() as c:
            rows = c.execute(sql, (*params, limit, offset)).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(r: sqlite3.Row) -> TicketOut:
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
            suggested_reply=r["suggested_reply"],
            article_ids=json.loads(r["article_ids"]),
            status=Status(r["status"]),
            created_at=datetime.fromisoformat(r["created_at"]),
        )
