"""Hosted access regressions; isolated ASGI app, no provider/database writes."""
import os
import sys
from unittest.mock import patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.access import OwnerAccess, OwnerAccessMiddleware, auth_router, COOKIE

PASSWORD = "test-only-owner-password-not-a-real-credential"
SECRET = "test-only-signing-secret-with-at-least-32-characters"
ORIGIN = "https://office.example"


def make_client(access=None):
    access = access or OwnerAccess(production=True, password=PASSWORD, secret=SECRET, origins=(ORIGIN,))
    app = FastAPI()
    app.add_middleware(OwnerAccessMiddleware, access=access)
    app.include_router(auth_router(access))

    @app.get("/api/private")
    @app.post("/api/private")
    @app.get("/media/private.svg")
    def private():
        return {"private": True}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept(subprotocol="agency-office" if "agency-office" in websocket.scope.get("subprotocols", []) else None)
        await websocket.send_json({"ok": True})
        await websocket.close()

    return TestClient(app, base_url="https://testserver"), access


def login(client):
    return client.post("/api/auth/login", json={"password": PASSWORD}, headers={"Origin": ORIGIN})


def test_production_fails_closed():
    with pytest.raises(RuntimeError):
        OwnerAccess(production=True)
    with pytest.raises(RuntimeError):
        OwnerAccess(password="short", secret=SECRET)


def test_private_api_media_docs_and_ticket_require_session():
    client, _ = make_client()
    assert client.get("/healthz").json() == {"ok": True}
    assert client.get("/api/auth/session").json() == {"required": True, "authenticated": False}
    for path in ["/api/private", "/media/private.svg", "/docs", "/openapi.json", "/api/auth/ws-ticket"]:
        response = client.get(path)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"


def test_login_cookie_logout():
    client, _ = make_client()
    assert client.post("/api/auth/login", json={"password": "wrong"}, headers={"Origin": ORIGIN}).status_code == 401
    response = login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert "domain=" not in cookie  # Reverse proxy sets this for the frontend host.
    assert PASSWORD not in cookie
    assert client.get("/api/auth/session").json()["authenticated"] is True
    assert client.get("/api/private").json() == {"private": True}
    assert client.get("/media/private.svg").status_code == 200
    assert client.post("/api/auth/logout", headers={"Origin": ORIGIN}).status_code == 204
    assert client.get("/api/private").status_code == 401


def test_bad_or_missing_origin_allowlist_blocks_browser_writes():
    client, _ = make_client()
    assert client.post("/api/auth/login", json={"password": PASSWORD}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert login(client).status_code == 200
    assert client.post("/api/private", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/private", headers={"Origin": ORIGIN}).status_code == 200
    locked, _ = make_client(OwnerAccess(production=True, password=PASSWORD, secret=SECRET))
    assert login(locked).status_code == 403


def test_rate_limit():
    client, _ = make_client()
    for _ in range(10):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    response = login(client)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "300"


def test_token_integrity_expiry_and_kind_separation():
    _, access = make_client()
    token = access.issue("session", 60)
    assert access.valid(token, "session")
    assert not access.valid(token, "ws")
    assert not access.valid(token + "tampered", "session")
    assert not access.valid("bad.format", "session")
    assert not access.valid(access.issue("session", -1), "session")
    rotated = OwnerAccess(production=True, password=PASSWORD + "new", secret=SECRET)
    assert not rotated.valid(token, "session")
    with patch("app.access.time.time", return_value=10**12):
        assert not access.valid(token, "session")


def test_websocket_uses_short_lived_ticket_not_session_in_url():
    client, access = make_client()
    assert login(client).status_code == 200
    ticket = client.get("/api/auth/ws-ticket").json()["ticket"]
    assert access.valid(ticket, "ws")
    assert not access.valid(ticket, "session")
    with client.websocket_connect("/ws", subprotocols=["agency-office", "ticket." + ticket], headers={"Origin": ORIGIN}) as ws:
        assert ws.receive_json() == {"ok": True}
    for protocols, origin in [([], ORIGIN), (["ticket." + client.cookies[COOKIE]], ORIGIN), (["ticket." + ticket], "https://evil.example")]:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", subprotocols=protocols, headers={"Origin": origin}):
                pass


def test_local_mode_is_backward_compatible():
    client, _ = make_client(OwnerAccess())
    assert client.get("/api/auth/session").json() == {"required": False, "authenticated": True}
    assert client.get("/api/private").status_code == 200
    assert client.get("/api/auth/ws-ticket").json() == {"ticket": None}
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json() == {"ok": True}
