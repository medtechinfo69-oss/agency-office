"""Single-owner access gate for hosted deployments.

Local use stays unchanged unless ACCESS_PASSWORD is set. Production fails closed
without strong credentials. This is not a multi-user role/permission system.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.requests import HTTPConnection

COOKIE = "ao_session"
SESSION_SECONDS = 12 * 60 * 60
PUBLIC_PATHS = {"/healthz", "/api/auth/session", "/api/auth/login"}


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


@dataclass
class OwnerAccess:
    production: bool = False
    password: str = ""
    secret: str = ""
    origins: tuple[str, ...] = ()
    failures: dict[str, list[float]] = field(default_factory=dict)

    def __post_init__(self):
        if self.enabled and (len(self.password) < 16 or len(self.secret) < 32):
            raise RuntimeError("Hosted access requires ACCESS_PASSWORD (16+ characters) and SESSION_SECRET (32+ characters).")

    @property
    def enabled(self) -> bool:
        return self.production or bool(self.password)

    @classmethod
    def from_env(cls):
        return cls(
            production=os.getenv("APP_ENV", "local").lower() == "production",
            password=os.getenv("ACCESS_PASSWORD", ""),
            secret=os.getenv("SESSION_SECRET", ""),
            origins=tuple(x.strip().rstrip("/") for x in os.getenv("ALLOWED_ORIGINS", "").split(",") if x.strip()),
        )

    def _signature(self, payload: str) -> str:
        # Rotating either the password or signing secret invalidates all sessions.
        key = hashlib.sha256((self.secret + "\0" + self.password).encode()).digest()
        return _encode(hmac.new(key, payload.encode(), hashlib.sha256).digest())

    def issue(self, kind: str, seconds: int) -> str:
        payload = _encode(json.dumps({"kind": kind, "exp": time.time() + seconds, "nonce": secrets.token_urlsafe(16)}).encode())
        return payload + "." + self._signature(payload)

    def valid(self, token: str, kind: str) -> bool:
        try:
            if not token or len(token) > 2048:
                return False
            payload, signature = token.split(".")
            if not hmac.compare_digest(signature, self._signature(payload)):
                return False
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            return data["kind"] == kind and float(data["exp"]) > time.time()
        except (ValueError, TypeError, KeyError, UnicodeError):
            return False

    def authenticated(self, connection: HTTPConnection) -> bool:
        return not self.enabled or self.valid(connection.cookies.get(COOKIE, ""), "session")

    def origin_allowed(self, connection: HTTPConnection) -> bool:
        origin = connection.headers.get("origin", "").rstrip("/")
        if not origin:
            return True  # Non-browser clients still need the password/session.
        if origin in self.origins:
            return True
        return not self.production and origin == str(connection.base_url).rstrip("/")

    def check_rate(self, ip: str):
        now = time.monotonic()
        recent = [stamp for stamp in self.failures.get(ip, []) if now - stamp < 300]
        if len(self.failures) > 1000:
            self.failures.clear()
        self.failures[ip] = recent
        if len(recent) >= 10:
            raise HTTPException(429, "Too many sign-in attempts. Wait five minutes and try again.", headers={"Retry-After": "300"})


class OwnerAccessMiddleware:
    def __init__(self, app, access: OwnerAccess):
        self.app, self.access = app, access

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        connection = HTTPConnection(scope)
        if scope["type"] == "websocket":
            if self.access.enabled:
                protocols = scope.get("subprotocols", [])
                ticket = next((p[7:] for p in protocols if p.startswith("ticket.")), "")
                if not self.access.origin_allowed(connection) or not self.access.valid(ticket, "ws"):
                    return await send({"type": "websocket.close", "code": 1008})
            return await self.app(scope, receive, send)

        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() not in {b"cache-control", b"vary"}]
                headers += [(b"cache-control", b"no-store"), (b"vary", b"Cookie, Origin")]
                message = {**message, "headers": headers}
            await send(message)

        if self.access.enabled and scope.get("method") not in {"GET", "HEAD", "OPTIONS"} and not self.access.origin_allowed(connection):
            return await JSONResponse({"detail": "This frontend origin is not allowed. Configure ALLOWED_ORIGINS on the backend."}, status_code=403)(scope, receive, private_send)
        if scope["path"] not in PUBLIC_PATHS and not self.access.authenticated(connection):
            return await JSONResponse({"detail": "Sign in to access your agency."}, status_code=401)(scope, receive, private_send)
        await self.app(scope, receive, private_send)


class SignIn(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


def auth_router(access: OwnerAccess) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    def healthz():
        return {"ok": True}  # No configuration or provider secrets in public health checks.

    @router.get("/api/auth/session")
    def session(request: Request):
        return {"required": access.enabled, "authenticated": access.authenticated(request)}

    @router.post("/api/auth/login")
    def login(body: SignIn, request: Request):
        if not access.enabled:
            return {"authenticated": True}
        ip = request.client.host if request.client else "unknown"
        access.check_rate(ip)
        if not hmac.compare_digest(hashlib.sha256(body.password.encode()).digest(), hashlib.sha256(access.password.encode()).digest()):
            access.failures[ip].append(time.monotonic())
            raise HTTPException(401, "Incorrect password. Try again.")
        access.failures.pop(ip, None)
        response = JSONResponse({"authenticated": True})
        response.set_cookie(COOKIE, access.issue("session", SESSION_SECONDS), max_age=SESSION_SECONDS,
                            httponly=True, secure=access.production, samesite="lax", path="/")
        return response

    @router.post("/api/auth/logout")
    def logout():
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path="/", secure=access.production, httponly=True, samesite="lax")
        return response

    @router.get("/api/auth/ws-ticket")
    def websocket_ticket():
        # Short-lived WS-only credential goes in the subprotocol, never a URL or localStorage.
        return {"ticket": access.issue("ws", 30) if access.enabled else None}

    return router
