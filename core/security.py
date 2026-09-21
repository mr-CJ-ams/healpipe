from __future__ import annotations

import hashlib
import hmac


def verify_webhook_signature(
    payload_bytes: bytes,
    signature: str,
    secret_key: str,
) -> bool:
    """Verify raw webhook bytes using HMAC-SHA256.

    Accepts either a raw hexadecimal digest or the common ``sha256=`` form.
    """
    supplied = signature.strip()
    if supplied.lower().startswith("sha256="):
        supplied = supplied[7:]
    expected = hmac.new(
        secret_key.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied.lower(), expected)