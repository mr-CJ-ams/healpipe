from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from collections.abc import Sequence

import aiosmtplib

from database.models import HealingEventRecord


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertTemplate:
    subject: str
    text: str
    html: str
    send_immediately: bool = True


def _mail_settings() -> dict[str, str | int] | None:
    required = {
        "host": os.getenv("SMTP_HOST"),
        "username": os.getenv("SMTP_USERNAME"),
        "password": os.getenv("SMTP_PASSWORD"),
        "sender": os.getenv("ALERT_FROM_EMAIL"),
        "recipient": os.getenv("ALERT_TO_EMAIL"),
    }
    if not all(required.values()):
        logger.warning("Pipeline alert was skipped because SMTP configuration is incomplete")
        return None

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        logger.warning("Pipeline alert was skipped because SMTP_PORT is invalid")
        return None

    return {**required, "port": port}


def _validated_template(event_id: str, details: str) -> AlertTemplate:
    return AlertTemplate(
        subject="HealPipe validation digest",
        text=(
            "HealPipe Validation Digest\n\n"
            f"Event ID: {event_id}\n{details}\n\n"
            "Validated events are compiled into the scheduled weekly or monthly digest."
        ),
        html=(
            "<html><body style=\"font-family:Arial,sans-serif;color:#17211f\">"
            "<h2>HealPipe validation digest</h2>"
            "<p>This event is queued for the scheduled weekly or monthly validation digest.</p>"
            f"<p><strong>Reference event:</strong> {escape(event_id)}</p>"
            f"<p>{escape(details)}</p>"
            "</body></html>"
        ),
        send_immediately=False,
    )


def _healed_template(event_id: str, details: str) -> AlertTemplate:
    return AlertTemplate(
        subject=f"Proof of value: HealPipe rescued event {event_id}",
        text=(
            "HealPipe rescued your data workflow\n\n"
            f"Event ID: {event_id}\n{details}\n\n"
            "Our normalization scripts corrected the format variation before it could cause an integration crash."
        ),
        html=(
            "<html><body style=\"font-family:Arial,sans-serif;color:#17211f;line-height:1.5\">"
            "<section style=\"max-width:620px;padding:28px;border:1px solid #9be7c4;background:#f2fff7\">"
            "<p style=\"color:#047857;font-weight:bold\">HEALPIPE PROOF OF VALUE</p>"
            "<h2>Your workflow was rescued before it could crash</h2>"
            "<p>HealPipe programmatically normalized a format variation and safely kept the integration moving.</p>"
            f"<p><strong>Event ID:</strong> {escape(event_id)}</p><p>{escape(details)}</p>"
            "</section></body></html>"
        ),
    )


def _rejected_template(event_id: str, details: str) -> AlertTemplate:
    return AlertTemplate(
        subject=f"Security alert: HealPipe rejected event {event_id}",
        text=(
            "SECURITY ALERT: Payload rejected\n\n"
            f"Event ID: {event_id}\nFailure timestamp and log: {details}\n\n"
            "Recommended Action Steps:\n"
            "1. Review the source platform record at the failure timestamp.\n"
            "2. Require customer ID and email address before submission.\n"
            "3. Correct the payload and replay it through HealPipe."
        ),
        html=(
            "<html><body style=\"font-family:Arial,sans-serif;background:#111;color:#fff;padding:24px\">"
            "<section style=\"max-width:620px;border:3px solid #ff4d4f;background:#1b0808;padding:28px\">"
            "<p style=\"color:#ff8585;font-weight:bold;letter-spacing:1px\">SECURITY ALERT</p>"
            "<h2 style=\"margin:0\">Payload rejected</h2>"
            f"<p><strong>Event ID:</strong> {escape(event_id)}</p>"
            f"<p><strong>Failure timestamp and execution log:</strong><br>{escape(details)}</p>"
            "<h3>Recommended Action Steps</h3>"
            "<ol><li>Review the source platform record at the failure timestamp.</li>"
            "<li>Require customer ID and email address before submission.</li>"
            "<li>Correct the payload and replay it through HealPipe.</li></ol>"
            "</section></body></html>"
        ),
    )


def _uncertain_template(event_id: str, details: str) -> AlertTemplate:
    dashboard_url = os.getenv("HEALPIPE_DASHBOARD_URL", "http://localhost:5173")
    return AlertTemplate(
        subject=f"Action required: HealPipe event {event_id} needs triage",
        text=(
            "HIGH PRIORITY: Payload requires manual review\n\n"
            f"Event ID: {event_id}\n{details}\n\n"
            f"Complete triage now: {dashboard_url}"
        ),
        html=(
            "<html><body style=\"font-family:Arial,sans-serif;color:#17211f;line-height:1.5\">"
            "<section style=\"max-width:620px;border:2px solid #f59e0b;background:#fff9eb;padding:28px\">"
            "<p style=\"color:#b45309;font-weight:bold;letter-spacing:1px\">HIGH PRIORITY</p>"
            "<h2>Payload requires manual review</h2>"
            f"<p><strong>Event ID:</strong> {escape(event_id)}</p><p>{escape(details)}</p>"
            f"<a href=\"{escape(dashboard_url, quote=True)}\" style=\"display:inline-block;background:#047857;color:#fff;padding:12px 18px;text-decoration:none;font-weight:bold\">Open HealPipe triage</a>"
            "</section></body></html>"
        ),
    )


def _delivery_failed_template(event_id: str, details: str) -> AlertTemplate:
    return AlertTemplate(
        subject=f"Delivery failed: HealPipe event {event_id}",
        text=f"Outbound delivery needs attention\n\nEvent ID: {event_id}\n{details}",
        html=(
            "<html><body style=\"font-family:Arial,sans-serif;color:#17211f\">"
            "<h2>Outbound delivery needs attention</h2>"
            f"<p><strong>Event ID:</strong> {escape(event_id)}</p><p>{escape(details)}</p>"
            "</body></html>"
        ),
    )


def _alert_content(event_id: str, status: str, details: str) -> AlertTemplate:
    template_factories = {
        "validated": _validated_template,
        "healed": _healed_template,
        "rejected": _rejected_template,
        "uncertain": _uncertain_template,
        "delivery_failed": _delivery_failed_template,
    }
    factory = template_factories.get(status, _delivery_failed_template)
    return factory(event_id, details)


async def _send_template(template: AlertTemplate) -> None:
    if not template.send_immediately:
        logger.info("Validated event queued for scheduled digest")
        return

    settings = _mail_settings()
    if settings is None:
        return

    message = EmailMessage()
    message["From"] = str(settings["sender"])
    message["To"] = str(settings["recipient"])
    message["Subject"] = template.subject
    message.set_content(template.text)
    message.add_alternative(template.html, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=str(settings["host"]),
            port=int(settings["port"]),
            username=str(settings["username"]),
            password=str(settings["password"]),
            start_tls=os.getenv("SMTP_START_TLS", "true").lower() == "true",
            timeout=10,
        )
    except (aiosmtplib.SMTPException, OSError) as error:
        logger.exception("Unable to send pipeline alert: %s", error)


async def send_pipeline_alert(event_id: str, status: str, details: str) -> None:
    """Send a non-blocking operational alert without affecting pipeline execution."""
    await _send_template(_alert_content(event_id, status, details))


async def dispatch_pipeline_alert(event: HealingEventRecord) -> None:
    """Dispatch an alert using a persisted event record snapshot."""
    details = event.reason or f"Pipeline event recorded with status {event.status}."
    await send_pipeline_alert(str(event.event_id), event.status, details)


async def send_weekly_validation_digest(events: Sequence[HealingEventRecord]) -> None:
    """Send the validated-event digest; callers decide the weekly schedule."""
    if not events:
        return
    details = "\n".join(
        f"- {event.event_id}: {event.created_at.isoformat() if event.created_at else 'unknown time'}"
        for event in events
    )
    template = AlertTemplate(
        subject=f"HealPipe weekly validation digest ({len(events)} events)",
        text=f"HealPipe weekly validation digest\n\n{details}",
        html=(
            "<html><body style=\"font-family:Arial,sans-serif;color:#17211f\">"
            f"<h2>HealPipe weekly validation digest</h2><p>{len(events)} validated events.</p>"
            f"<pre>{escape(details)}</pre></body></html>"
        ),
    )
    await _send_template(template)