import asyncio
import logging
from typing import Dict, List

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self) -> None:
        self._connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        logger.info("WebSocket connected: %s", websocket.client)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        logger.info("WebSocket disconnected: %s", websocket.client)

    async def broadcast(self, payload: Dict) -> None:
        async with self._lock:
            connections = list(self._connections)

        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except WebSocketDisconnect:
                await self.disconnect(websocket)
            except RuntimeError as exc:  # pragma: no cover - safety net for concurrent sends
                logger.warning("Runtime error when pushing to websocket %s: %s", websocket.client, exc)
                await self.disconnect(websocket)
            except Exception as exc:  # pragma: no cover - unexpected send failure
                logger.exception("Failed to send payload to websocket %s", websocket.client, exc_info=exc)
                await self.disconnect(websocket)

    async def broadcast_job(self, job_payload: Dict) -> None:
        await self.broadcast({"type": "job", "data": job_payload})
