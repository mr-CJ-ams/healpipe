from __future__ import annotations

import json
import os
from typing import Any

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field, ValidationError


VALID_DESTINATION_KEYS = {
    "customer_id",
    "email_address",
    "stock_count",
    "phone_number",
    "contact_phone",
}


class SchemaResolution(BaseModel):
    mapped_key: str
    confidence: float = Field(ge=0.0, le=1.0)


def _client() -> AsyncAnthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return AsyncAnthropic(api_key=api_key)


async def resolve_ambiguous_schema(
    raw_payload: dict[str, Any],
    missing_key: str,
) -> dict[str, Any]:
    """Ask Claude for one conservative schema alignment decision."""
    model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    prompt = (
        "You are a schema reconciliation service. Analyze the incoming JSON key "
        "against the allowed destination keys. Use the value and surrounding "
        "payload as evidence, but never invent a destination key. Return only a "
        "JSON object with exactly mapped_key and confidence. confidence must be "
        "a number from 0.0 to 1.0. Allowed destination keys: "
        f"{sorted(VALID_DESTINATION_KEYS)}.\n\n"
        f"Unrecognized key: {missing_key}\n"
        f"Payload: {json.dumps(raw_payload, ensure_ascii=True, default=str)}"
    )

    async with _client() as client:
        response = await client.messages.create(
            model=model,
            max_tokens=120,
            temperature=0,
            system="Return strict JSON only. No markdown, prose, or code fences.",
            messages=[{"role": "user", "content": prompt}],
        )

    text = next((block.text for block in response.content if hasattr(block, "text")), "")
    try:
        resolution = SchemaResolution.model_validate_json(text)
    except (ValidationError, ValueError) as error:
        raise ValueError("Claude returned an invalid schema resolution") from error

    if resolution.mapped_key not in VALID_DESTINATION_KEYS:
        raise ValueError("Claude returned a destination key outside the allowlist")
    result = resolution.model_dump()
    result["telemetry"] = {
        "confidence_score": resolution.confidence,
        "algorithm": model,
    }
    return result