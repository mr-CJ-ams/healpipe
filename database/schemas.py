from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class OnboardingRequest(BaseModel):
    user_type: str = Field(min_length=1, max_length=64)
    integration_type: str = Field(min_length=1, max_length=64)
    primary_problem: str = Field(min_length=1, max_length=64)
    monthly_volume: str = Field(min_length=1, max_length=64)
    user_role: str = Field(min_length=1, max_length=64)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1)
    mode: Literal["login", "signup"] = "login"


class WebhookReceiveRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    customer_id: str | None = None
    email_address: str | None = None
    stock_count: int | None = None
    phone_number: str | None = None
    source: str = Field(default="diagnostic", min_length=1, max_length=255)
    target_url: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    payload: dict[str, Any] | None = None
    expected_fields: list[str] = Field(
        default_factory=lambda: ["customer_id", "email_address", "stock_count", "phone_number"]
    )

    def as_payload(self) -> dict[str, Any]:
        if self.payload is not None:
            return self.payload
        known_fields = {
            key: value
            for key, value in self.model_dump(
                include={"customer_id", "email_address", "stock_count", "phone_number"}
            ).items()
            if value is not None
        }
        extra_fields = {
            key: value
            for key, value in (self.model_extra or {}).items()
            if key != "target_url"
        }
        return {**known_fields, **extra_fields}


class TriageRequest(BaseModel):
    event_id: UUID
    target_key: str | None = None
    action: Literal["map", "drop"] = "map"


class DataBridgeCreateRequest(BaseModel):
    bridge_name: str = Field(default="Unnamed Connection", min_length=1, max_length=100)
    source_platform: str = Field(..., min_length=1, max_length=255)
    target_endpoint_url: str = Field(..., min_length=1, max_length=2048)


class DataBridgeStatusRequest(BaseModel):
    is_active: bool


class MappingRuleCreateRequest(BaseModel):
    source_field: str = Field(..., min_length=1, max_length=255)
    destination_field: str = Field(..., min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=1000)


class MappingTestRequest(BaseModel):
    payload: dict[str, Any]


class AccountCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class ApiKeyCreateRequest(BaseModel):
    scopes: list[str] = Field(default_factory=lambda: ["events:read", "mappings:read"])
    role: Literal["owner", "admin", "operator", "viewer"] = "operator"


class AuditExportRequest(BaseModel):
    export_format: Literal["json", "csv", "summary", "pdf"] = "json"
    bridge_id: UUID | None = None
    event_id: UUID | None = None
    status: str | None = None
    source_platform: str | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None
class ReplayBatchRequest(BaseModel):
    bridge_id: UUID
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None
    status: Literal["dead_lettered", "delivery_failed", "retrying"] = "dead_lettered"
    payload_override: dict[str, Any] | None = None
    target_url_override: str | None = Field(default=None, max_length=2048)


class HealingEvent(BaseModel):
    event_id: UUID
    source: str
    received_at: datetime
    status: Literal["validated", "healed", "rejected", "uncertain"]
    reason: str | None = None
    key_mappings: dict[str, str] = Field(default_factory=dict)
    normalized_payload: dict[str, Any]


class WebhookReceiveResponse(BaseModel):
    event_id: UUID
    status: Literal["validated", "healed", "rejected", "uncertain"]
    payload: dict[str, Any]
    key_mappings: dict[str, str] = Field(default_factory=dict)
    reason: str | None = None
