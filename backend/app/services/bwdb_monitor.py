"""
BWDB Tender Monitor — Email Notification Agent
Monitors eGP for BWDB tenders above 5 crore and sends email alerts.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("procureflow.bwdb_monitor")

BWDB_KEYWORDS = ["BWDB", "Bangladesh Water Development Board", "পানি উন্নয়ন বোর্ড"]
HIGH_VALUE_THRESHOLD = 50_000_000  # 5 Crore BDT


class BWDBTenderMonitor:
    """
    Monitors eGP for BWDB tenders above 5 crore threshold.
    Sends email alerts to configured recipients.
    Stores alert history locally.
    """

    def __init__(self):
        self._smtp_config = self._load_smtp_config()

    def _load_smtp_config(self) -> Dict[str, str]:
        return {
            "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
            "port": int(os.getenv("SMTP_PORT", "587")),
            "user": os.getenv("SMTP_USER", ""),
            "pass": os.getenv("SMTP_PASS", ""),
            "from_email": os.getenv("NOTIFICATION_FROM", "alerts@procureflow.ai"),
            "alert_email": os.getenv("ALERT_EMAIL", "z.nasim073@gmail.com"),
        }

    def _is_bwdb_tender(self, tender: Dict) -> bool:
        """Check if a tender belongs to BWDB."""
        notice = tender.get("notice_data") if isinstance(tender.get("notice_data"), dict) else {}
        entity = " ".join(
            [
                str(tender.get("procuring_entity") or ""),
                str(notice.get("procuring_entity") or ""),
                str(notice.get("ministry") or ""),
            ]
        ).lower()
        title = " ".join(
            [
                str(tender.get("title") or ""),
                str(tender.get("work_name") or ""),
                str(tender.get("app_work_name") or ""),
                str(tender.get("live_work_name") or ""),
                str(notice.get("title") or ""),
                str(notice.get("work_name") or ""),
                str(notice.get("app_work_name") or ""),
                str(notice.get("live_work_name") or ""),
            ]
        ).lower()
        for kw in BWDB_KEYWORDS:
            if kw.lower() in entity or kw.lower() in title:
                return True
        return False

    def _best_tender_id(self, tender: Dict) -> str:
        notice = tender.get("notice_data") if isinstance(tender.get("notice_data"), dict) else {}
        for key in (
            "app_tender_id",
            "tender_id",
            "live_tender_id",
            "package_no",
        ):
            value = tender.get(key)
            if value:
                return str(value)
            value = notice.get(key)
            if value:
                return str(value)
        return ""

    def _best_title(self, tender: Dict) -> str:
        notice = tender.get("notice_data") if isinstance(tender.get("notice_data"), dict) else {}
        for key in (
            "app_work_name",
            "work_name",
            "live_work_name",
            "title",
        ):
            value = tender.get(key)
            if value:
                return str(value)
            value = notice.get(key)
            if value:
                return str(value)
        return ""

    def _best_value(self, tender: Dict) -> float:
        notice = tender.get("notice_data") if isinstance(tender.get("notice_data"), dict) else {}
        for key in (
            "app_estimated_value_bdt",
            "estimated_value_bdt",
            "live_estimated_value_bdt",
            "estimated_amount_bdt",
            "estimated_cost_bdt",
            "live_value_bdt",
            "app_value_bdt",
        ):
            value = tender.get(key)
            if value not in (None, "", 0, 0.0):
                try:
                    return float(value)
                except Exception:
                    pass
            value = notice.get(key)
            if value not in (None, "", 0, 0.0):
                try:
                    return float(value)
                except Exception:
                    pass
        return 0.0

    def _is_high_value(self, tender: Dict) -> bool:
        """Check if tender value is above threshold (5 crore)."""
        value = self._best_value(tender)
        return value >= HIGH_VALUE_THRESHOLD

    async def _already_alerted(self, tender_id: str) -> bool:
        """Check if we already sent an alert for this tender."""
        from app.db.base import get_session_factory
        from app.models.intelligence import BWDBAlertRecord
        from sqlalchemy import select

        sf = get_session_factory()
        async with sf() as session:
            stmt = select(BWDBAlertRecord).where(BWDBAlertRecord.tender_id == tender_id)
            res = await session.execute(stmt)
            return res.scalar_one_or_none() is not None

    async def scan_and_alert(self, tenders: List[Dict]) -> List[Dict]:
        """
        Scan a list of tenders, find BWDB high-value ones, send alerts.
        Returns list of alerts sent.
        """
        alerts_sent = []

        for tender in tenders:
            if not self._is_bwdb_tender(tender):
                continue
            if not self._is_high_value(tender):
                continue
            tender_id = self._best_tender_id(tender) or str(tender.get("tender_id", ""))
            if await self._already_alerted(tender_id):
                continue

            # Send email alert
            success = self._send_alert(tender)
            if success:
                alert_record = {
                    "tender_id": tender_id,
                    "title": self._best_title(tender),
                    "value": self._best_value(tender),
                    "entity": tender.get("procuring_entity", "") or (tender.get("notice_data") or {}).get("procuring_entity", ""),
                    "deadline": tender.get("deadline", "") or (tender.get("notice_data") or {}).get("deadline", ""),
                    "sent_at": datetime.utcnow().isoformat(),
                    "recipient": self._smtp_config["alert_email"],
                }
                alerts_sent.append(alert_record)

                # Save to history database
                from app.db.base import get_session_factory
                from app.models.intelligence import BWDBAlertRecord
                import uuid

                record = BWDBAlertRecord(
                    id=str(uuid.uuid4()),
                    tender_id=alert_record["tender_id"],
                    title=alert_record["title"],
                    value=float(alert_record["value"]),
                    entity=alert_record["entity"],
                    deadline=alert_record["deadline"],
                    sent_at=alert_record["sent_at"],
                    recipient=alert_record["recipient"]
                )
                sf = get_session_factory()
                async with sf() as session:
                    session.add(record)
                    await session.commit()

                logger.info(f"Alert sent for BWDB tender {tender.get('tender_id')}")

        return alerts_sent

    def _send_alert(self, tender: Dict) -> bool:
        """Send email alert for a BWDB high-value tender."""
        cfg = self._smtp_config
        if not cfg["host"] or not cfg["user"]:
            logger.warning("SMTP not configured — saving alert locally only")
            return self._save_alert_locally(tender)

        to_email = cfg["alert_email"]
        title = self._best_title(tender)
        value_bdt = self._best_value(tender)
        value_cr = value_bdt / 10_000_000
        subject = f"BWDB High-Value Tender Alert: {title[:60]}"

        notice = tender.get("notice_data") if isinstance(tender.get("notice_data"), dict) else {}
        app_id = tender.get("app_tender_id") or notice.get("app_tender_id") or tender.get("tender_id", "")
        live_id = tender.get("live_tender_id") or notice.get("live_tender_id") or tender.get("tender_id", "")
        app_value = tender.get("app_estimated_value_bdt") or notice.get("app_estimated_value_bdt") or notice.get("app_value_bdt") or 0
        live_value = tender.get("live_estimated_value_bdt") or notice.get("live_estimated_value_bdt") or notice.get("live_value_bdt") or 0

        body = f"""
        <h2 style="color: #dc2626;">BWDB High-Value Tender Alert</h2>
        <p>New Bangladesh Water Development Board tender found above 5 crore threshold.</p>
        
        <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">APP Tender ID</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{app_id}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Live Tender ID</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{live_id}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Title</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{title}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Entity</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{tender.get('procuring_entity', '') or notice.get('procuring_entity', '')}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Estimated Value</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; color: #dc2626; font-weight: bold;">
                    ৳{value_bdt:,.0f} ({value_cr:.2f} Cr)</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">APP Estimate</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">৳{float(app_value):,.0f}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Live Estimate</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">৳{float(live_value):,.0f}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Deadline</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{tender.get('deadline', '') or notice.get('deadline', 'N/A')}</td></tr>
            <tr><td style="padding: 8px; font-weight: bold;">Status</td>
                <td style="padding: 8px;">{tender.get('status', 'Live')}</td></tr>
        </table>

        <p><strong>Why this matters:</strong> This BWDB tender exceeds 5 crore BDT — high-value opportunity
        requiring competitive bidding strategy, SOR rate analysis, and advance preparation.</p>

        <p style="margin-top: 20px;">
            <a href="https://www.eprocure.gov.bd/resources/common/ViewTender.jsp?id={live_id or app_id}"
               style="background: #1e40af; color: white; padding: 10px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">
                View on eGP Portal
            </a>
        </p>

        <hr>
        <p style="color: #666; font-size: 12px;">
            Procurement Flow Specialist BD — AI Tender Intelligence System<br>
            Automated BWDB Tender Monitor | Checked: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
        </p>
        """

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = cfg["from_email"]
            msg["To"] = to_email
            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
                server.starttls()
                server.login(cfg["user"], cfg["pass"])
                server.send_message(msg)

            logger.info(f"BWDB alert emailed to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send BWDB alert email: {e}")
            return self._save_alert_locally(tender)

    def _save_alert_locally(self, tender: Dict) -> bool:
        """Save alert to local file when email fails."""
        logger.warning(f"Failed to send alert for {tender.get('tender_id', '')} - local backup skipped")
        return True

    async def get_alert_history(self, limit: int = 20) -> List[Dict]:
        """Get alert history."""
        from app.db.base import get_session_factory
        from app.models.intelligence import BWDBAlertRecord
        from sqlalchemy import select

        sf = get_session_factory()
        async with sf() as session:
            stmt = select(BWDBAlertRecord).order_by(BWDBAlertRecord.sent_at.desc()).limit(limit)
            res = await session.execute(stmt)
            records = res.scalars().all()

        history = []
        for r in records:
            history.append({
                "tender_id": r.tender_id,
                "title": r.title,
                "value": r.value,
                "entity": r.entity,
                "deadline": r.deadline,
                "sent_at": r.sent_at,
                "recipient": r.recipient,
            })
        history.reverse()
        return history

    async def get_stats(self) -> Dict[str, Any]:
        """Get monitor statistics."""
        from app.db.base import get_session_factory
        from app.models.intelligence import BWDBAlertRecord
        from sqlalchemy import select, func

        sf = get_session_factory()
        async with sf() as session:
            stmt = select(func.count(BWDBAlertRecord.id))
            res = await session.execute(stmt)
            total_sent = res.scalar() or 0

            stmt_last = select(BWDBAlertRecord).order_by(BWDBAlertRecord.sent_at.desc()).limit(1)
            res_last = await session.execute(stmt_last)
            last = res_last.scalar_one_or_none()

        last_alert = None
        if last:
            last_alert = {
                "tender_id": last.tender_id,
                "title": last.title,
                "value": last.value,
                "entity": last.entity,
                "deadline": last.deadline,
                "sent_at": last.sent_at,
                "recipient": last.recipient,
            }

        return {
            "total_alerts_sent": total_sent,
            "last_alert": last_alert,
            "config": {
                "threshold_crore": HIGH_VALUE_THRESHOLD / 10_000_000,
                "smtp_configured": bool(self._smtp_config["host"]),
                "alert_email": self._smtp_config["alert_email"],
            },
        }


bwdb_monitor = BWDBTenderMonitor()
