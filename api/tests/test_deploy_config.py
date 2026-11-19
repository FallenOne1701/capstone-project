"""Plan 4a: settings the Railway deploy needs."""

from fastapi.testclient import TestClient

from app import db as dbmod
from app.config import get_settings


def test_cors_origin_list_cleans_entries():
    from app.config import cors_origin_list
    assert cors_origin_list("https://x.vercel.app/ , http://localhost:3000,") == [
        "https://x.vercel.app", "http://localhost:3000"]
    assert cors_origin_list("*") == ["*"]


def _app_with_origins(monkeypatch, db_session, origins):
    monkeypatch.setattr(get_settings(), "cors_origins", origins)
    from app.main import create_app
    app = create_app(init_corpus=False)
    app.dependency_overrides[dbmod.get_db] = lambda: db_session
    return TestClient(app)


def _preflight(c, origin):
    return c.options("/api/desk/queue", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})


def test_listed_origin_allowed_other_refused(monkeypatch, db_session):
    c = _app_with_origins(monkeypatch, db_session, "https://desk.vercel.app/ , http://localhost:3000")
    assert _preflight(c, "https://desk.vercel.app").headers.get("access-control-allow-origin") == "https://desk.vercel.app"
    assert _preflight(c, "http://localhost:3000").headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in _preflight(c, "https://evil.example").headers
    assert c.get("/health").status_code == 200   # no Origin header: health checks and curl still work


def test_default_origins_stay_open(monkeypatch, db_session):
    c = _app_with_origins(monkeypatch, db_session, "*")
    assert _preflight(c, "https://anything.example").headers.get("access-control-allow-origin") in ("*", "https://anything.example")


# Task 2 — /health says whether the Google tool is ready, by name only
def test_google_status_lists_missing_names_only(monkeypatch):
    from app.delivery.mcp_client import google_status
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "")
    monkeypatch.setattr(s, "google_client_secret", "")
    monkeypatch.setattr(s, "google_refresh_token", "SECRET-VALUE")
    monkeypatch.setattr(s, "pulse_doc_id", "")
    st = google_status()
    assert st["ready"] is False
    assert {"GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "PULSE_DOC_ID"} <= set(st["missing"])
    assert "GOOGLE_REFRESH_TOKEN" not in st["missing"]
    assert "SECRET-VALUE" not in str(st)


def test_google_status_flags_missing_node_and_build(monkeypatch, tmp_path):
    from app.delivery.mcp_client import google_status
    s = get_settings()
    monkeypatch.setattr(s, "node_command", "no-such-node-binary")
    monkeypatch.setattr(s, "mcp_server_dir", tmp_path)
    assert {"node", "mcp_build"} <= set(google_status()["missing"])


def test_health_is_200_while_corpus_empty(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok" and set(body["google"]) == {"ready", "missing"}
