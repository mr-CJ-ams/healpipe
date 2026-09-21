from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any

from database.repository import fetch_active_mapping_snapshot


DEFAULT_MATCH_THRESHOLD = 0.78
KNOWN_FIELD_ALIASES = {
    "client_num": "customer_id",
    "user_email": "email_address",
    "qty_on_hand": "stock_count",
    "phone_number": "contact_phone",
    "contact_phone": "phone_number",
}


def levenshtein_distance(left: str, right: str) -> int:
    previous_row = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current_row = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current_row.append(
                min(
                    current_row[-1] + 1,
                    previous_row[right_index] + 1,
                    previous_row[right_index - 1] + (left_character != right_character),
                )
            )
        previous_row = current_row
    return previous_row[-1]


def levenshtein_ratio(left: str, right: str) -> float:
    longest = max(len(left), len(right))
    if longest == 0:
        return 1.0
    return 1.0 - levenshtein_distance(left, right) / longest


def similarity(left: str, right: str) -> float:
    normalized_left = left.casefold()
    normalized_right = right.casefold()
    character_score = levenshtein_ratio(normalized_left, normalized_right)
    sequence_score = SequenceMatcher(None, normalized_left, normalized_right).ratio()

    left_tokens = set(re.findall(r"[a-z0-9]+", normalized_left))
    right_tokens = set(re.findall(r"[a-z0-9]+", normalized_right))
    shared_tokens = left_tokens & right_tokens
    token_score = (
        0.8
        if any(len(token) >= 4 for token in shared_tokens)
        else 0.0
    )

    return max(character_score, sequence_score, token_score)


def best_key_match(
    incoming_key: str,
    expected_fields: list[str],
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> str | None:
    if incoming_key in expected_fields:
        return incoming_key
    alias = KNOWN_FIELD_ALIASES.get(incoming_key.casefold())
    if alias in expected_fields:
        return alias

    candidates = (
        (similarity(incoming_key, expected), expected)
        for expected in expected_fields
    )
    score, expected = max(candidates, default=(0.0, None))
    return expected if expected is not None and score >= threshold else None


def key_confidence(incoming_key: str, expected_fields: list[str]) -> float:
    if incoming_key in expected_fields:
        return 1.0
    if KNOWN_FIELD_ALIASES.get(incoming_key.casefold()) in expected_fields:
        return DEFAULT_MATCH_THRESHOLD
    return max(
        (similarity(incoming_key, expected) for expected in expected_fields),
        default=0.0,
    )


def map_payload_keys(
    payload: dict[str, Any],
    expected_fields: list[str],
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Map only confident top-level key mismatches; preserve ambiguous keys."""
    mapped_payload: dict[str, Any] = {}
    mappings: dict[str, str] = {}
    used_expected: set[str] = set()

    for incoming_key, value in payload.items():
        match = best_key_match(incoming_key, expected_fields, threshold)
        if match is None or match in used_expected:
            mapped_payload[incoming_key] = value
            continue

        mapped_payload[match] = value
        used_expected.add(match)
        if incoming_key != match:
            mappings[incoming_key] = match

    return mapped_payload, mappings


async def apply_persisted_mappings(
    payload: dict[str, Any],
    bridge_id: Any,
) -> tuple[dict[str, Any], dict[str, str], dict[str, int]]:
    """Apply only mapping rules owned by the current bridge before heuristics."""
    stored_mappings, mapping_versions = await fetch_active_mapping_snapshot(bridge_id)
    mapped_payload = dict(payload)
    applied: dict[str, str] = {}
    for source_key, target_key in stored_mappings.items():
        if source_key not in mapped_payload or target_key in mapped_payload:
            continue
        mapped_payload[target_key] = mapped_payload.pop(source_key)
        applied[source_key] = target_key
    return mapped_payload, applied, mapping_versions
