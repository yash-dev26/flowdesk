import logging

from app.db import connection
from app.schemas import TriageResult
from app.triage.graph import RunStats

log = logging.getLogger("flowdesk.metrics")

SCHEMA = """
CREATE TABLE IF NOT EXISTS request_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    llm_calls INTEGER NOT NULL,
    fallback_used INTEGER NOT NULL,
    needs_human_review INTEGER NOT NULL,
    injection_suspected INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, round(p * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


class MetricsStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with connection(db_path) as c:
            c.executescript(SCHEMA)

    def record(self, ticket_id: str, stats: RunStats, result: TriageResult) -> None:
        log.info(
            "ticket=%s latency_ms=%.0f tokens_in=%d tokens_out=%d cost_usd=%.6f "
            "llm_calls=%d fallback=%s human_review=%s injection=%s",
            ticket_id, stats.latency_ms, stats.prompt_tokens, stats.completion_tokens,
            stats.cost_usd, stats.llm_calls, stats.fallback_used,
            result.needs_human_review, result.injection_suspected)
        with connection(self.db_path) as c:
            c.execute(
                "INSERT INTO request_logs (ticket_id, latency_ms, prompt_tokens, completion_tokens,"
                " cost_usd, llm_calls, fallback_used, needs_human_review, injection_suspected)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (ticket_id, stats.latency_ms, stats.prompt_tokens, stats.completion_tokens,
                 stats.cost_usd, stats.llm_calls, int(stats.fallback_used),
                 int(result.needs_human_review), int(result.injection_suspected)))

    def summary(self) -> dict:
        with connection(self.db_path) as c:
            rows = c.execute("SELECT * FROM request_logs").fetchall()
        n = len(rows)
        lat = sorted(r["latency_ms"] for r in rows)
        cost = sum(r["cost_usd"] for r in rows)
        rate = lambda col: round(sum(r[col] for r in rows) / n, 4) if n else 0.0
        return {
            "total_requests": n,
            "latency_ms": {
                "avg": round(sum(lat) / n, 1) if n else 0.0,
                "p50": round(_percentile(lat, 0.5), 1),
                "p95": round(_percentile(lat, 0.95), 1),
            },
            "tokens": {
                "prompt": sum(r["prompt_tokens"] for r in rows),
                "completion": sum(r["completion_tokens"] for r in rows),
            },
            "llm_calls": sum(r["llm_calls"] for r in rows),
            "estimated_cost_usd": {"total": round(cost, 6),
                                   "avg_per_request": round(cost / n, 6) if n else 0.0},
            "fallback_rate": rate("fallback_used"),
            "human_review_rate": rate("needs_human_review"),
            "injection_rate": rate("injection_suspected"),
        }
