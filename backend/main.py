from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import List

from fastapi import Depends, FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from .database import Base, engine, get_db
from .models import Job, serialize_job
from .notifier import Notifier
from .poller import poll_once, start_poller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("internship_tracker")

app = FastAPI(title="Internship Tracker API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

notifier = Notifier()
poller_task: asyncio.Task | None = None


@app.on_event("startup")
async def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    global poller_task
    poller_task = asyncio.create_task(start_poller(notifier))
    logger.info("Internship Tracker backend started")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global poller_task
    if poller_task:
        poller_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poller_task
    logger.info("Internship Tracker backend stopped")


@app.get("/jobs")
def get_jobs(limit: int = 50, db: Session = Depends(get_db)) -> List[dict]:
    limit = max(1, min(200, limit))
    jobs = (
        db.query(Job)
        .order_by(Job.posted_at.desc().nullslast(), Job.created_at.desc())
        .limit(limit)
        .all()
    )
    return [serialize_job(job) for job in jobs]


@app.post("/poll")
async def trigger_poll() -> dict:
    new_jobs = await poll_once(notifier)
    return {"ingested": len(new_jobs)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await notifier.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await notifier.disconnect(websocket)
    except Exception as exc:  # pragma: no cover - guard unexpected disconnections
        logger.warning("WebSocket error: %s", exc)
        await notifier.disconnect(websocket)
