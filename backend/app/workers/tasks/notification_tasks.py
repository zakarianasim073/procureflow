"""Notification background tasks."""
from __future__ import annotations

from typing import Any, Dict
from app.workers.celery_app import celery_app
from app.services.notification_service import notification_service


def _build_body(title: str, payload: Dict[str, Any]) -> str:
    lines = [f"<p>{title}</p>"]
    if payload:
        lines.append("<ul>")
        for key, value in payload.items():
            lines.append(f"<li><strong>{key}</strong>: {value}</li>")
        lines.append("</ul>")
    return "".join(lines)


def _persist_and_maybe_send(
    *,
    channel: str,
    subject: str,
    recipient: str,
    body: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    record_path = notification_service.record_system_notification(
        channel=channel,
        subject=subject,
        recipient=recipient,
        status="queued",
        body=body,
        payload=payload,
    )
    if not recipient or not notification_service.smtp_host or not notification_service.smtp_user or not notification_service.smtp_pass:
        return {
            "status": "disabled",
            "record_path": record_path,
            "recipient": recipient,
            "reason": "smtp_not_configured",
        }

    sent = notification_service.send_email(recipient, subject, body)
    return {
        "status": "sent" if sent else "failed",
        "record_path": record_path,
        "recipient": recipient,
    }


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_approval_notification(self, approval_id: int, recipient_email: str) -> dict:
    """Send approval notification email."""
    try:
        subject = f"Procurement approval #{approval_id}"
        body = _build_body(
            "A procurement approval event was recorded.",
            {"approval_id": approval_id, "recipient": recipient_email},
        )
        result = _persist_and_maybe_send(
            channel="approval",
            subject=subject,
            recipient=recipient_email,
            body=body,
            payload={"approval_id": approval_id},
        )
        result["approval_id"] = approval_id
        return result
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3)
def send_order_confirmation(self, order_id: int, vendor_email: str) -> dict:
    """Send order confirmation to vendor."""
    try:
        subject = f"Purchase order #{order_id} confirmation"
        body = _build_body(
            "A purchase order confirmation was recorded.",
            {"order_id": order_id, "recipient": vendor_email},
        )
        result = _persist_and_maybe_send(
            channel="order_confirmation",
            subject=subject,
            recipient=vendor_email,
            body=body,
            payload={"order_id": order_id},
        )
        result["order_id"] = order_id
        return result
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task
def send_vendor_onboarding_email(vendor_id: int, email: str) -> dict:
    """Send vendor onboarding email."""
    subject = f"Vendor onboarding #{vendor_id}"
    body = _build_body(
        "Vendor onboarding was requested and recorded.",
        {"vendor_id": vendor_id, "recipient": email},
    )
    result = _persist_and_maybe_send(
        channel="vendor_onboarding",
        subject=subject,
        recipient=email,
        body=body,
        payload={"vendor_id": vendor_id},
    )
    result["vendor_id"] = vendor_id
    return result
