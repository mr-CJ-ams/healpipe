from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

from database.repository import (
    claim_idempotency_key,
    mark_delivery_failed,
    mark_idempotency_blocked,
    record_delivery_attempt,
    append_job_lifecycle,
    update_delivery_job,
)
from services.notification import send_pipeline_alert
from services.outbound import forward_payload, is_retryable_response, retry_backoff_seconds


@dataclass(frozen=True)
class DeliveryJob:
    job_id: Any
    event_id: Any
    payload: dict[str, Any]
    target_url: str
    bridge_id: Any
    idempotency_key: str | None
    is_replay: bool = False


_jobs: queue.Queue[DeliveryJob | None] = queue.Queue()
_claims: dict[str, float] = {}
_claims_lock = threading.Lock()
_workers: list[threading.Thread] = []
_running = threading.Event()
_application_loop: asyncio.AbstractEventLoop | None = None
_claim_ttl_seconds = 24 * 60 * 60


def _claim(key: str | None) -> bool:
    if not key:
        return True
    now = time.monotonic()
    with _claims_lock:
        expired = [item for item, expires_at in _claims.items() if expires_at <= now]
        for item in expired:
            del _claims[item]
        if key in _claims:
            return False
        _claims[key] = now + _claim_ttl_seconds
        return True


def _run_on_application_loop(coroutine: Any, fallback_loop: asyncio.AbstractEventLoop) -> Any:
    if _application_loop is not None and _application_loop.is_running():
        return asyncio.run_coroutine_threadsafe(coroutine, _application_loop).result()
    return fallback_loop.run_until_complete(coroutine)


def _run_job_on_loop(job: DeliveryJob, loop: asyncio.AbstractEventLoop) -> None:
    attempt_number = job.attempt_count + 1
    _run_on_application_loop(update_delivery_job(job.job_id, status="delivering", attempt_count=attempt_number), loop)
    _run_on_application_loop(append_job_lifecycle(job_id=job.job_id, state="delivering"), loop)
    if job.idempotency_key and not job.is_replay and not _claim(job.idempotency_key):
        _run_on_application_loop(
            mark_idempotency_blocked(job.event_id, job.idempotency_key),
            loop,
        )
        _run_on_application_loop(
            update_delivery_job(
                job.job_id,
                status="idempotency_blocked",
                attempt_count=1,
                last_error="Duplicate idempotency key",
            ),
            loop,
        )
        return
    if job.idempotency_key:
        claimed = _run_on_application_loop(
            claim_idempotency_key(job.bridge_id, job.event_id, job.idempotency_key),
            loop,
        )
        if not claimed:
            _run_on_application_loop(
                mark_idempotency_blocked(job.event_id, job.idempotency_key),
                loop,
            )
            _run_on_application_loop(
                update_delivery_job(
                    job.job_id,
                    status="idempotency_blocked",
                    attempt_count=1,
                    last_error="Duplicate idempotency key",
                ),
                loop,
            )
            return
    attempts = {"count": 0}

    async def record_attempt(
        attempt_number: int,
        status: str,
        http_status: int | None,
        error_message: str | None,
        response_body: str | None,
    ) -> None:
        attempts["count"] = attempt_number
        attempts["retryable"] = is_retryable_response(http_status)
        await record_delivery_attempt(
            job.job_id,
            attempt_number,
            status,
            http_status=http_status,
            error_message=error_message,
            response_body=response_body,
        )
        await append_job_lifecycle(
            job_id=job.job_id,
            state="delivery_attempted",
            attempt_number=attempt_number,
            reason=error_message,
            metadata={"http_status": http_status},
        )
        if status == "delivered":
            await append_job_lifecycle(job_id=job.job_id, state="delivered", attempt_number=attempt_number, metadata={"http_status": http_status})
        if status == "failed":
            await append_job_lifecycle(job_id=job.job_id, state="retrying", attempt_number=attempt_number, reason=error_message)
        await update_delivery_job(job.job_id, status="delivering" if status == "delivered" else "delivering", attempt_count=attempt_number, last_error=error_message)

    delivered = _run_on_application_loop(
        forward_payload(
            event_id=job.event_id,
            payload=job.payload,
            target_url=job.target_url,
            attempt_number=attempt_number,
            on_attempt=record_attempt,
        ),
        loop,
    )
    final_attempt = attempts["count"] or attempt_number
    retryable = attempts.get("retryable", True)
    backoff = retry_backoff_seconds()
    if delivered:
        final_status = "delivered"
        next_attempt_at = None
    elif retryable and final_attempt < len(backoff):
        final_status = "retrying"
        next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=backoff[final_attempt])
    else:
        final_status = "dead_lettered"
        next_attempt_at = None
        _run_on_application_loop(send_pipeline_alert(str(job.event_id), "delivery_failed", "Delivery moved to dead letter after retry policy"), loop)
    _run_on_application_loop(update_delivery_job(job.job_id, status=final_status, attempt_count=final_attempt, last_error=None if delivered else "Delivery failed after retry policy", next_attempt_at=next_attempt_at), loop)
    if final_status == "dead_lettered":
        _run_on_application_loop(mark_delivery_failed(job.event_id, "Delivery moved to dead letter after retry policy"), loop)
    _run_on_application_loop(
        append_job_lifecycle(
            job_id=job.job_id,
            state=final_status,
            reason=None if delivered else "Delivery failed after retry policy",
        ),
        loop,
    )


def _worker_loop() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        while _running.is_set():
            job = _jobs.get()
            try:
                if job is None:
                    return
                _run_job_on_loop(job, loop)
            except Exception:
                # A failed worker invocation must not kill the worker pool.
                continue
            finally:
                _jobs.task_done()
    finally:
        loop.close()


def start_queue_workers(worker_count: int = 2) -> None:
    global _application_loop
    if _running.is_set():
        return
    try:
        _application_loop = asyncio.get_running_loop()
    except RuntimeError:
        _application_loop = None
    _running.set()
    for index in range(worker_count):
        worker = threading.Thread(
            target=_worker_loop,
            name=f"healpipe-delivery-{index + 1}",
            daemon=True,
        )
        worker.start()
        _workers.append(worker)


def enqueue_delivery(
    *,
    event_id: Any,
    payload: dict[str, Any],
    target_url: str,
    bridge_id: Any,
    job_id: Any,
    is_replay: bool = False,
    idempotency_key: str | None = None,
) -> None:
    if not _running.is_set():
        start_queue_workers()
    _jobs.put(DeliveryJob(job_id, event_id, payload, target_url, bridge_id, idempotency_key, is_replay))


def stop_queue_workers() -> None:
    global _application_loop
    if not _running.is_set():
        return
    _running.clear()
    for _ in _workers:
        _jobs.put(None)
    for worker in _workers:
        worker.join(timeout=10)
    _workers.clear()
    _application_loop = None