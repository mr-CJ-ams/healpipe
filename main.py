import asyncio
import hashlib
import csv
import io
import json
import importlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from core.ai_agent import resolve_ambiguous_schema
from core.auth import bearer_session, create_session_token, verify_google_credential
from core.algorithms import (
    DEFAULT_MATCH_THRESHOLD,
    apply_persisted_mappings,
    key_confidence,
    map_payload_keys,
)
from core.normalizer import normalize_payload
from core.queue_worker import enqueue_delivery, start_queue_workers, stop_queue_workers
from core.security import verify_webhook_signature
from database.connection import configured_cors_origins
from database.repository import (
    fetch_event_stats,
    fetch_event_audit,
    fetch_healing_events,
    list_mapping_rules,
    create_mapping_rule,
    approve_mapping_rule,
    disable_mapping_rule,
    rollback_mapping_rule,
    fetch_active_mapping_snapshot,
    create_data_bridge,
    create_delivery_job,
    get_delivery_job,
    replay_delivery_job,
    delete_data_bridge,
    get_active_data_bridge,
    set_data_bridge_active,
    persist_healing_event,
    promote_ai_healing,
    resolve_triage_event,
    update_event_reason,
    fetch_data_bridges,
    create_account,
    create_account_api_key,
    get_default_account,
    get_or_create_google_account,
    google_identity_exists,
    save_onboarding_profile,
    resolve_api_key,
    write_audit_log,
    append_event_lifecycle,
    append_job_lifecycle,
    fetch_recoverable_delivery_jobs,
    fetch_reconciliation,
    fetch_export_events,
    create_audit_export,
    list_replayable_jobs,
)
from database.schemas import (
    DataBridgeCreateRequest,
    DataBridgeStatusRequest,
    MappingRuleCreateRequest,
    MappingTestRequest,
    AccountCreateRequest,
    ApiKeyCreateRequest,
    AuditExportRequest,
    ReplayBatchRequest,
    TriageRequest,
    WebhookReceiveRequest,
    WebhookReceiveResponse,
    OnboardingRequest,
    GoogleLoginRequest,
)
from services.notification import send_pipeline_alert
from services.scheduler import scheduler_loop


async def delivery_recovery_loop() -> None:
    while True:
        for recovered_job in await fetch_recoverable_delivery_jobs():
            enqueue_delivery(
                event_id=recovered_job.event_id,
                payload=recovered_job.payload,
                target_url=recovered_job.target_url,
                bridge_id=recovered_job.bridge_id,
                job_id=recovered_job.job_id,
                idempotency_key=recovered_job.idempotency_key,
            )
        await asyncio.sleep(5)



@asynccontextmanager
async def lifespan(_: FastAPI):
    start_queue_workers()
    for recovered_job in await fetch_recoverable_delivery_jobs():
        enqueue_delivery(
            event_id=recovered_job.event_id,
            payload=recovered_job.payload,
            target_url=recovered_job.target_url,
            bridge_id=recovered_job.bridge_id,
            job_id=recovered_job.job_id,
            idempotency_key=recovered_job.idempotency_key,
        )
    scheduler_task = asyncio.create_task(scheduler_loop())
    delivery_recovery_task = asyncio.create_task(delivery_recovery_loop())
    try:
        yield
    finally:
        scheduler_task.cancel()
        delivery_recovery_task.cancel()
        await asyncio.gather(scheduler_task, delivery_recovery_task, return_exceptions=True)
        stop_queue_workers()


app = FastAPI(title="HealPipe.io", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.post("/auth/google")
async def google_login(payload: GoogleLoginRequest) -> dict[str, Any]:
    credential = payload.credential
    if not os.getenv("AUTH_SESSION_SECRET"):
        raise HTTPException(status_code=503, detail="Browser session signing is not configured")
    claims = verify_google_credential(credential)
    identity_exists = await google_identity_exists(str(claims["sub"]))
    if payload.mode == "signup" and identity_exists:
        raise HTTPException(status_code=409, detail="An account already exists for this Google account. Please choose Login.")
    if payload.mode == "login" and not identity_exists:
        raise HTTPException(status_code=404, detail="No HealPipe account exists for this Google account. Please choose Sign up first.")
    account, role, onboarding_required = await get_or_create_google_account(
        google_subject=str(claims["sub"]),
        email=str(claims["email"]),
        display_name=claims.get("name"),
    )
    actor_id = f"google:{claims['sub']}"
    await write_audit_log(account.account_id, actor_id, "auth.google_login", "account", str(account.account_id), after_state={"email": claims["email"]})
    return {
        "session_token": create_session_token(account_id=account.account_id, actor_id=actor_id, role=role),
        "onboarding_required": onboarding_required,
        "user": {"email": claims["email"], "name": claims.get("name") or claims["email"], "picture": claims.get("picture"), "account_name": account.name},
    }


@app.post("/auth/onboarding")
async def complete_onboarding(request: OnboardingRequest, raw_request: Request) -> dict[str, bool]:
    session = bearer_session(raw_request)
    if session is None:
        raise HTTPException(status_code=401, detail="A Google session is required")
    profile = await save_onboarding_profile(UUID(session["account_id"]), request.model_dump())
    await write_audit_log(UUID(session["account_id"]), session["actor_id"], "account.onboarding_completed", "onboarding_profile", str(profile.profile_id), after_state=request.model_dump())
    return {"completed": True}


def event_execution_log(status: str, detail: str) -> str:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return f"Timestamp: {timestamp}. Status: {status}. {detail}"


async def resolve_and_forward_uncertain(
    *,
    event_id: object,
    raw_payload: dict,
    healed_payload: dict,
    key_mappings: dict[str, str],
    uncertain_key: str,
    target_url: str,
    bridge_id: UUID,
    account_id: UUID,
) -> None:
    try:
        resolution = await resolve_ambiguous_schema(raw_payload, uncertain_key)
        if resolution["confidence"] < 0.85:
            return

        destination_key = resolution["mapped_key"]
        if destination_key in healed_payload:
            return

        corrected_payload = dict(healed_payload)
        corrected_payload[destination_key] = corrected_payload.pop(uncertain_key)
        corrected_mappings = {**key_mappings, uncertain_key: destination_key}
        reason = (
            f"Claude mapped {uncertain_key} to {destination_key} "
            f"with confidence {resolution['confidence']:.2f}"
        )
        await promote_ai_healing(
            event_id,
            corrected_payload,
            corrected_mappings,
            reason,
            ai_telemetry=resolution.get("telemetry"),
            bridge_id=bridge_id,
        )
        job = await create_delivery_job(
            event_id=event_id,
            payload=corrected_payload,
            target_url=target_url,
            bridge_id=bridge_id,
            idempotency_key=None,
            account_id=account_id,
        )
        if job is None:
            raise RuntimeError("Delivery job could not be persisted")
        enqueue_delivery(
            event_id=event_id,
            payload=corrected_payload,
            target_url=target_url,
            bridge_id=bridge_id,
            job_id=job.job_id,
        )
    except Exception as error:
        # Fail closed: uncertain data is never forwarded without a valid decision.
        await update_event_reason(event_id, f"AI triage failed: {error}")


@app.get("/v1/webhooks/events")
async def get_webhook_events(
    raw_request: Request,
    limit: int = 100,
    bridge_id: UUID | None = None,
) -> list[dict]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    if bridge_id is not None:
        await require_bridge_account(raw_request, bridge_id, "events:read")
    elif os.getenv("ACCOUNT_AUTH_REQUIRED", "false").lower() == "true":
        raise HTTPException(status_code=400, detail="bridge_id is required for account-scoped event queries")
    return await fetch_healing_events(limit, bridge_id)


@app.get("/v1/webhooks/stats")
async def get_webhook_stats(raw_request: Request, bridge_id: UUID | None = None) -> dict[str, int]:
    if bridge_id is not None:
        await require_bridge_account(raw_request, bridge_id, "events:read")
    return await fetch_event_stats(bridge_id)


@app.get("/v1/webhooks/reconciliation")
async def get_reconciliation(raw_request: Request, bridge_id: UUID) -> dict[str, int]:
    account_id, _, _ = await require_bridge_account(raw_request, bridge_id, "events:read")
    return await fetch_reconciliation(bridge_id, account_id)


@app.post("/v1/audit-exports")
async def export_audit(request: AuditExportRequest, raw_request: Request) -> Response:
    account_id, actor = await require_role(raw_request, {"owner", "admin", "operator"})
    await request_account(raw_request, "audit:export")
    max_rows = int(os.getenv("AUDIT_EXPORT_MAX_ROWS", "5000"))
    filters = request.model_dump(mode="json", exclude_none=True)
    query_filters = request.model_dump(exclude_none=True)
    query_filters.pop("export_format", None)
    rows = await fetch_export_events(account_id, limit=max_rows, **query_filters)
    if request.export_format == "summary":
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "filters": filters,
            "row_count": len(rows),
            "status_counts": {status: sum(row["status"] == status for row in rows) for status in sorted({row["status"] for row in rows})},
            "events": [{"event_id": row["event_id"], "received_at": row["received_at"], "source_platform": row["source_platform"], "status": row["status"], "raw_payload_sha256": row["raw_payload_sha256"]} for row in rows],
        }
        body = json.dumps(summary, indent=2).encode()
        content_type = "application/json"
        filename = "healpipe-audit-summary.json"
    elif request.export_format == "pdf":
        reportlab_pages = importlib.import_module("reportlab.lib.pagesizes")
        reportlab_canvas = importlib.import_module("reportlab.pdfgen.canvas")
        letter = reportlab_pages.letter
        canvas = reportlab_canvas
        pdf_buffer = io.BytesIO()
        pdf = canvas.Canvas(pdf_buffer, pagesize=letter)
        pdf.setTitle("HealPipe Audit Summary")
        pdf.drawString(48, 750, "HealPipe Audit Summary")
        pdf.drawString(48, 732, f"Generated: {datetime.now(timezone.utc).isoformat()}")
        pdf.drawString(48, 714, f"Events: {len(rows)}")
        y = 680
        for row in rows[:80]:
            line = f"{row['event_id'][:12]}  {row['status']}  {row['source_platform']}  {row['received_at']}"
            pdf.drawString(48, y, line[:115])
            y -= 14
            if y < 48:
                pdf.showPage()
                y = 750
        pdf.save()
        body = pdf_buffer.getvalue()
        content_type = "application/pdf"
        filename = "healpipe-audit-summary.pdf"
    elif request.export_format == "csv":
        output = io.StringIO()
        fields = ["event_id", "received_at", "source_platform", "bridge_id", "raw_payload_sha256", "status", "final_payload", "mapping_changes", "validation_errors", "delivery_jobs", "reason"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(row[field], ensure_ascii=True) if isinstance(row[field], (dict, list)) else row[field] for field in fields})
        body = output.getvalue().encode()
        content_type = "text/csv"
        filename = "healpipe-audit.csv"
    else:
        body = json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "filters": filters, "events": rows}, indent=2, ensure_ascii=True).encode()
        content_type = "application/json"
        filename = "healpipe-audit.json"
    await create_audit_export(account_id, actor, request.export_format, filters, len(rows), hashlib.sha256(body).hexdigest())
    await write_audit_log(account_id, actor, "audit.exported", "audit_export", filename, after_state={"format": request.export_format, "row_count": len(rows), "sha256": hashlib.sha256(body).hexdigest()})
    return Response(content=body, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/v1/webhooks/events/{event_id}/audit")
async def get_event_audit(event_id: UUID, bridge_id: UUID, raw_request: Request) -> dict:
    await require_bridge_account(raw_request, bridge_id, "events:read")
    audit = await fetch_event_audit(event_id, bridge_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Event audit was not found")
    return audit


@app.get("/v1/bridges")
async def get_bridges(raw_request: Request, include_inactive: bool = True) -> list[dict]:
    account_id, _ = await request_account(raw_request, "bridges:read")
    return await fetch_data_bridges(include_inactive, account_id)


@app.post("/v1/accounts", status_code=201)
async def create_account_route(request: AccountCreateRequest, raw_request: Request) -> dict[str, str]:
    actor = require_operator(raw_request)
    account = await create_account(request.name, actor)
    await write_audit_log(account.account_id, actor, "account.created", "account", str(account.account_id), after_state={"name": account.name})
    return {"account_id": str(account.account_id), "name": account.name}


@app.post("/v1/accounts/{account_id}/api-keys", status_code=201)
async def create_api_key_route(account_id: UUID, request: ApiKeyCreateRequest, raw_request: Request) -> dict[str, Any]:
    actor = require_operator(raw_request)
    raw_key, key = await create_account_api_key(account_id, request.scopes, request.role)
    await write_audit_log(account_id, actor, "api_key.created", "api_key", str(key.key_id), after_state={"scopes": key.scopes})
    return {"api_key": raw_key, "key_id": str(key.key_id), "scopes": key.scopes}


def operator_identity(request: Request) -> str:
    return request.headers.get("X-Operator-Id", "local-operator")


def require_operator(request: Request) -> str:
    configured_key = os.getenv("OPERATOR_API_KEY")
    if configured_key and request.headers.get("X-Operator-Key") != configured_key:
        raise HTTPException(status_code=403, detail="Operator authorization is required")
    return operator_identity(request)


async def request_account(request: Request, scope: str | None = None) -> tuple[UUID, str]:
    session = bearer_session(request)
    if session is not None:
        return UUID(session["account_id"]), session["actor_id"]
    raw_key = request.headers.get("X-API-Key")
    if raw_key:
        api_key = await resolve_api_key(raw_key)
        if api_key is None:
            raise HTTPException(status_code=401, detail="API key is invalid or revoked")
        if scope and scope not in api_key.scopes and "*" not in api_key.scopes:
            raise HTTPException(status_code=403, detail="API key scope is insufficient")
        return api_key.account_id, api_key.key_prefix
    if os.getenv("ACCOUNT_AUTH_REQUIRED", "false").lower() == "true":
        raise HTTPException(status_code=401, detail="Account API key is required")
    account = await get_default_account()
    if account is None:
        raise HTTPException(status_code=503, detail="Default account is not initialized")
    return account.account_id, "local-operator"


async def require_role(request: Request, allowed_roles: set[str]) -> tuple[UUID, str]:
    session = bearer_session(request)
    if session is not None:
        if session.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Account role is insufficient")
        return UUID(session["account_id"]), session["actor_id"]
    raw_key = request.headers.get("X-API-Key")
    if not raw_key:
        if os.getenv("ACCOUNT_AUTH_REQUIRED", "false").lower() == "true":
            raise HTTPException(status_code=401, detail="Account API key is required")
        return (await get_default_account()).account_id, "local-operator"
    api_key = await resolve_api_key(raw_key)
    if api_key is None or api_key.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Account role is insufficient")
    return api_key.account_id, api_key.key_prefix


async def require_bridge_account(request: Request, bridge_id: UUID, scope: str | None = None):
    account_id, actor = await request_account(request, scope)
    bridge = await get_active_data_bridge(bridge_id, account_id)
    if bridge is None:
        raise HTTPException(status_code=404, detail="Active data bridge was not found")
    return account_id, actor, bridge


@app.get("/v1/bridges/{bridge_id}/mappings")
async def get_bridge_mappings(bridge_id: UUID, raw_request: Request) -> list[dict]:
    await require_bridge_account(raw_request, bridge_id, "mappings:read")
    return await list_mapping_rules(bridge_id)


@app.post("/v1/bridges/{bridge_id}/mappings", status_code=201)
async def propose_bridge_mapping(
    bridge_id: UUID,
    request: MappingRuleCreateRequest,
    raw_request: Request,
) -> dict:
    await require_role(raw_request, {"owner", "admin", "operator"})
    account_id, actor, _ = await require_bridge_account(raw_request, bridge_id, "mappings:write")
    result = await create_mapping_rule(
        bridge_id,
        request.source_field,
        request.destination_field,
        actor,
        request.reason,
        account_id,
    )
    await write_audit_log(account_id, actor, "mapping.proposed", "mapping", result["mapping_id"], after_state=result)
    return result


@app.post("/v1/mappings/{mapping_id}/approve")
async def approve_mapping(mapping_id: UUID, raw_request: Request) -> dict:
    account_id, actor = await require_role(raw_request, {"owner", "admin"})
    await request_account(raw_request, "mappings:approve")
    result = await approve_mapping_rule(mapping_id, actor, account_id)
    if result is None:
        raise HTTPException(status_code=409, detail="Mapping is not available for approval")
    await write_audit_log(account_id, actor, "mapping.approved", "mapping", str(mapping_id), after_state=result)
    return result


@app.post("/v1/mappings/{mapping_id}/disable")
async def disable_mapping(mapping_id: UUID, raw_request: Request) -> dict:
    account_id, actor = await require_role(raw_request, {"owner", "admin", "operator"})
    await request_account(raw_request, "mappings:write")
    result = await disable_mapping_rule(mapping_id, actor, account_id)
    if result is None:
        raise HTTPException(status_code=409, detail="Only an active mapping can be disabled")
    await write_audit_log(account_id, actor, "mapping.disabled", "mapping", str(mapping_id), after_state=result)
    return result


@app.post("/v1/mappings/{mapping_id}/rollback")
async def rollback_mapping(mapping_id: UUID, raw_request: Request) -> dict:
    account_id, actor = await require_role(raw_request, {"owner", "admin"})
    await request_account(raw_request, "mappings:approve")
    result = await rollback_mapping_rule(mapping_id, actor, account_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Mapping revision was not found")
    await write_audit_log(account_id, actor, "mapping.rollback", "mapping", str(mapping_id), after_state=result)
    return result


@app.post("/v1/bridges/{bridge_id}/mappings/test")
async def test_bridge_mapping(bridge_id: UUID, request: MappingTestRequest, raw_request: Request) -> dict:
    await require_bridge_account(raw_request, bridge_id, "mappings:read")
    mappings, versions = await fetch_active_mapping_snapshot(bridge_id)
    output = dict(request.payload)
    changes = []
    for source, destination in mappings.items():
        if source in output and destination not in output:
            value = output.pop(source)
            output[destination] = value
            changes.append({"source": source, "destination": destination, "value": value})
    return {"mapping_versions": versions, "input": request.payload, "output": output, "changes": changes}


@app.post("/v1/bridges", status_code=201)
async def create_bridge(request: DataBridgeCreateRequest, raw_request: Request) -> dict[str, str | bool]:
    account_id, actor = await require_role(raw_request, {"owner", "admin"})
    await request_account(raw_request, "bridges:write")
    bridge = await create_data_bridge(
        request.bridge_name,
        request.source_platform,
        request.target_endpoint_url,
        account_id,
    )
    await write_audit_log(account_id, actor, "bridge.created", "bridge", str(bridge.bridge_id), after_state={"bridge_name": bridge.bridge_name})
    return {
        "bridge_id": str(bridge.bridge_id),
        "bridge_name": bridge.bridge_name,
        "source_platform": bridge.source_platform,
        "target_endpoint_url": bridge.target_endpoint_url,
        "is_active": bridge.is_active,
        "signature_secret": bridge.signature_secret,
        "ingestion_url": f"https://healpipe.io/v1/webhooks/receive?bridge_id={bridge.bridge_id}",
    }


@app.patch("/v1/bridges/{bridge_id}")
async def update_bridge_status(
    bridge_id: UUID,
    request: DataBridgeStatusRequest,
    raw_request: Request,
) -> dict[str, str | bool]:
    await require_role(raw_request, {"owner", "admin"})
    await require_bridge_account(raw_request, bridge_id, "bridges:write")
    bridge = await set_data_bridge_active(bridge_id, request.is_active)
    if bridge is None:
        raise HTTPException(status_code=404, detail="Data bridge was not found")
    return {
        "bridge_id": str(bridge.bridge_id),
        "source_platform": bridge.source_platform,
        "is_active": bridge.is_active,
    }


@app.delete("/v1/bridges/{bridge_id}", status_code=204)
async def delete_bridge(bridge_id: UUID, raw_request: Request) -> None:
    await require_role(raw_request, {"owner", "admin"})
    await require_bridge_account(raw_request, bridge_id, "bridges:write")
    bridge = await delete_data_bridge(bridge_id)
    if bridge is None:
        raise HTTPException(status_code=404, detail="Data bridge was not found")


@app.post("/v1/delivery-jobs/{job_id}/replay")
async def replay_delivery(job_id: UUID, raw_request: Request) -> dict[str, str]:
    await require_role(raw_request, {"owner", "admin", "operator"})
    original_job = await get_delivery_job(job_id)
    if original_job is None:
        raise HTTPException(status_code=404, detail="Delivery job was not found")
    await require_bridge_account(raw_request, original_job.bridge_id, "deliveries:replay")
    job = await replay_delivery_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Delivery job was not found or is not replayable")
    await append_job_lifecycle(job_id=job.job_id, state="replayed", reason=f"Replay requested for delivery job {job_id}")
    enqueue_delivery(
        job_id=job.job_id,
        event_id=job.event_id,
        payload=job.payload,
        target_url=job.target_url,
        bridge_id=job.bridge_id,
        is_replay=True,
        idempotency_key=job.idempotency_key,
    )
    return {"job_id": str(job.job_id), "status": "queued"}
@app.post("/v1/delivery-jobs/replay-batch")
async def replay_delivery_batch(request: ReplayBatchRequest, raw_request: Request) -> dict[str, Any]:
    account_id, actor = await require_role(raw_request, {"owner", "admin", "operator"})
    await request_account(raw_request, "deliveries:replay")
    await require_bridge_account(raw_request, request.bridge_id, "deliveries:replay")
    jobs = await list_replayable_jobs(account_id, request.bridge_id, request.status, request.from_timestamp, request.to_timestamp)
    results = []
    for original in jobs:
        replay = await replay_delivery_job(original.job_id)
        if replay is None:
            results.append({"job_id": str(original.job_id), "status": "skipped"})
            continue
        if request.payload_override is not None or request.target_url_override is not None:
            from database.connection import async_session
            if async_session is not None:
                async with async_session() as session:
                    if request.payload_override is not None:
                        replay.payload = request.payload_override
                    if request.target_url_override is not None:
                        replay.target_url = request.target_url_override
                    await session.commit()
        await append_job_lifecycle(job_id=replay.job_id, state="replayed", reason=f"Batch replay requested by {actor}")
        enqueue_delivery(event_id=replay.event_id, payload=replay.payload, target_url=replay.target_url, bridge_id=replay.bridge_id, job_id=replay.job_id, is_replay=True, idempotency_key=replay.idempotency_key)
        results.append({"job_id": str(original.job_id), "replay_job_id": str(replay.job_id), "status": "queued"})
    return {"requested": len(jobs), "queued": sum(item["status"] == "queued" for item in results), "results": results}


@app.post("/v1/webhooks/resolve-triage")
async def resolve_triage(
    request: TriageRequest,
    background_tasks: BackgroundTasks,
    raw_request: Request,
) -> dict:
    account_id, actor = await require_role(raw_request, {"owner", "admin", "operator"})
    await request_account(raw_request, "events:write")
    try:
        result = await resolve_triage_event(
            request.event_id,
            action=request.action,
            target_key=request.target_key,
            actor=actor,
            account_id=account_id,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if request.action == "map":
        if not result.get("bridge_id"):
            raise HTTPException(status_code=409, detail="The event has no tenant bridge")
        account_id, _, bridge = await require_bridge_account(raw_request, UUID(result["bridge_id"]), "events:write")
        if bridge is None:
            raise HTTPException(status_code=409, detail="The event bridge is no longer active")
        target_url = bridge.target_endpoint_url
        job = await create_delivery_job(
            event_id=request.event_id,
            payload=result["payload"],
            target_url=target_url,
            bridge_id=UUID(result["bridge_id"]),
            idempotency_key=None,
            account_id=account_id,
        )
        if job is None:
            raise HTTPException(status_code=503, detail="Delivery job could not be persisted")
        enqueue_delivery(
            event_id=request.event_id,
            payload=result["payload"],
            target_url=target_url,
            bridge_id=UUID(result["bridge_id"]),
            job_id=job.job_id,
        )
    return result

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/webhooks/receive", response_model=WebhookReceiveResponse)
async def receive_webhook(
    raw_request: Request,
    request: WebhookReceiveRequest,
    background_tasks: BackgroundTasks,
    bridge_id: UUID,
) -> WebhookReceiveResponse:
    raw_body = await raw_request.body()
    raw_payload = request.as_payload()
    normalized_payload = normalize_payload(raw_payload)
    expected_fields = request.expected_fields
    bridge = await get_active_data_bridge(bridge_id)
    if bridge is None:
        raise HTTPException(status_code=404, detail="Active data bridge was not found")
    signature = raw_request.headers.get("X-Webhook-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Webhook signature is required")
    if not verify_webhook_signature(raw_body, signature, bridge.signature_secret):
        raise HTTPException(status_code=401, detail="Webhook signature is invalid")
    raw_payload_sha256 = hashlib.sha256(raw_body).hexdigest()
    target_url = bridge.target_endpoint_url
    idempotency_key = request.idempotency_key
    if os.getenv("REQUIRE_IDEMPOTENCY_KEY", "false").lower() == "true" and not idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency_key is required for this bridge")
    mapped_payload, persisted_mappings, mapping_versions = await apply_persisted_mappings(
        normalized_payload,
        bridge_id,
    )
    healed_payload, key_mappings = map_payload_keys(
        mapped_payload,
        expected_fields,
    )
    key_mappings = {**persisted_mappings, **key_mappings}
    missing_required = [
        field
        for field in ("customer_id", "email_address")
        if field not in healed_payload
    ]
    if missing_required:
        response = WebhookReceiveResponse(
            event_id=uuid4(),
            status="rejected",
            payload=healed_payload,
            reason=f"Missing required fields: {', '.join(missing_required)}",
        )
        await persist_healing_event(
            event_id=response.event_id,
            status=response.status,
            raw_payload=raw_payload,
            normalized_payload=normalized_payload,
            healed_payload=healed_payload,
            key_mappings=key_mappings,
            mapping_versions=mapping_versions,
            reason=response.reason,
            validation_errors=[{"field": field, "message": "Required field is missing"} for field in missing_required],
            bridge_id=bridge_id,
            account_id=bridge.account_id,
            raw_payload_sha256=raw_payload_sha256,
        )
        await append_event_lifecycle(event_id=response.event_id, bridge_id=bridge_id, account_id=bridge.account_id, state="rejected", reason=response.reason)
        background_tasks.add_task(
            send_pipeline_alert,
            event_id=str(response.event_id),
            status=response.status,
            details=event_execution_log(response.status, response.reason or "Payload was rejected."),
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    uncertain_keys = [
        key
        for key in healed_payload
        if key not in expected_fields
        and key_confidence(key, expected_fields) < DEFAULT_MATCH_THRESHOLD
    ]
    if uncertain_keys:
        response = WebhookReceiveResponse(
            event_id=uuid4(),
            status="uncertain",
            payload=healed_payload,
            key_mappings=key_mappings,
            reason=f"Low-confidence fields parked for triage: {', '.join(uncertain_keys)}",
        )
        await persist_healing_event(
            event_id=response.event_id,
            status=response.status,
            raw_payload=raw_payload,
            normalized_payload=normalized_payload,
            healed_payload=healed_payload,
            key_mappings=key_mappings,
            mapping_versions=mapping_versions,
            reason=response.reason,
            validation_errors=[{"field": key, "message": "Low-confidence field requires triage"} for key in uncertain_keys],
            bridge_id=bridge_id,
            account_id=bridge.account_id,
            raw_payload_sha256=raw_payload_sha256,
        )
        await append_event_lifecycle(event_id=response.event_id, bridge_id=bridge_id, account_id=bridge.account_id, state="uncertain", reason=response.reason)
        background_tasks.add_task(
            send_pipeline_alert,
            event_id=str(response.event_id),
            status=response.status,
            details=event_execution_log(
                response.status,
                response.reason or "An incoming payload requires manual review.",
            ),
        )
        background_tasks.add_task(
            resolve_and_forward_uncertain,
            event_id=response.event_id,
            raw_payload=raw_payload,
            healed_payload=healed_payload,
            key_mappings=key_mappings,
            uncertain_key=uncertain_keys[0],
            target_url=target_url,
            bridge_id=bridge_id,
            account_id=bridge.account_id,
        )
        return JSONResponse(status_code=202, content=response.model_dump(mode="json"))

    event_id = uuid4()
    status = "healed" if key_mappings else "validated"
    await persist_healing_event(
        event_id=event_id,
        status=status,
        raw_payload=raw_payload,
        normalized_payload=normalized_payload,
        healed_payload=healed_payload,
        key_mappings=key_mappings,
        mapping_versions=mapping_versions,
        reason=None,
        bridge_id=bridge_id,
        account_id=bridge.account_id,
        raw_payload_sha256=raw_payload_sha256,
    )
    await append_event_lifecycle(event_id=event_id, bridge_id=bridge_id, account_id=bridge.account_id, state=status)
    execution_detail = (
        f"Normalized fields: {', '.join(key_mappings) or 'none'}."
        if status == "healed"
        else "Payload passed validation without schema corrections."
    )
    background_tasks.add_task(
        send_pipeline_alert,
        event_id=str(event_id),
        status=status,
        details=event_execution_log(status, execution_detail),
    )
    job = await create_delivery_job(
        event_id=event_id,
        payload=healed_payload,
        target_url=target_url,
        bridge_id=bridge_id,
        idempotency_key=idempotency_key,
        account_id=bridge.account_id,
    )
    if job is None:
        raise HTTPException(status_code=503, detail="Delivery job could not be persisted")
    enqueue_delivery(
        event_id=event_id,
        payload=healed_payload,
        target_url=target_url,
        bridge_id=bridge_id,
        job_id=job.job_id,
    )
    await append_event_lifecycle(event_id=event_id, bridge_id=bridge_id, account_id=bridge.account_id, job_id=job.job_id, state="queued")

    return WebhookReceiveResponse(
        event_id=event_id,
        status=status,
        payload=healed_payload,
        key_mappings=key_mappings,
    )
