from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


DEFAULT_ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AccountMember(Base):
    __tablename__ = "account_members"

    membership_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True, default=DEFAULT_ACCOUNT_ID)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("account_id", "actor_id", name="uq_account_member_actor"),)


class GoogleIdentity(Base):
    __tablename__ = "google_identities"

    identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True)
    google_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
class OnboardingProfile(Base):
    __tablename__ = "onboarding_profiles"

    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, unique=True, index=True)
    user_type: Mapped[str] = mapped_column(String(64), nullable=False)
    integration_type: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_problem: Mapped[str] = mapped_column(String(64), nullable=False)
    monthly_volume: Mapped[str] = mapped_column(String(64), nullable=False)
    user_role: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ApiKey(Base):
    __tablename__ = "api_keys"

    key_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True, default=DEFAULT_ACCOUNT_ID)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True, default=DEFAULT_ACCOUNT_ID)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(255), nullable=False)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuditExport(Base):
    __tablename__ = "audit_exports"

    export_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    export_format: Mapped[str] = mapped_column(String(16), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    row_count: Mapped[int] = mapped_column(nullable=False, default=0)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class HealingEventRecord(Base):
    __tablename__ = "healing_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True, default=DEFAULT_ACCOUNT_ID)
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_bridges.bridge_id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    healed_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    key_mappings: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    ai_telemetry: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    mapping_versions: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('validated', 'healed', 'rejected', 'uncertain', 'delivery_failed', 'dropped', 'idempotency_blocked')",
            name="ck_healing_events_status",
        ),
        Index("ix_healing_events_created_at", "created_at"),
    )


class IdempotencyClaim(Base):
    __tablename__ = "idempotency_claims"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True, default=DEFAULT_ACCOUNT_ID)
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_bridges.bridge_id"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("bridge_id", "idempotency_key", name="uq_idempotency_claim_bridge_key"),
        Index("ix_idempotency_claim_expires_at", "expires_at"),
    )


class DigestRun(Base):
    __tablename__ = "digest_runs"

    digest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True, default=DEFAULT_ACCOUNT_ID)
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_bridges.bridge_id"), nullable=False, index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("bridge_id", "period_start", name="uq_digest_run_bridge_period"),
    )


class DeliveryJob(Base):
    __tablename__ = "delivery_jobs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True, default=DEFAULT_ACCOUNT_ID)
    original_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_jobs.job_id"), nullable=True, index=True
    )
    replay_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_bridges.bridge_id"), nullable=False, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'delivering', 'retrying', 'delivered', 'dead_lettered', 'idempotency_blocked')",
            name="ck_delivery_jobs_status",
        ),
        Index("ix_delivery_jobs_next_attempt_at", "next_attempt_at"),
    )


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_jobs.job_id"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status: Mapped[int | None] = mapped_column(nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EventLifecycle(Base):
    __tablename__ = "event_lifecycle"

    lifecycle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True)
    bridge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("data_bridges.bridge_id"), nullable=False, index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("healing_events.event_id"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("delivery_jobs.job_id"), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_number: Mapped[int | None] = mapped_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    __table_args__ = (
        CheckConstraint(
            "state IN ('received', 'validated', 'healed', 'uncertain', 'rejected', 'queued', 'delivering', 'delivery_attempted', 'delivered', 'retrying', 'delivery_failed', 'dead_lettered', 'replayed', 'archived', 'idempotency_blocked')",
            name="ck_event_lifecycle_state",
        ),
        Index("ix_event_lifecycle_account_time", "account_id", "bridge_id", "occurred_at"),
    )


class InventoryMapping(Base):
    __tablename__ = "inventory_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bridge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_bridges.bridge_id"), nullable=True, index=True
    )
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sku: Mapped[str] = mapped_column(String(255), nullable=False)
    target_sku: Mapped[str] = mapped_column(String(255), nullable=False)
    translation_vector: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "supplier_name",
            "source_sku",
            name="uq_inventory_mappings_supplier_source_sku",
        ),
        Index("ix_inventory_mappings_target_sku", "target_sku"),
    )


class MappingRule(Base):
    __tablename__ = "mapping_rules"

    mapping_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True, default=DEFAULT_ACCOUNT_ID)
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_bridges.bridge_id"), nullable=False, index=True
    )
    source_field: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_field: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("bridge_id", "source_field", "revision", name="uq_mapping_rule_revision"),
        CheckConstraint(
            "status IN ('proposed', 'approved', 'active', 'inactive', 'rejected')",
            name="ck_mapping_rule_status",
        ),
        Index("ix_mapping_rules_bridge_status", "bridge_id", "status"),
        Index(
            "uq_mapping_rule_active_source",
            "bridge_id",
            "source_field",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
class DataBridge(Base):
    __tablename__ = "data_bridges"

    bridge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False, index=True, default=DEFAULT_ACCOUNT_ID)
    bridge_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Unnamed Connection", server_default="Unnamed Connection"
    )
    source_platform: Mapped[str] = mapped_column(String(255), nullable=False)
    target_endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    signature_secret: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_data_bridges_source_platform", "source_platform"),)