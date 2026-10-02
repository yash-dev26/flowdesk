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
CREATE INDEX IF NOT EXISTS idx_request_logs_latency ON request_logs(latency_ms);
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
            totals = c.execute(
                "SELECT COUNT(*) AS n, "
                "COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens, "
                "COALESCE(SUM(completion_tokens), 0) AS completion_tokens, "
                "COALESCE(SUM(llm_calls), 0) AS llm_calls, "
                "COALESCE(SUM(cost_usd), 0) AS cost_usd, "
                "COALESCE(SUM(fallback_used), 0) AS fallback_used, "
                "COALESCE(SUM(needs_human_review), 0) AS needs_human_review, "
                "COALESCE(SUM(injection_suspected), 0) AS injection_suspected, "
                "COALESCE(AVG(latency_ms), 0) AS avg_latency_ms "
                "FROM request_logs"
            ).fetchone()
            n = totals["n"]

            def percentile(p: float) -> float:
                if not n:
                    return 0.0
                idx = min(n - 1, max(0, round(p * (n - 1))))
                row = c.execute(
                    "SELECT latency_ms FROM request_logs "
                    "ORDER BY latency_ms LIMIT 1 OFFSET ?", (idx,)).fetchone()
                return round(row["latency_ms"], 1)

            p50 = percentile(0.5)
            p95 = percentile(0.95)

        rate = lambda col: round(totals[col] / n, 4) if n else 0.0
        return {
            "total_requests": n,
            "latency_ms": {
                "avg": round(totals["avg_latency_ms"], 1),
                "p50": p50,
                "p95": p95,
            },
            "tokens": {
                "prompt": totals["prompt_tokens"],
                "completion": totals["completion_tokens"],
            },
            "llm_calls": totals["llm_calls"],
            "estimated_cost_usd": {"total": round(totals["cost_usd"], 6),
                                   "avg_per_request": round(totals["cost_usd"] / n, 6) if n else 0.0},
            "fallback_rate": rate("fallback_used"),
            "human_review_rate": rate("needs_human_review"),
            "injection_rate": rate("injection_suspected"),
        }
