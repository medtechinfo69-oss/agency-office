"""Hosted sessions, managed workspace identities and resource authorization.
Local use remains open unless ACCESS_PASSWORD is set; production fails closed.
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
PUBLIC_PATHS = {"/", "/healthz", "/api/auth/session", "/api/auth/login", "/api/auth/invite/accept"}


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


@dataclass
class OwnerAccess:
    managed: bool = False
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
            managed=True,
            production=(os.getenv('VERCEL') == '1' or os.getenv("APP_ENV", "local").lower() == "production"),
            password=os.getenv("ACCESS_PASSWORD", ""),
            secret=os.getenv("SESSION_SECRET", ""),
            origins=tuple(x.strip().rstrip("/") for x in os.getenv("ALLOWED_ORIGINS", "").split(",") if x.strip()),
        )

    def _signature(self, payload: str) -> str:
        # Rotating either the password or signing secret invalidates all sessions.
        key = hashlib.sha256((self.secret + "\0" + self.password).encode()).digest()
        return _encode(hmac.new(key, payload.encode(), hashlib.sha256).digest())

    def issue(self, kind: str, seconds: int, uid: str = 'owner') -> str:
        data = {"kind": kind, "exp": time.time() + seconds, "nonce": secrets.token_urlsafe(16)}
        if self.managed:
            from .admin import version
            data.update(uid=uid, ver=version(uid))
        payload = _encode(json.dumps(data).encode())
        return payload + "." + self._signature(payload)

    def valid(self, token: str, kind: str) -> bool:
        try:
            if not token or len(token) > 2048:
                return False
            payload, signature = token.split(".")
            if not hmac.compare_digest(signature, self._signature(payload)):
                return False
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            valid = data["kind"] == kind and float(data["exp"]) > time.time()
            if valid and self.managed:
                from .admin import version
                valid = data.get('ver', 0) == version(data.get('uid', 'owner')) and data.get('ver', 0) >= 0
            return valid
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
                if self.access.managed:
                    from . import admin
                    data = json.loads(base64.urlsafe_b64decode(ticket.split('.')[0] + '=='))
                    member = admin.user(data.get('uid', 'owner'))
                    if not member or not admin.permits(member, 'projects'):
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
        if scope["path"] not in PUBLIC_PATHS and not (self.access.authenticated(connection) or (self.access.managed and connection.headers.get("authorization", "").startswith("Bearer ao_"))):
            return await JSONResponse({"detail": "Sign in to access your agency."}, status_code=401)(scope, receive, private_send)
        if self.access.managed and scope['path'] not in PUBLIC_PATHS:
            from . import admin
            identity = None
            authorization = connection.headers.get('authorization', '')
            if authorization.startswith('Bearer '): identity = admin.key_identity(authorization[7:])
            if identity is None and self.access.authenticated(connection):
                token = connection.cookies.get(COOKIE, '')
                uid = 'owner'
                if token:
                    data = json.loads(base64.urlsafe_b64decode(token.split('.')[0] + '=='))
                    uid = data.get('uid', 'owner')
                row = admin.user(uid)
                if row: identity = admin.public_user(row)
            if identity is None:
                return await JSONResponse({'detail': 'Sign in to access your agency.'}, status_code=401)(scope, receive, private_send)
            scope.setdefault('state', {})['identity'] = identity
            path = scope['path']
            own_account = path.startswith('/api/admin/me') or path.startswith('/api/auth/')
            write = scope.get('method') not in ('GET', 'HEAD', 'OPTIONS')
            # Model discovery is a read capability despite its POST body.
            if path.startswith('/api/providers/') and path.endswith('/models'): write = False
            if not own_account and not admin.permits(identity, admin.resource(path), write):
                return await JSONResponse({'detail': 'Your role does not allow this action.'}, status_code=403)(scope, receive, private_send)
        await self.app(scope, receive, private_send)


class InviteAccept(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=16, max_length=1024)


class SignIn(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
    email: str = Field(default="", max_length=254)


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
        uid = 'owner'
        if access.managed:
            from .admin import login
            uid = login(body.email, body.password, access.password)
        valid = bool(uid) if access.managed else hmac.compare_digest(hashlib.sha256(body.password.encode()).digest(), hashlib.sha256(access.password.encode()).digest())
        if not valid:
            access.failures[ip].append(time.monotonic())
            raise HTTPException(401, "Incorrect password. Try again.")
        access.failures.pop(ip, None)
        response = JSONResponse({"authenticated": True})
        response.set_cookie(COOKIE, access.issue("session", SESSION_SECONDS, uid=uid), max_age=SESSION_SECONDS,
                            httponly=True, secure=access.production, samesite="lax", path="/")
        return response

    @router.post('/api/auth/invite/accept')
    def accept_invitation(body: InviteAccept):
        from .admin import accept_invite
        return accept_invite(body)

    @router.post("/api/auth/logout")
    def logout():
        response = Response(status_code=204)
        response.delete_cookie(COOKIE, path="/", secure=access.production, httponly=True, samesite="lax")
        return response

    @router.get("/api/auth/ws-ticket")
    def websocket_ticket(request: Request):
        # Short-lived WS-only credential goes in the subprotocol, never a URL or localStorage.
        identity = getattr(request.state, 'identity', {})
        return {"ticket": access.issue("ws", 30, uid=identity.get('id', 'owner')) if access.enabled else None}

    return router
