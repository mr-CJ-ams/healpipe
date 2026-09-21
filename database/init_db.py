from __future__ import annotations

import asyncio
import secrets
import uuid

from sqlalchemy import text

from database.connection import engine
from database.models import Base, DEFAULT_ACCOUNT_ID


async def create_tables() -> None:
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text(
                "INSERT INTO accounts (account_id, name) VALUES (:account_id, 'Legacy Workspace') "
                "ON CONFLICT (account_id) DO NOTHING"
            ),
            {"account_id": DEFAULT_ACCOUNT_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO account_members (membership_id, account_id, actor_id, role) "
                "VALUES (:membership_id, :account_id, 'local-operator', 'owner') "
                "ON CONFLICT (account_id, actor_id) DO NOTHING"
            ),
            {"membership_id": uuid.uuid4(), "account_id": DEFAULT_ACCOUNT_ID},
        )
        for table in ("data_bridges", "healing_events", "delivery_jobs", "idempotency_claims", "digest_runs", "mapping_rules"):
            await connection.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS account_id UUID REFERENCES accounts(account_id)")
            )
        await connection.execute(text("UPDATE data_bridges SET account_id = :account_id WHERE account_id IS NULL"), {"account_id": DEFAULT_ACCOUNT_ID})
        for table in ("healing_events", "delivery_jobs", "idempotency_claims", "digest_runs", "mapping_rules"):
            await connection.execute(
                text(
                    f"UPDATE {table} child SET account_id = bridge.account_id "
                    f"FROM data_bridges bridge WHERE child.bridge_id = bridge.bridge_id AND child.account_id IS NULL"
                )
            )
        for table in ("data_bridges", "healing_events", "delivery_jobs", "idempotency_claims", "digest_runs", "mapping_rules"):
            await connection.execute(text(f"UPDATE {table} SET account_id = :account_id WHERE account_id IS NULL"), {"account_id": DEFAULT_ACCOUNT_ID})
            await connection.execute(text(f"ALTER TABLE {table} ALTER COLUMN account_id SET NOT NULL"))
        await connection.execute(text("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'viewer'"))
        await connection.execute(
            text(
                "ALTER TABLE data_bridges ADD COLUMN IF NOT EXISTS "
                "bridge_name VARCHAR(100) NOT NULL DEFAULT 'Unnamed Connection'"
            )
        )
        await connection.execute(
            text(
                "ALTER TABLE data_bridges ADD COLUMN IF NOT EXISTS "
                "signature_secret VARCHAR(128)"
            )
        )
        bridge_rows = await connection.execute(
            text("SELECT bridge_id FROM data_bridges WHERE signature_secret IS NULL")
        )
        for (bridge_id,) in bridge_rows:
            await connection.execute(
                text(
                    "UPDATE data_bridges SET signature_secret = :secret "
                    "WHERE bridge_id = :bridge_id"
                ),
                {"bridge_id": bridge_id, "secret": secrets.token_urlsafe(48)},
            )
        await connection.execute(
            text("ALTER TABLE data_bridges ALTER COLUMN signature_secret SET NOT NULL")
        )
        await connection.execute(
            text("ALTER TABLE healing_events ALTER COLUMN status TYPE VARCHAR(32)")
        )
        await connection.execute(
            text("ALTER TABLE healing_events DROP CONSTRAINT IF EXISTS ck_healing_events_status")
        )
        await connection.execute(
            text(
                "ALTER TABLE healing_events ADD CONSTRAINT ck_healing_events_status "
                "CHECK (status IN ('validated', 'healed', 'rejected', 'uncertain', 'delivery_failed', 'dropped', 'idempotency_blocked'))"
            )
        )
        await connection.execute(
            text(
                "ALTER TABLE healing_events ADD COLUMN IF NOT EXISTS "
                "bridge_id UUID REFERENCES data_bridges(bridge_id)"
            )
        )
        await connection.execute(
            text(
                "ALTER TABLE healing_events ADD COLUMN IF NOT EXISTS "
                "ai_telemetry JSONB"
            )
        )
        await connection.execute(
            text(
                "ALTER TABLE healing_events ADD COLUMN IF NOT EXISTS "
                "normalized_payload JSONB"
            )
        )
        await connection.execute(
            text("ALTER TABLE healing_events ADD COLUMN IF NOT EXISTS raw_payload_sha256 VARCHAR(64)")
        )
        await connection.execute(
            text(
                "ALTER TABLE healing_events ADD COLUMN IF NOT EXISTS "
                "validation_errors JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        )
        await connection.execute(
            text(
                "UPDATE healing_events SET normalized_payload = raw_payload "
                "WHERE normalized_payload IS NULL"
            )
        )
        await connection.execute(
            text("ALTER TABLE healing_events ALTER COLUMN normalized_payload SET NOT NULL")
        )
        await connection.execute(
            text(
                "ALTER TABLE inventory_mappings ADD COLUMN IF NOT EXISTS "
                "bridge_id UUID REFERENCES data_bridges(bridge_id)"
            )
        )
        await connection.execute(text("ALTER TABLE delivery_jobs ADD COLUMN IF NOT EXISTS original_job_id UUID REFERENCES delivery_jobs(job_id)"))
        await connection.execute(text("ALTER TABLE delivery_jobs ADD COLUMN IF NOT EXISTS replay_count INTEGER NOT NULL DEFAULT 0"))
        await connection.execute(
            text("ALTER TABLE delivery_attempts ADD COLUMN IF NOT EXISTS response_body TEXT")
        )
        await connection.execute(
            text("ALTER TABLE healing_events ADD COLUMN IF NOT EXISTS mapping_versions JSONB NOT NULL DEFAULT '{}'::jsonb")
        )
        await connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_mapping_rule_active_source "
                "ON mapping_rules (bridge_id, source_field) WHERE status = 'active'"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_healing_events_bridge_id "
                "ON healing_events (bridge_id)"
            )
        )
        unscoped_count = await connection.scalar(
            text("SELECT COUNT(*) FROM healing_events WHERE bridge_id IS NULL")
        )
        if unscoped_count:
            quarantine_bridge_id = await connection.scalar(
                text(
                    "SELECT bridge_id FROM data_bridges "
                    "WHERE bridge_name = 'Legacy Event Quarantine' "
                    "AND source_platform = 'legacy' "
                    "ORDER BY created_at LIMIT 1"
                )
            )
            if quarantine_bridge_id is None:
                quarantine_bridge_id = uuid.uuid4()
                await connection.execute(
                    text(
                        "INSERT INTO data_bridges "
                        "(bridge_id, bridge_name, source_platform, target_endpoint_url, is_active) "
                        "VALUES (:bridge_id, 'Legacy Event Quarantine', 'legacy', "
                        "'https://invalid.local/legacy-quarantine', false)"
                    ),
                    {"bridge_id": quarantine_bridge_id},
                )
            await connection.execute(
                text(
                    "UPDATE healing_events SET bridge_id = :bridge_id "
                    "WHERE bridge_id IS NULL"
                ),
                {"bridge_id": quarantine_bridge_id},
            )
        await connection.execute(
            text(
                "ALTER TABLE healing_events ALTER COLUMN bridge_id SET NOT NULL"
            )
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_tables())