import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(Settings(db_path=str(tmp_path / "t.db"), llm_provider="fake", embedding_provider="hashing", retrieval_min_score=0.2))
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_get_ticket(client):
    r = client.post("/tickets", json={"message": "  I was charged twice  "})
    assert r.status_code == 201
    body = r.json()
    assert body["message"] == "I was charged twice"
    assert body["status"] == "needs_review"
    fetched = client.get(f"/tickets/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_blank_message_rejected(client):
    assert client.post("/tickets", json={"message": "   "}).status_code == 422


def test_unknown_ticket_404(client):
    assert client.get("/tickets/nope").status_code == 404


def test_list_filters(client):
    client.post("/tickets", json={"message": "one"})
    client.post("/tickets", json={"message": "two"})
    assert len(client.get("/tickets").json()) == 2
    assert len(client.get("/tickets?category=other").json()) == 2
    assert client.get("/tickets?category=billing").json() == []
    assert client.get("/tickets?status=resolved").json() == []
    assert client.get("/tickets?priority=bogus").status_code == 422


def test_metrics_endpoint_reflects_requests(client):
    assert client.get("/metrics").json()["total_requests"] == 0
    client.post("/tickets", json={"message": "hello"})  # fake LLM returns "{}" -> safe fallback
    m = client.get("/metrics").json()
    assert m["total_requests"] == 1
    assert m["fallback_rate"] == 1.0 and m["human_review_rate"] == 1.0
    assert set(m) >= {"latency_ms", "tokens", "estimated_cost_usd", "injection_rate"}


def test_ticket_exposes_review_reason(client):
    t = client.post("/tickets", json={"message": "hello"}).json()
    assert t["needs_human_review"] and t["review_reason"] == "triage_failed"
