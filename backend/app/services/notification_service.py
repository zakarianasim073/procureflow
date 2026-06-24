"""
Procurement Flow Specialist BD — Notification Service
Handles tender alerts, email notifications, and in-app notifications.
"""

from __future__ import annotations

import json
import logging
import smtplib
import os
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("procureflow.notifications")


@dataclass
class TenderAlert:
    """A tender alert/notification payload."""
    tender_id: str
    title: str
    procuring_entity: str
    source: str = "eGP"
    match_score: float = 0.0
    estimated_value: float = 0.0
    deadline: str = ""
    alert_type: str = "new_tender"  # new_tender, corrigendum, award, reminder
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class NotificationService:
    """
    Multi-channel notification service.
    Supports: console logging, file-based alerts, email (SMTP).
    """

    def __init__(self):
        self.alerts_dir = os.getenv("TENDERAI_DIR", "./runtime") + "/alerts"
        self.notifications_dir = os.getenv("TENDERAI_DIR", "./runtime") + "/notifications"
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.from_email = os.getenv("NOTIFICATION_FROM", "alerts@procureflow.ai")

    # ── In-App Alerts (JSON file) ────────────────────────────────────────

    def save_alert(self, alert: TenderAlert) -> str:
        """Save an alert to the local alerts directory."""
        Path(self.alerts_dir).mkdir(parents=True, exist_ok=True)
        filepath = Path(self.alerts_dir) / f"{alert.tender_id}_{alert.alert_type}.json"
        with open(filepath, "w") as f:
            json.dump(asdict(alert), f, indent=2, default=str)
        logger.info(f"Alert saved: {alert.alert_type} for {alert.tender_id}")
        return str(filepath)

    def get_alerts(self, limit: int = 20, alert_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent alerts."""
        alerts_dir = Path(self.alerts_dir)
        if not alerts_dir.exists():
            return []
        
        files = sorted(alerts_dir.glob("*.json"), reverse=True)
        results = []
        for f in files[:limit]:
            try:
                with open(f) as fh:
                    alert = json.load(fh)
                    if alert_type and alert.get("alert_type") != alert_type:
                        continue
                    results.append(alert)
            except Exception:
                continue
        return results

    def clear_alerts(self, older_than_days: int = 30) -> int:
        """Clear old alerts."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        count = 0
        for f in Path(self.alerts_dir).glob("*.json"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    f.unlink()
                    count += 1
            except Exception:
                continue
        return count

    def record_system_notification(
        self,
        *,
        channel: str,
        subject: str,
        recipient: str,
        status: str,
        body: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist a system notification audit record for later review."""
        target_dir = Path(self.notifications_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        record = {
            "id": str(uuid.uuid4()),
            "channel": channel,
            "subject": subject,
            "recipient": recipient,
            "status": status,
            "body": body,
            "payload": payload or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path = target_dir / f"{stamp}_{record['id']}.json"
        path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        logger.info("Notification recorded: %s -> %s (%s)", channel, recipient or "n/a", status)
        return str(path)

    # ── Email Notifications ──────────────────────────────────────────────

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send an email notification via SMTP."""
        if not self.smtp_host:
            logger.warning("SMTP not configured — email not sent")
            return False
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email
            
            html = f"""<html><body style="font-family: sans-serif; padding: 20px;">
                <h2 style="color: #1e40af;">Procurement Flow Specialist BD Alert</h2>
                {body}
                <hr><p style="color: #666; font-size: 12px;">
                Procurement Flow Specialist BD — AI Tender Processing</p></body></html>"""
            
            msg.attach(MIMEText(html, "html"))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
            
            logger.info(f"Email sent to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_tender_alert_email(self, to_email: str, alert: TenderAlert) -> bool:
        """Send a formatted tender alert email."""
        subject = f"🔔 {alert.alert_type.replace('_', ' ').title()}: {alert.title[:60]}"
        
        body = f"""
        <h3>{alert.title}</h3>
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Tender ID</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{alert.tender_id}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Entity</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{alert.procuring_entity}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Value</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">৳{alert.estimated_value:,.0f}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Deadline</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{alert.deadline}</td></tr>
            <tr><td style="padding: 8px; font-weight: bold;">Match Score</td>
                <td style="padding: 8px;">{alert.match_score:.0%}</td></tr>
        </table>
        <p style="margin-top: 20px;">
            <a href="https://www.eprocure.gov.bd" style="background: #1e40af; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                View on eGP
            </a>
        </p>
        """
        
        return self.send_email(to_email, subject, body)

    # ── Tender Radar Alerts ──────────────────────────────────────────────

    def process_radar_matches(self, matches: List[Dict[str, Any]], 
                                user_email: Optional[str] = None) -> List[TenderAlert]:
        """Process tender radar matches into alerts."""
        alerts = []
        for match in matches:
            alert = TenderAlert(
                tender_id=match.get("tender_id", ""),
                title=match.get("title", ""),
                procuring_entity=match.get("procuring_entity", ""),
                source=match.get("source", "eGP"),
                match_score=match.get("match_score", 0.0),
                estimated_value=match.get("estimated_value", 0.0),
                deadline=match.get("deadline", ""),
                alert_type="new_tender",
                message=f"New tender match: {match.get('title', '')[:100]}",
            )
            self.save_alert(alert)
            alerts.append(alert)
            
            # Send email if configured
            if user_email:
                self.send_tender_alert_email(user_email, alert)
        
        return alerts


notification_service = NotificationService()
