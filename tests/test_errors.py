import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(Settings(db_path=str(tmp_path / "t.db"), llm_provider="fake", embedding_provider="hashing", retrieval_min_score=0.2))

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_error_is_clean_json(client):
    r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret" not in r.text


def test_validation_error_shape(client):
    r = client.post("/tickets", json={"message": "  "})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_not_found_shape(client):
    r = client.get("/tickets/missing")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
