from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from typing import Any

from redis import Redis
from rq import Queue
from sqlalchemy.orm import Session

from eviforge.config import Settings
from eviforge.core.db import utcnow
from eviforge.core.models import Job, JobStatus

logger = logging.getLogger(__name__)


def _execution_mode() -> str:
    mode = os.getenv("EVIFORGE_JOB_EXECUTION", "auto").strip().lower()
    if mode in {"queue", "inline", "auto"}:
        return mode
    return "auto"


def _run_inline(job_id: str) -> None:
    from eviforge.worker import execute_module_task

    try:
        execute_module_task(job_id)
    except Exception:
        # Job failure state is persisted by execute_module_task itself.
        logger.exception("Inline job execution failed: %s", job_id)


def execute_job_inline(job_id: str, *, async_mode: bool = True) -> None:
    """
    Execute a queued Job without Redis/RQ.
    """
    if async_mode:
        t = threading.Thread(
            target=_run_inline,
            args=(job_id,),
            daemon=True,
            name=f"eviforge-inline-{job_id[:8]}",
        )
        t.start()
        return
    _run_inline(job_id)


def enqueue_job(
    session: Session,
    settings: Settings,
    case_id: str,
    tool_name: str,
    params: dict[str, Any] | None = None,
) -> Job:
    """
    Create a Job record and enqueue it in Redis.

    If `EVIFORGE_JOB_EXECUTION=inline`, or `auto` with Redis unavailable,
    the job is marked for inline execution.
    """
    if params is None:
        params = {}

    evidence_id = params.get("evidence_id")
    job_id = str(uuid.uuid4())

    job = Job(
        id=job_id,
        case_id=case_id,
        evidence_id=evidence_id,
        tool_name=tool_name,
        status=JobStatus.PENDING,
        queued_at=utcnow(),
        created_at=utcnow(),
        params_json=json.dumps(params, sort_keys=True),
    )
    session.add(job)
    session.flush()

    mode = _execution_mode()
    if mode == "inline":
        job.rq_job_id = f"inline:{job_id}"
        return job

    try:
        redis_conn = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        q = Queue(connection=redis_conn)
        rq_job = q.enqueue(
            "eviforge.worker.execute_module_task",
            job_id,
            job_timeout="1h",
        )
        job.rq_job_id = rq_job.id
        return job
    except Exception as exc:
        if mode == "queue":
            raise
        logger.warning("Redis queue unavailable; falling back to inline execution: %s", exc)
        job.rq_job_id = f"inline:{job_id}"
        return job


def update_job_status(
    session: Session,
    job_id: str,
    status: JobStatus,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """
    Update the status of a job.
    """
    job = session.get(Job, job_id)
    if not job:
        return

    job.status = status
    if result is not None:
        job.result_json = json.dumps(result)
    if error is not None:
        job.error_message = error

    if status in (JobStatus.COMPLETED, JobStatus.FAILED):
        job.completed_at = utcnow()

    session.add(job)
    session.commit()
