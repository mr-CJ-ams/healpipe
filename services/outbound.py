from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx



DEFAULT_RETRY_BACKOFF_SECONDS = (0, 60, 300, 1800, 7200)


def retry_backoff_seconds() -> tuple[int, ...]:
    configured = os.getenv("DELIVERY_RETRY_BACKOFF_SECONDS")
    if not configured:
        return DEFAULT_RETRY_BACKOFF_SECONDS
    try:
        values = tuple(int(value.strip()) for value in configured.split(","))
    except ValueError:
        return DEFAULT_RETRY_BACKOFF_SECONDS
    return values if values and values[0] == 0 else DEFAULT_RETRY_BACKOFF_SECONDS


def is_retryable_response(status_code: int | None) -> bool:
    return status_code is None or status_code in {408, 429} or 500 <= status_code <= 599


async def forward_payload(
    *,
    event_id: Any,
    payload: dict[str, Any],
    target_url: str,
    attempt_number: int = 1,
    on_attempt: Callable[[int, str, int | None, str | None, str | None], Awaitable[None]] | None = None,
) -> bool:
    last_error: Exception | None = None
    response = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(target_url, json=payload)
            response.raise_for_status()
            if on_attempt is not None:
                await on_attempt(attempt_number, "delivered", response.status_code, None, response.text[:4000])
            return True
    except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as error:
        last_error = error
        response_status = response.status_code if response is not None else None
        if on_attempt is not None:
            response_body = response.text[:4000] if response is not None else None
            await on_attempt(attempt_number, "failed", response_status, str(error), response_body)
    # Scheduling the next attempt belongs to the durable delivery job worker.
    return False
