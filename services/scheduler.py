from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from database.connection import async_session
from database.models import DataBridge, HealingEventRecord
from database.repository import claim_digest_run
from services.notification import send_weekly_validation_digest


async def run_validation_digest() -> None:
    if async_session is None:
        return
    now = datetime.now(timezone.utc)
    period_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    cutoff = period_start - timedelta(days=7)
    async with async_session() as session:
        bridge_result = await session.execute(
            select(DataBridge).where(DataBridge.is_active.is_(True))
        )
        for bridge in bridge_result.scalars():
            if not await claim_digest_run(bridge.bridge_id, period_start):
                continue
            event_result = await session.execute(
                select(HealingEventRecord).where(
                    HealingEventRecord.bridge_id == bridge.bridge_id,
                    HealingEventRecord.created_at >= cutoff,
                    HealingEventRecord.status.in_(["validated", "healed"]),
                )
            )
            events = list(event_result.scalars())
            if events:
                await send_weekly_validation_digest(events)


async def scheduler_loop() -> None:
    interval = int(os.getenv("DIGEST_INTERVAL_SECONDS", str(7 * 24 * 60 * 60)))
    while True:
        await asyncio.sleep(interval)
        await run_validation_digest()