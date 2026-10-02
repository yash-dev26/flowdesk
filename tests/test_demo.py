import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make(tmp_path, demo):
    s = Settings(db_path=str(tmp_path / "t.db"), llm_provider="fake", embedding_provider="hashing",
                 demo_mode=demo, llm_base_delay_seconds=0.0)
    return TestClient(create_app(s))


def test_index_and_static_served(tmp_path):
    c = make(tmp_path, False)
    assert "Flowdesk triage console" in c.get("/").text
    assert c.get("/static/app.js").status_code == 200


def test_demo_routes_hidden_when_disabled(tmp_path):
    assert make(tmp_path, False).get("/demo/fault").status_code == 404


@pytest.mark.parametrize("mode", ["timeout", "rate_limit", "server_error", "invalid_json"])
def test_injected_failures_fall_back_cleanly(tmp_path, mode):
    c = make(tmp_path, True)
    assert c.post("/demo/fault", json={"mode": mode}).json()["mode"] == mode
    r = c.post("/tickets", json={"message": "I was charged twice"})
    assert r.status_code == 201 and r.json()["review_reason"] == "triage_failed"
    c.post("/demo/fault", json={"mode": "off"})
    assert c.get("/metrics").json()["fallback_rate"] == 1.0


def test_unknown_fault_mode_rejected_and_kb_listed(tmp_path):
    c = make(tmp_path, True)
    assert c.post("/demo/fault", json={"mode": "nope"}).status_code == 422
    assert len(c.get("/demo/kb").json()) >= 10
