from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


def _session_serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("AUTH_SESSION_SECRET")
    if not secret:
        raise RuntimeError("AUTH_SESSION_SECRET is required for Google login")
    return URLSafeTimedSerializer(secret, salt="healpipe-browser-session")


def verify_google_credential(credential: str) -> dict[str, Any]:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    try:
        claims = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            audience=client_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Google credential is invalid") from error
    if not claims.get("sub") or not claims.get("email") or not claims.get("email_verified"):
        raise HTTPException(status_code=403, detail="A verified Google email is required")
    return claims


def create_session_token(*, account_id: Any, actor_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    return _session_serializer().dumps(
        {
            "account_id": str(account_id),
            "actor_id": actor_id,
            "role": role,
            "iat": now.isoformat(),
        }
    )


def read_session_token(token: str) -> dict[str, Any]:
    max_age = int(os.getenv("AUTH_SESSION_TTL_SECONDS", str(8 * 60 * 60)))
    try:
        return _session_serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired) as error:
        raise HTTPException(status_code=401, detail="Browser session is invalid or expired") from error


def bearer_session(request: Request) -> dict[str, Any] | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return read_session_token(header.removeprefix("Bearer ").strip())