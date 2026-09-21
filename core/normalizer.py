from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


_NULL_STRINGS = {"", "null", "none", "n/a", "na", "undefined"}


def normalize_value(value: Any) -> Any:
    """Normalize common webhook representations while preserving unknown values."""
    if isinstance(value, dict):
        return {str(key): normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if stripped.lower() in _NULL_STRINGS:
        return None

    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False

    try:
        if "." in stripped:
            return float(stripped)
        return int(stripped)
    except ValueError:
        pass

    return stripped


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return normalize_value(payload)
