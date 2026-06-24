"""
Procurement Flow — WhatsApp Notification Service
Generates WhatsApp message links + formatted alert messages.
Uses wa.me links (no API key needed — click to send).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("procureflow.whatsapp")


class WhatsAppService:
    """
    WhatsApp notification service.
    Generates wa.me deep links with pre-formatted tender alert messages.
    Messages can be in English or Bengali.
    """

    def __init__(self):
        self.alerts_dir = os.getenv("TENDERAI_DIR", "./runtime") + "/whatsapp_alerts"
        self.default_phone = os.getenv("WHATSAPP_PHONE", "")  # e.g. 8801712345678

    # ── Message Formatting ──────────────────────────────────────────────

    def format_tender_alert(self, tender: Dict[str, Any], lang: str = "bn") -> str:
        """Format a tender alert as a WhatsApp message (English or Bengali)."""
        title = tender.get("title", "") or ""
        tid = tender.get("tender_id", "") or ""
        entity = tender.get("procuring_entity", "") or ""
        deadline = tender.get("deadline", "") or ""
        value = tender.get("estimated_value_bdt", 0) or 0
        nature = tender.get("detected_nature", tender.get("nature", ""))

        if lang == "bn":
            val_str = f"৳{value:,.0f}" if value else "উল্লেখ নেই"
            return (
                f"\U0001f514 *টেন্ডার এলার্ট — BWDB*\n\n"
                f"\U0001f4cb *টেন্ডার আইডি:* {tid}\n"
                f"\U0001f4d6 *শিরোনাম:* {title[:200]}\n"
                f"\U0001f3e2 *প্রযুক্ত প্রতিষ্ঠান:* {entity[:100]}\n"
                f"\U0001f4b5 *আনুমানিক মূল্য:* {val_str}\n"
                f"\U0001f4c5 *শেষ তারিখ:* {deadline}\n"
                f"\U0001f3af *ধরন:* {nature}\n"
                f"\n"
                f"\U0001f517 *eGP লিংক:* https://www.eprocure.gov.bd\n"
                f"\n"
                f"— Procurement Flow Specialist BD"
            )
        else:
            val_str = f"BDT {value:,.0f}" if value else "N/A"
            return (
                f"\U0001f514 *TENDER ALERT — BWDB*\n\n"
                f"\U0001f4cb *Tender ID:* {tid}\n"
                f"\U0001f4d6 *Title:* {title[:200]}\n"
                f"\U0001f3e2 *Entity:* {entity[:100]}\n"
                f"\U0001f4b5 *Est. Value:* {val_str}\n"
                f"\U0001f4c5 *Deadline:* {deadline}\n"
                f"\U0001f3af *Type:* {nature}\n"
                f"\n"
                f"\U0001f517 *eGP Link:* https://www.eprocure.gov.bd\n"
                f"\n"
                f"— Procurement Flow Specialist BD"
            )

    def format_summary(self, tenders: List[Dict[str, Any]], lang: str = "bn") -> str:
        """Format a summary of multiple tenders."""
        if lang == "bn":
            lines = [
                f"\U0001f4ca *BWDB টেন্ডার সারসংক্ষেপ*\n",
                f"মোট টেন্ডার: {len(tenders)}",
                "",
            ]
            for t in tenders:
                v = t.get("estimated_value_bdt", 0) or 0
                val_str = f"৳{v:,.0f} কোটি" if v else "—"
                title = t.get('title', '')
                title_short = title.replace('\r', ' ').replace('\n', ' ').strip()[:80]
                lines.append(f"\U0001f539 {t.get('tender_id','')} | {val_str} | {t.get('deadline','')[:11]} | {title_short}")
            lines.append(f"\n— Procurement Flow Specialist BD")
            return "\n".join(lines)
        else:
            lines = [
                f"\U0001f4ca *BWDB Tender Summary*\n",
                f"Total tenders: {len(tenders)}",
                "",
            ]
            for t in tenders:
                v = t.get("estimated_value_bdt", 0) or 0
                val_str = f"BDT {v:,.0f} Cr" if v else "—"
                title = t.get('title', '')
                title_short = title.replace('\r', ' ').replace('\n', ' ').strip()[:80]
                lines.append(f"\U0001f539 {t.get('tender_id','')} | {val_str} | {t.get('deadline','')[:11]} | {title_short}")
            lines.append(f"\n— Procurement Flow Specialist BD")
            return "\n".join(lines)

    # ── wa.me Link Generation ──────────────────────────────────────────

    def get_wa_link(self, message: str, phone: str = "") -> str:
        """Generate a wa.me deep link with pre-filled message."""
        p = phone or self.default_phone
        if not p:
            p = "880"  # fallback
        encoded = urllib.parse.quote(message)
        return f"https://wa.me/{p}?text={encoded}"

    def get_tender_wa_link(self, tender: Dict[str, Any], phone: str = "", lang: str = "bn") -> str:
        """Generate a wa.me link for a single tender alert."""
        msg = self.format_tender_alert(tender, lang=lang)
        return self.get_wa_link(msg, phone=phone)

    def get_summary_wa_link(self, tenders: List[Dict[str, Any]], phone: str = "", lang: str = "bn") -> str:
        """Generate a wa.me link for a summary of multiple tenders."""
        msg = self.format_summary(tenders, lang=lang)
        return self.get_wa_link(msg, phone=phone)

    # ── Save Alert to File ──────────────────────────────────────────────

    def save_alert(self, tender: Dict[str, Any], lang: str = "bn") -> str:
        """Save a WhatsApp-ready alert to disk."""
        Path(self.alerts_dir).mkdir(parents=True, exist_ok=True)
        tid = tender.get("tender_id", "unknown")
        msg = self.format_tender_alert(tender, lang=lang)
        link = self.get_tender_wa_link(tender, lang=lang)

        record = {
            "tender_id": tid,
            "message": msg,
            "wa_link": link,
            "phone": self.default_phone,
            "language": lang,
            "created_at": datetime.utcnow().isoformat(),
        }
        fp = Path(self.alerts_dir) / f"{tid}_whatsapp.json"
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        logger.info(f"WhatsApp alert saved: {tid}")
        return str(fp)

    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent WhatsApp alerts."""
        ad = Path(self.alerts_dir)
        if not ad.exists():
            return []
        files = sorted(ad.glob("*_whatsapp.json"), reverse=True)
        results = []
        for f in files[:limit]:
            try:
                results.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return results

    def send_batch_alerts(self, tenders: List[Dict[str, Any]], lang: str = "bn") -> Dict[str, Any]:
        """Process a batch of tenders into WhatsApp alerts."""
        links = []
        count = 0
        for t in tenders:
            try:
                self.save_alert(t, lang=lang)
                link = self.get_tender_wa_link(t, lang=lang)
                links.append({"tender_id": t.get("tender_id", ""), "wa_link": link})
                count += 1
            except Exception as e:
                logger.warning(f"WhatsApp alert failed for {t.get('tender_id', '?')}: {e}")

        # Also create summary
        summary_link = self.get_summary_wa_link(tenders, lang=lang)
        return {
            "success": True,
            "alerts_created": count,
            "tenders": links,
            "summary_link": summary_link,
            "summary_message": self.format_summary(tenders, lang=lang),
        }


whatsapp_service = WhatsAppService()
