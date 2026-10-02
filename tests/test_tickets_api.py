import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(Settings(db_path=str(tmp_path / "t.db")))
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
