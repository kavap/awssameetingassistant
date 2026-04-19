"""WebSocket connection manager — broadcasts JSON messages to all connected clients."""
from __future__ import annotations

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        logger.info(f"WS connected. Total clients: {len(self._connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        was_present = websocket in self._connections
        self._connections.discard(websocket)
        if was_present:
            logger.info(f"WS disconnected. Total clients: {len(self._connections)}")
        else:
            logger.debug(f"WS disconnect called on unknown socket (already removed)")

    async def broadcast(self, message: dict) -> None:
        if not self._connections:
            return
        data = json.dumps(message)
        dead: set[WebSocket] = set()
        for ws in list(self._connections):
            try:
                await ws.send_text(data)
            except WebSocketDisconnect:
                dead.add(ws)
            except Exception as e:
                logger.warning(f"WS send error: {e}")
                dead.add(ws)
        self._connections -= dead

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Module-level singleton
manager = ConnectionManager()
