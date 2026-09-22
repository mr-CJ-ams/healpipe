from __future__ import annotations

import asyncio
import os

from core.queue_worker import enqueue_delivery, start_queue_workers, stop_queue_workers
from database.connection import close_database
from database.repository import fetch_recoverable_delivery_jobs
from services.scheduler import scheduler_loop


async def recovery_loop() -> None:
    while True:
        for job in await fetch_recoverable_delivery_jobs():
            enqueue_delivery(
                event_id=job.event_id,
                payload=job.payload,
                target_url=job.target_url,
                bridge_id=job.bridge_id,
                job_id=job.job_id,
                idempotency_key=job.idempotency_key,
            )
        await asyncio.sleep(float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "5")))


async def run() -> None:
    os.environ["HEALPIPE_PROCESS_ROLE"] = "worker"
    start_queue_workers(int(os.getenv("DELIVERY_WORKER_COUNT", "2")))
    tasks = [asyncio.create_task(recovery_loop()), asyncio.create_task(scheduler_loop())]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        stop_queue_workers()
        await close_database()


if __name__ == "__main__":
    asyncio.run(run())
