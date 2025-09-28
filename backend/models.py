from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, func

from .database import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "req_id", name="uq_jobs_source_req"),)

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    url = Column(String(1024), nullable=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    req_id = Column(String(128), nullable=False)
    source = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - repr for debugging only
        return (
            f"Job(id={self.id!r}, title={self.title!r}, company={self.company!r}, "
            f"source={self.source!r}, req_id={self.req_id!r})"
        )


def serialize_job(job: Job) -> Dict[str, Any]:
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "url": job.url,
        "posted_at": job.posted_at.isoformat() if job.posted_at is not None and isinstance(job.posted_at, datetime) else None,
        "req_id": job.req_id,
        "source": job.source,
        "created_at": job.created_at.isoformat() if isinstance(job.created_at, datetime) else None,
    }
