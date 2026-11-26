"""In-process event bus → WebSocket broadcast.

Every state change in the office (agent status, speech bubbles, kanban moves,
progress, approvals…) is published here and pushed to all connected frontends.
A short history buffer lets newly connected clients replay recent events.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import Any, Optional

from fastapi import WebSocket


class EventBus:
    def __init__(self, history: int = 300) -> None:
        self._clients: set[WebSocket] = set()
        self._history: deque[dict] = deque(maxlen=history)

    # -- connections -------------------------------------------------------
    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        # replay recent history so a fresh page load catches up
        for ev in list(self._history)[-100:]:
            try:
                await ws.send_text(json.dumps({"type": "history", "event": ev}))
            except Exception:
                break

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    # -- publishing --------------------------------------------------------
    async def publish(self, etype: str, data: Optional[dict] = None, project_id: Optional[str] = None) -> dict:
        event = {
            "type": etype,
            "project_id": project_id,
            "data": data or {},
            "ts": time.time(),
        }
        self._history.append(event)
        dead: list[WebSocket] = []
        payload = json.dumps(event, ensure_ascii=False, default=str)
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)
        return event

    def publish_sync(self, etype: str, data: Optional[dict] = None, project_id: Optional[str] = None) -> None:
        """Fire-and-forget publish from sync code (schedules the coroutine)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(etype, data, project_id))
        except RuntimeError:
            # no running loop (e.g. unit tests) — just record history
            self._history.append({"type": etype, "project_id": project_id,
                                  "data": data or {}, "ts": time.time()})


bus = EventBus()
