from __future__ import annotations

import hashlib
import secrets
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from database.connection import async_session
from database.models import (
    Account,
    AccountMember,
    ApiKey,
    AuditLog,
    AuditExport,
    DEFAULT_ACCOUNT_ID,
    DataBridge,
    DeliveryAttempt,
    DeliveryJob,
    DigestRun,
    EventLifecycle,
    HealingEventRecord,
    IdempotencyClaim,
    InventoryMapping,
    MappingRule,
)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


_EXPORT_SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "authorization", "signature", "credential"}


def redact_export_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if any(part in key.casefold() for part in _EXPORT_SENSITIVE_KEYS) else redact_export_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_export_value(item) for item in value]
    return value


async def get_default_account() -> Account | None:
    if async_session is None:
        return None
    async with async_session() as session:
        return await session.get(Account, DEFAULT_ACCOUNT_ID)


async def create_account(name: str, actor_id: str = "local-operator") -> Account:
    if async_session is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with async_session() as session:
        account = Account(name=name)
        session.add(account)
        await session.flush()
        session.add(AccountMember(account_id=account.account_id, actor_id=actor_id, role="owner"))
        await session.commit()
        await session.refresh(account)
        return account


async def create_account_api_key(account_id: Any, scopes: list[str], role: str = "operator") -> tuple[str, ApiKey]:
    if async_session is None:
        raise RuntimeError("DATABASE_URL is not configured")
    raw_key = f"hp_{secrets.token_urlsafe(32)}"
    async with async_session() as session:
        key = ApiKey(account_id=account_id, key_prefix=raw_key[:10], key_hash=hash_api_key(raw_key), scopes=scopes, role=role)
        session.add(key)
        await session.commit()
        await session.refresh(key)
        return raw_key, key


async def resolve_api_key(raw_key: str) -> ApiKey | None:
    if async_session is None:
        return None
    async with async_session() as session:
        result = await session.execute(
            select(ApiKey).where(
                ApiKey.key_hash == hash_api_key(raw_key),
                ApiKey.revoked_at.is_(None),
                (ApiKey.expires_at.is_(None) | (ApiKey.expires_at > datetime.now(timezone.utc))),
            )
        )
        return result.scalar_one_or_none()


async def write_audit_log(
    account_id: Any,
    actor_id: str,
    action: str,
    object_type: str,
    object_id: str,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    if async_session is None:
        return {}, {}
    async with async_session() as session:
        session.add(AuditLog(account_id=account_id, actor_id=actor_id, action=action, object_type=object_type, object_id=object_id, before_state=before_state, after_state=after_state, request_id=request_id, ip_address=ip_address))
        await session.commit()


async def create_audit_export(account_id: Any, requested_by: str, export_format: str, filters: dict[str, Any], row_count: int, file_sha256: str | None = None) -> AuditExport:
    if async_session is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with async_session() as session:
        export = AuditExport(account_id=account_id, requested_by=requested_by, export_format=export_format, filters=filters, row_count=row_count, file_sha256=file_sha256)
        session.add(export)
        await session.commit()
        await session.refresh(export)
        return export


async def fetch_export_events(account_id: Any, *, bridge_id: Any | None = None, event_id: Any | None = None, status: str | None = None, source_platform: str | None = None, from_timestamp: datetime | None = None, to_timestamp: datetime | None = None, limit: int = 5000) -> list[dict[str, Any]]:
    if async_session is None:
        return []
    async with async_session() as session:
        query = select(HealingEventRecord, DataBridge.source_platform).join(DataBridge, DataBridge.bridge_id == HealingEventRecord.bridge_id).where(HealingEventRecord.account_id == account_id)
        if bridge_id is not None: query = query.where(HealingEventRecord.bridge_id == bridge_id)
        if event_id is not None: query = query.where(HealingEventRecord.event_id == event_id)
        if status is not None: query = query.where(HealingEventRecord.status == status)
        if source_platform is not None: query = query.where(DataBridge.source_platform == source_platform)
        if from_timestamp is not None: query = query.where(HealingEventRecord.created_at >= from_timestamp)
        if to_timestamp is not None: query = query.where(HealingEventRecord.created_at <= to_timestamp)
        result = await session.execute(query.order_by(HealingEventRecord.created_at).limit(limit))
        events = list(result)
        event_ids = [event.event_id for event, _ in events]
        jobs_result = await session.execute(select(DeliveryJob).where(DeliveryJob.account_id == account_id, DeliveryJob.event_id.in_(event_ids))) if event_ids else None
        jobs = list(jobs_result.scalars()) if jobs_result is not None else []
        job_ids = [job.job_id for job in jobs]
        attempts_result = await session.execute(select(DeliveryAttempt).where(DeliveryAttempt.job_id.in_(job_ids)).order_by(DeliveryAttempt.attempt_number)) if job_ids else None
        attempts_by_job: dict[Any, list[dict[str, Any]]] = {job_id: [] for job_id in job_ids}
        if attempts_result is not None:
            for attempt in attempts_result.scalars():
                attempts_by_job[attempt.job_id].append({"attempt_number": attempt.attempt_number, "status": attempt.status, "http_status": attempt.http_status, "error_message": attempt.error_message, "response_body": attempt.response_body, "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None})
        jobs_by_event: dict[Any, list[dict[str, Any]]] = {}
        for job in jobs:
            jobs_by_event.setdefault(job.event_id, []).append({"job_id": str(job.job_id), "status": job.status, "attempt_count": job.attempt_count, "last_error": job.last_error, "target_url": job.target_url, "attempts": attempts_by_job[job.job_id]})
        return [{"event_id": str(event.event_id), "received_at": event.created_at.isoformat() if event.created_at else None, "source_platform": source, "bridge_id": str(event.bridge_id), "raw_payload_sha256": event.raw_payload_sha256, "raw_payload": redact_export_value(event.raw_payload), "normalized_payload": redact_export_value(event.normalized_payload), "final_payload": redact_export_value(event.healed_payload), "mapping_changes": event.key_mappings, "mapping_versions": event.mapping_versions, "validation_errors": event.validation_errors, "status": event.status, "reason": event.reason, "delivery_jobs": jobs_by_event.get(event.event_id, [])} for event, source in events]


async def create_data_bridge(
    bridge_name: str,
    source_platform: str,
    target_endpoint_url: str,
    account_id: Any = DEFAULT_ACCOUNT_ID,
) -> DataBridge:
    if async_session is None:
        raise RuntimeError("DATABASE_URL is not configured")

    async with async_session() as session:
        try:
            bridge = DataBridge(
                account_id=account_id,
                bridge_name=bridge_name,
                source_platform=source_platform,
                target_endpoint_url=target_endpoint_url,
                signature_secret=secrets.token_urlsafe(48),
            )
            session.add(bridge)
            await session.commit()
            await session.refresh(bridge)
            return bridge
        except Exception:
            await session.rollback()
            raise


async def get_active_data_bridge(bridge_id: Any, account_id: Any | None = None) -> DataBridge | None:
    if async_session is None:
        return None

    async with async_session() as session:
        query = select(DataBridge).where(
                DataBridge.bridge_id == bridge_id,
                DataBridge.is_active.is_(True),
            )
        if account_id is not None:
            query = query.where(DataBridge.account_id == account_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()


async def set_data_bridge_active(bridge_id: Any, is_active: bool) -> DataBridge | None:
    if async_session is None:
        return None

    async with async_session() as session:
        try:
            result = await session.execute(
                select(DataBridge).where(DataBridge.bridge_id == bridge_id).with_for_update()
            )
            bridge = result.scalar_one_or_none()
            if bridge is None:
                return None
            bridge.is_active = is_active
            await session.commit()
            await session.refresh(bridge)
            return bridge
        except Exception:
            await session.rollback()
            raise


async def delete_data_bridge(bridge_id: Any) -> DataBridge | None:
    return await set_data_bridge_active(bridge_id, False)


async def fetch_data_bridges(include_inactive: bool = True, account_id: Any | None = None) -> list[dict[str, Any]]:
    if async_session is None:
        return []

    async with async_session() as session:
        query = select(DataBridge)
        if not include_inactive:
            query = query.where(DataBridge.is_active.is_(True))
        if account_id is not None:
            query = query.where(DataBridge.account_id == account_id)
        result = await session.execute(query.order_by(DataBridge.created_at))
        return [
            {
                "bridge_id": str(bridge.bridge_id),
                "bridge_name": bridge.bridge_name,
                "source_platform": bridge.source_platform,
                "target_endpoint_url": bridge.target_endpoint_url,
                "is_active": bridge.is_active,
                "created_at": bridge.created_at.isoformat() if bridge.created_at else None,
            }
            for bridge in result.scalars()
        ]


async def fetch_bridge_inventory_mappings(bridge_id: Any) -> dict[str, str]:
    if async_session is None:
        return {}
    async with async_session() as session:
        versioned = await session.execute(
            select(MappingRule.source_field, MappingRule.destination_field).where(
                MappingRule.bridge_id == bridge_id,
                MappingRule.status == "active",
            )
        )
        legacy = await session.execute(
            select(InventoryMapping.source_sku, InventoryMapping.target_sku).where(
                InventoryMapping.bridge_id == bridge_id
            )
        )
        mappings = {source: target for source, target in legacy}
        mappings.update({source: target for source, target in versioned})
        return mappings


async def fetch_active_mapping_snapshot(bridge_id: Any) -> tuple[dict[str, str], dict[str, int]]:
    if async_session is None:
        return {}, {}
    async with async_session() as session:
        result = await session.execute(
            select(MappingRule).where(
                MappingRule.bridge_id == bridge_id,
                MappingRule.status == "active",
            )
        )
        rules = list(result.scalars())
        legacy_result = await session.execute(
            select(InventoryMapping.source_sku, InventoryMapping.target_sku).where(
                InventoryMapping.bridge_id == bridge_id
            )
        )
        legacy = {source: target for source, target in legacy_result}
        mappings = dict(legacy)
        versions = {source: 0 for source in legacy}
        mappings.update({rule.source_field: rule.destination_field for rule in rules})
        versions.update({rule.source_field: rule.revision for rule in rules})
        return mappings, versions


def _mapping_rule_dict(rule: MappingRule) -> dict[str, Any]:
    return {
        "mapping_id": str(rule.mapping_id),
        "bridge_id": str(rule.bridge_id),
        "account_id": str(rule.account_id),
        "source_field": rule.source_field,
        "destination_field": rule.destination_field,
        "revision": rule.revision,
        "status": rule.status,
        "created_by": rule.created_by,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "approved_by": rule.approved_by,
        "approved_at": rule.approved_at.isoformat() if rule.approved_at else None,
        "deactivated_by": rule.deactivated_by,
        "deactivated_at": rule.deactivated_at.isoformat() if rule.deactivated_at else None,
        "reason": rule.reason,
    }


async def list_mapping_rules(bridge_id: Any) -> list[dict[str, Any]]:
    if async_session is None:
        return []
    async with async_session() as session:
        result = await session.execute(
            select(MappingRule)
            .where(MappingRule.bridge_id == bridge_id)
            .order_by(MappingRule.source_field, MappingRule.revision.desc())
        )
        return [_mapping_rule_dict(rule) for rule in result.scalars()]


async def create_mapping_rule(
    bridge_id: Any,
    source_field: str,
    destination_field: str,
    created_by: str,
    reason: str | None = None,
    account_id: Any = DEFAULT_ACCOUNT_ID,
) -> dict[str, Any]:
    if async_session is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with async_session() as session:
        result = await session.execute(
            select(func.coalesce(func.max(MappingRule.revision), 0)).where(
                MappingRule.bridge_id == bridge_id,
                MappingRule.source_field == source_field,
            )
        )
        revision = int(result.scalar_one()) + 1
        rule = MappingRule(
            account_id=account_id,
            bridge_id=bridge_id,
            source_field=source_field,
            destination_field=destination_field,
            revision=revision,
            status="proposed",
            created_by=created_by,
            reason=reason,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return _mapping_rule_dict(rule)


async def approve_mapping_rule(mapping_id: Any, actor: str, account_id: Any = DEFAULT_ACCOUNT_ID) -> dict[str, Any] | None:
    if async_session is None:
        return None
    async with async_session() as session:
        result = await session.execute(
            select(MappingRule).where(MappingRule.mapping_id == mapping_id, MappingRule.account_id == account_id).with_for_update()
        )
        rule = result.scalar_one_or_none()
        if rule is None or rule.status not in {"proposed", "approved"}:
            return None
        active_result = await session.execute(
            select(MappingRule).where(
                MappingRule.bridge_id == rule.bridge_id,
                MappingRule.source_field == rule.source_field,
                MappingRule.status == "active",
            ).with_for_update()
        )
        for active in active_result.scalars():
            active.status = "inactive"
            active.deactivated_by = actor
            active.deactivated_at = datetime.now(timezone.utc)
        rule.status = "active"
        rule.approved_by = actor
        rule.approved_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(rule)
        return _mapping_rule_dict(rule)


async def disable_mapping_rule(mapping_id: Any, actor: str, account_id: Any = DEFAULT_ACCOUNT_ID) -> dict[str, Any] | None:
    if async_session is None:
        return None
    async with async_session() as session:
        result = await session.execute(
            select(MappingRule).where(MappingRule.mapping_id == mapping_id, MappingRule.account_id == account_id).with_for_update()
        )
        rule = result.scalar_one_or_none()
        if rule is None or rule.status != "active":
            return None
        rule.status = "inactive"
        rule.deactivated_by = actor
        rule.deactivated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(rule)
        return _mapping_rule_dict(rule)


async def rollback_mapping_rule(mapping_id: Any, actor: str, account_id: Any = DEFAULT_ACCOUNT_ID) -> dict[str, Any] | None:
    if async_session is None:
        return None
    async with async_session() as session:
        result = await session.execute(
            select(MappingRule).where(MappingRule.mapping_id == mapping_id, MappingRule.account_id == account_id).with_for_update()
        )
        target = result.scalar_one_or_none()
        if target is None or target.status not in {"inactive", "approved"}:
            return None
        active_result = await session.execute(
            select(MappingRule).where(
                MappingRule.bridge_id == target.bridge_id,
                MappingRule.source_field == target.source_field,
                MappingRule.status == "active",
            ).with_for_update()
        )
        active = active_result.scalar_one_or_none()
        if active is not None:
            active.status = "inactive"
            active.deactivated_by = actor
            active.deactivated_at = datetime.now(timezone.utc)
        target.status = "active"
        target.approved_by = actor
        target.approved_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(target)
        return _mapping_rule_dict(target)


async def fetch_healing_events(
    limit: int = 100,
    bridge_id: Any | None = None,
) -> list[dict[str, Any]]:
    if async_session is None:
        return []

    async with async_session() as session:
        query = select(HealingEventRecord).where(HealingEventRecord.status != "dropped")
        if bridge_id is not None:
            query = query.where(HealingEventRecord.bridge_id == bridge_id)
        result = await session.execute(
            query
            .order_by(HealingEventRecord.created_at.desc())
            .limit(limit)
        )
        return [
            {
                "event_id": str(event.event_id),
                "bridge_id": str(event.bridge_id) if event.bridge_id else None,
                "status": event.status,
                "raw_payload": event.raw_payload,
                "normalized_payload": event.normalized_payload,
                "healed_payload": event.healed_payload,
                "key_mappings": event.key_mappings,
                "mapping_versions": event.mapping_versions,
                "ai_telemetry": event.ai_telemetry,
                "validation_errors": event.validation_errors,
                "reason": event.reason,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in result.scalars()
        ]


async def fetch_event_stats(bridge_id: Any | None = None) -> dict[str, int]:
    stats = {
        "validated": 0,
        "healed": 0,
        "rejected": 0,
        "uncertain": 0,
        "delivery_failed": 0,
        "dropped": 0,
        "idempotency_blocked": 0,
    }
    if async_session is None:
        return stats

    async with async_session() as session:
        query = select(HealingEventRecord.status, func.count())
        if bridge_id is not None:
            query = query.where(HealingEventRecord.bridge_id == bridge_id)
        result = await session.execute(query.group_by(HealingEventRecord.status))
        for status, count in result:
            stats[status] = count
    return stats


async def persist_healing_event(
    *,
    event_id: Any,
    status: str,
    raw_payload: dict[str, Any],
    normalized_payload: dict[str, Any] | None = None,
    healed_payload: dict[str, Any],
    key_mappings: dict[str, str],
    mapping_versions: dict[str, int] | None = None,
    reason: str | None,
    ai_telemetry: dict[str, Any] | None = None,
    validation_errors: list[dict[str, Any]] | None = None,
    bridge_id: Any | None = None,
    account_id: Any = DEFAULT_ACCOUNT_ID,
    raw_payload_sha256: str | None = None,
) -> None:
    """Commit one audit event when PostgreSQL persistence is configured."""
    if async_session is None:
        return

    async with async_session() as session:
        try:
            session.add(
                HealingEventRecord(
                    event_id=event_id,
                                        account_id=account_id,
                    bridge_id=bridge_id,
                    status=status,
                    raw_payload=raw_payload,
                    raw_payload_sha256=raw_payload_sha256,
                    normalized_payload=normalized_payload if normalized_payload is not None else raw_payload,
                    healed_payload=healed_payload,
                    key_mappings=key_mappings,
                    mapping_versions=mapping_versions or {},
                    ai_telemetry=ai_telemetry,
                    validation_errors=validation_errors or [],
                    reason=reason,
                )
            )
            await session.flush()
            session.add(EventLifecycle(
                event_id=event_id,
                bridge_id=bridge_id,
                account_id=account_id,
                state="received",
                reason=reason,
            ))
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def append_event_lifecycle(
    *,
    event_id: Any,
    bridge_id: Any,
    account_id: Any,
    state: str,
    job_id: Any | None = None,
    attempt_number: int | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if async_session is None:
        return
    async with async_session() as session:
        session.add(EventLifecycle(
            event_id=event_id,
            bridge_id=bridge_id,
            account_id=account_id,
            job_id=job_id,
            state=state,
            attempt_number=attempt_number,
            reason=reason,
            lifecycle_metadata=metadata or {},
        ))
        await session.commit()


async def append_job_lifecycle(
    *,
    job_id: Any,
    state: str,
    attempt_number: int | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if async_session is None:
        return
    async with async_session() as session:
        job = await session.get(DeliveryJob, job_id)
        if job is None:
            return
        session.add(EventLifecycle(
            event_id=job.event_id,
            bridge_id=job.bridge_id,
            account_id=job.account_id,
            job_id=job.job_id,
            state=state,
            attempt_number=attempt_number,
            reason=reason,
            lifecycle_metadata=metadata or {},
        ))
        await session.commit()


async def fetch_recoverable_delivery_jobs(stale_seconds: int = 300) -> list[DeliveryJob]:
    if async_session is None:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)
    async with async_session() as session:
        result = await session.execute(
            select(DeliveryJob).where(
                ((DeliveryJob.status.in_(["queued", "retrying"])) & (DeliveryJob.next_attempt_at <= datetime.now(timezone.utc)))
                | ((DeliveryJob.status == "delivering") & (DeliveryJob.created_at <= cutoff))
            ).order_by(DeliveryJob.created_at).with_for_update(skip_locked=True)
        )
        jobs = list(result.scalars())
        for job in jobs:
            job.status = "delivering"
        await session.commit()
        return jobs


async def fetch_reconciliation(bridge_id: Any, account_id: Any) -> dict[str, int]:
    if async_session is None:
        return {"received_count": 0, "delivered_count": 0, "failed_count": 0, "pending_count": 0, "dead_letter_count": 0, "unaccounted_count": 0}
    async with async_session() as session:
        received = await session.scalar(select(func.count()).select_from(EventLifecycle).where(EventLifecycle.account_id == account_id, EventLifecycle.bridge_id == bridge_id, EventLifecycle.state == "received")) or 0
        delivered = await session.scalar(select(func.count(func.distinct(EventLifecycle.event_id))).where(EventLifecycle.account_id == account_id, EventLifecycle.bridge_id == bridge_id, EventLifecycle.state == "delivered")) or 0
        failed = await session.scalar(select(func.count(func.distinct(EventLifecycle.event_id))).where(EventLifecycle.account_id == account_id, EventLifecycle.bridge_id == bridge_id, EventLifecycle.state == "delivery_failed")) or 0
        dead_letter = await session.scalar(select(func.count(func.distinct(EventLifecycle.event_id))).where(EventLifecycle.account_id == account_id, EventLifecycle.bridge_id == bridge_id, EventLifecycle.state == "dead_lettered")) or 0
        terminal = await session.scalar(select(func.count(func.distinct(EventLifecycle.event_id))).where(EventLifecycle.account_id == account_id, EventLifecycle.bridge_id == bridge_id, EventLifecycle.state.in_(["delivered", "delivery_failed", "dead_lettered", "rejected", "dropped", "idempotency_blocked"]))) or 0
        pending = max(received - terminal, 0)
        return {"received_count": received, "delivered_count": delivered, "failed_count": failed, "pending_count": pending, "dead_letter_count": dead_letter, "unaccounted_count": max(received - terminal - pending, 0)}


async def mark_delivery_failed(event_id: Any, error_message: str) -> None:
    if async_session is None:
        return

    async with async_session() as session:
        try:
            await session.execute(
                update(HealingEventRecord)
                .where(HealingEventRecord.event_id == event_id)
                .values(status="delivery_failed", reason=error_message)
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def mark_idempotency_blocked(event_id: Any, idempotency_key: str) -> None:
    if async_session is None:
        return
    async with async_session() as session:
        try:
            await session.execute(
                update(HealingEventRecord)
                .where(HealingEventRecord.event_id == event_id)
                .values(
                    status="idempotency_blocked",
                    reason=f"Duplicate delivery suppressed for idempotency key {idempotency_key}",
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def claim_idempotency_key(
    bridge_id: Any,
    event_id: Any,
    idempotency_key: str,
    ttl_seconds: int = 86400,
) -> bool:
    if async_session is None:
        return True
    async with async_session() as session:
        try:
            now = datetime.now(timezone.utc)
            existing = await session.scalar(
                select(IdempotencyClaim).where(
                    IdempotencyClaim.bridge_id == bridge_id,
                    IdempotencyClaim.idempotency_key == idempotency_key,
                    IdempotencyClaim.expires_at > now,
                )
            )
            if existing is not None:
                return existing.event_id == event_id
            await session.execute(
                update(IdempotencyClaim)
                .where(IdempotencyClaim.expires_at <= now)
                .values(expires_at=now)
            )
            session.add(
                IdempotencyClaim(
                    bridge_id=bridge_id,
                    event_id=event_id,
                    idempotency_key=idempotency_key,
                    expires_at=datetime.fromtimestamp(
                        now.timestamp() + ttl_seconds, timezone.utc
                    ),
                )
            )
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False
        except Exception:
            await session.rollback()
            raise


async def claim_digest_run(bridge_id: Any, period_start: datetime) -> bool:
    if async_session is None:
        return False
    async with async_session() as session:
        try:
            session.add(DigestRun(bridge_id=bridge_id, period_start=period_start))
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False
        except Exception:
            await session.rollback()
            raise


async def create_delivery_job(
    *,
    event_id: Any,
    bridge_id: Any,
    payload: dict[str, Any],
    target_url: str,
    idempotency_key: str | None = None,
    account_id: Any = DEFAULT_ACCOUNT_ID,
) -> DeliveryJob | None:
    if async_session is None:
        return None
    async with async_session() as session:
        try:
            job = DeliveryJob(
                                account_id=account_id,
                event_id=event_id,
                bridge_id=bridge_id,
                payload=payload,
                target_url=target_url,
                idempotency_key=idempotency_key,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job
        except Exception:
            await session.rollback()
            raise


async def update_delivery_job(
    job_id: Any,
    *,
    status: str,
    attempt_count: int,
    last_error: str | None = None,
    next_attempt_at: datetime | None = None,
) -> None:
    if async_session is None:
        return
    values: dict[str, Any] = {
        "status": status,
        "attempt_count": attempt_count,
        "last_error": last_error,
    }
    if next_attempt_at is not None:
        values["next_attempt_at"] = next_attempt_at
    if status in {"delivered", "dead_lettered", "idempotency_blocked"}:
        values["completed_at"] = datetime.now(timezone.utc)
    async with async_session() as session:
        try:
            await session.execute(
                update(DeliveryJob).where(DeliveryJob.job_id == job_id).values(**values)
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def record_delivery_attempt(
    job_id: Any,
    attempt_number: int,
    status: str,
    *,
    error_message: str | None = None,
    http_status: int | None = None,
    response_body: str | None = None,
) -> None:
    if async_session is None:
        return
    async with async_session() as session:
        try:
            session.add(
                DeliveryAttempt(
                    job_id=job_id,
                    attempt_number=attempt_number,
                    status=status,
                    error_message=error_message,
                    http_status=http_status,
                    response_body=response_body,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_delivery_job(job_id: Any) -> DeliveryJob | None:
    if async_session is None:
        return None
    async with async_session() as session:
        result = await session.execute(
            select(DeliveryJob).where(DeliveryJob.job_id == job_id)
        )
        return result.scalar_one_or_none()


async def fetch_event_audit(event_id: Any, bridge_id: Any) -> dict[str, Any] | None:
    if async_session is None:
        return None
    async with async_session() as session:
        event_result = await session.execute(
            select(HealingEventRecord).where(
                HealingEventRecord.event_id == event_id,
                HealingEventRecord.bridge_id == bridge_id,
            )
        )
        event = event_result.scalar_one_or_none()
        if event is None:
            return None

        jobs_result = await session.execute(
            select(DeliveryJob)
            .where(
                DeliveryJob.event_id == event_id,
                DeliveryJob.bridge_id == bridge_id,
            )
            .order_by(DeliveryJob.created_at)
        )
        jobs = list(jobs_result.scalars())
        job_ids = [job.job_id for job in jobs]
        attempts_result = await session.execute(
            select(DeliveryAttempt)
            .where(DeliveryAttempt.job_id.in_(job_ids))
            .order_by(DeliveryAttempt.started_at)
        ) if job_ids else None
        attempts_by_job: dict[Any, list[dict[str, Any]]] = {job_id: [] for job_id in job_ids}
        if attempts_result is not None:
            for attempt in attempts_result.scalars():
                attempts_by_job[attempt.job_id].append(
                    {
                        "attempt_id": str(attempt.attempt_id),
                        "attempt_number": attempt.attempt_number,
                        "status": attempt.status,
                        "http_status": attempt.http_status,
                        "response_body": attempt.response_body,
                        "error_message": attempt.error_message,
                        "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
                        "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
                    }
                )

        job_payloads = [
            {
                "job_id": str(job.job_id),
                "original_job_id": str(job.original_job_id) if job.original_job_id else None,
                "status": job.status,
                "payload": job.payload,
                "target_url": job.target_url,
                "attempt_count": job.attempt_count,
                "last_error": job.last_error,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "attempts": attempts_by_job[job.job_id],
            }
            for job in jobs
        ]
        return {
            "event_id": str(event.event_id),
            "bridge_id": str(event.bridge_id),
            "status": event.status,
            "raw_payload": event.raw_payload,
            "normalized_payload": event.normalized_payload,
            "healed_payload": event.healed_payload,
            "raw_payload_sha256": event.raw_payload_sha256,
            "key_mappings": event.key_mappings,
            "mapping_versions": event.mapping_versions,
            "ai_telemetry": event.ai_telemetry,
            "validation_errors": event.validation_errors,
            "reason": event.reason,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "delivery_jobs": job_payloads,
        }


async def replay_delivery_job(job_id: Any) -> DeliveryJob | None:
    job = await get_delivery_job(job_id)
    if job is None:
        return None
    if async_session is None:
        return None
    if job.status not in {"delivery_failed", "dead_lettered", "retrying"}:
        return None
    async with async_session() as session:
        try:
            replay = DeliveryJob(
                account_id=job.account_id,
                event_id=job.event_id,
                original_job_id=job.original_job_id or job.job_id,
                replay_count=job.replay_count + 1,
                bridge_id=job.bridge_id,
                payload=job.payload,
                target_url=job.target_url,
                idempotency_key=job.idempotency_key,
                status="queued",
                attempt_count=0,
                last_error=f"Replay of delivery job {job.job_id}",
            )
            session.add(replay)
            await session.commit()
            await session.refresh(replay)
            return replay
        except Exception:
            await session.rollback()
            raise


async def list_replayable_jobs(account_id: Any, bridge_id: Any, status: str, from_timestamp: datetime | None = None, to_timestamp: datetime | None = None, limit: int = 500) -> list[DeliveryJob]:
    if async_session is None:
        return []
    async with async_session() as session:
        query = select(DeliveryJob).where(
            DeliveryJob.account_id == account_id,
            DeliveryJob.bridge_id == bridge_id,
            DeliveryJob.status == status,
        )
        if from_timestamp is not None:
            query = query.where(DeliveryJob.created_at >= from_timestamp)
        if to_timestamp is not None:
            query = query.where(DeliveryJob.created_at <= to_timestamp)
        result = await session.execute(query.order_by(DeliveryJob.created_at).limit(limit))
        return list(result.scalars())


async def promote_ai_healing(
    event_id: Any,
    healed_payload: dict[str, Any],
    key_mappings: dict[str, str],
    reason: str,
    ai_telemetry: dict[str, Any] | None = None,
    bridge_id: Any | None = None,
) -> None:
    if async_session is None:
        return

    async with async_session() as session:
        try:
            result = await session.execute(
                select(HealingEventRecord)
                .where(HealingEventRecord.event_id == event_id)
                .with_for_update()
            )
            event = result.scalar_one_or_none()
            if event is None or (bridge_id is not None and event.bridge_id != bridge_id):
                raise LookupError("Event was not found for this bridge")
            if event.status != "uncertain":
                raise ValueError("Only uncertain events can be AI-healed")
            event.status = "healed"
            event.healed_payload = healed_payload
            event.key_mappings = key_mappings
            event.ai_telemetry = ai_telemetry
            event.reason = reason
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def update_event_reason(event_id: Any, reason: str) -> None:
    if async_session is None:
        return

    async with async_session() as session:
        try:
            await session.execute(
                update(HealingEventRecord)
                .where(HealingEventRecord.event_id == event_id)
                .values(reason=reason)
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def resolve_triage_event(
    event_id: Any,
    *,
    action: str,
    target_key: str | None = None,
    actor: str = "triage-operator",
    account_id: Any = DEFAULT_ACCOUNT_ID,
) -> dict[str, Any]:
    if async_session is None:
        raise RuntimeError("DATABASE_URL is not configured")

    allowed_keys = {"customer_id", "email_address", "stock_count"}
    async with async_session() as session:
        try:
            result = await session.execute(
                select(HealingEventRecord)
                .where(HealingEventRecord.event_id == event_id)
                .where(HealingEventRecord.account_id == account_id)
                .with_for_update()
            )
            event = result.scalar_one_or_none()
            if event is None:
                raise LookupError("Event was not found")

            if event.status != "uncertain":
                raise ValueError("Only uncertain events can be resolved through triage")

            if action == "drop":
                event.status = "dropped"
                event.reason = "Manually dropped from triage by an operator"
                await session.commit()
                return {"event_id": str(event_id), "status": event.status}

            if target_key not in allowed_keys:
                raise ValueError("target_key must be customer_id, email_address, or stock_count")

            source_keys = [key for key in event.raw_payload if key not in allowed_keys]
            if len(source_keys) != 1:
                raise ValueError("The event must contain exactly one unrecognized field")
            source_key = source_keys[0]

            healed_payload = dict(event.healed_payload)
            if target_key in healed_payload:
                raise ValueError("The selected target field already exists in the payload")
            healed_payload[target_key] = healed_payload.pop(source_key, event.raw_payload[source_key])
            key_mappings = {**event.key_mappings, source_key: target_key}
            event.status = "healed"
            event.healed_payload = healed_payload
            event.key_mappings = key_mappings
            event.reason = f"Manually mapped {source_key} to {target_key}"

            revision_result = await session.execute(
                select(func.coalesce(func.max(MappingRule.revision), 0)).where(
                    MappingRule.bridge_id == event.bridge_id,
                    MappingRule.source_field == source_key,
                )
            )
            session.add(
                MappingRule(
                    bridge_id=event.bridge_id,
                    source_field=source_key,
                    destination_field=target_key,
                    revision=int(revision_result.scalar_one()) + 1,
                    status="proposed",
                    created_by=actor,
                    reason=f"Manual triage proposal for event {event_id}",
                )
            )

            await session.commit()
            return {
                "event_id": str(event_id),
                "status": event.status,
                "payload": healed_payload,
                "mapping": {source_key: target_key},
                "bridge_id": str(event.bridge_id) if event.bridge_id else None,
            }
        except Exception:
            await session.rollback()
            raise
