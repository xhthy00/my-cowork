from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.industry_auth import IndustryAppAuthMiddleware


def client():
    app = FastAPI()
    app.add_middleware(IndustryAppAuthMiddleware)

    @app.get("/health")
    @app.get("/api/chat")
    @app.post("/api/tool/confirm/call")
    def endpoint():
        return {"ok": True}

    return TestClient(app)


def test_host_token_is_required_for_existing_task_and_confirmation_routes(monkeypatch):
    monkeypatch.setenv("MY_COWORK_INDUSTRY_TOKEN", "host-secret")
    host = client()
    assert host.get("/health").status_code == 200
    assert host.get("/api/chat").status_code == 403
    assert host.post("/api/tool/confirm/call").status_code == 403
    headers = {"X-MyCowork-Industry-Token": "host-secret"}
    assert host.get("/api/chat", headers=headers).status_code == 200
    assert host.post("/api/tool/confirm/call", headers=headers).status_code == 200


def test_missing_token_fails_closed_and_browser_origin_is_not_authorization(monkeypatch):
    monkeypatch.delenv("MY_COWORK_INDUSTRY_TOKEN", raising=False)
    assert client().get("/api/chat").status_code == 403
    monkeypatch.setenv("MY_COWORK_INDUSTRY_TOKEN", "host-secret")
    assert client().get("/api/chat", headers={
        "Origin": "mycowork-app://cn.example.other",
        "X-MyCowork-Industry-Token": "host-secret",
    }).status_code == 403
