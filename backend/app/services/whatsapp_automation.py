"""
WhatsApp Automation — Send tender alerts via WhatsApp Web using OpenClaw browser control.
Falls back to wa.me links if OpenClaw is unavailable or browser not logged in.

Send flow (learned from interactive session):
  1. Ensure browser is running (not headless, already logged into WhatsApp Web)
  2. Focus the logged-in WhatsApp tab (t3 or first WhatsApp tab)
  3. Click "New chat" button
  4. Click "Phone number" to open keypad
  5. Type phone number into the keypad input
  6. Click the contact result that appears
  7. Wait for message input area
  8. Type message and press Enter
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .openclaw_client import openclaw_client
from .whatsapp_service import whatsapp_service

logger = logging.getLogger("procureflow.whatsapp_automation")

WHATSAPP_URL = "https://web.whatsapp.com"


class WhatsAppAutomation:
    def __init__(self):
        self._session_dir = Path(os.getenv("TENDERAI_DIR", "./runtime")) / "whatsapp_session"
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._logged_in = False
        self._wa_tab_id = None

    async def is_openclaw_available(self) -> bool:
        return await openclaw_client.is_available()

    async def ensure_browser(self) -> bool:
        status = await openclaw_client.is_available()
        if not status:
            result = await openclaw_client.start(headless=False)
            if not result.get("success"):
                return False
        return True

    async def _find_whatsapp_tab(self) -> Optional[str]:
        """Find the already-logged-in WhatsApp tab from open tabs."""
        tabs_result = await openclaw_client.get_tabs()
        if not tabs_result.get("success"):
            return None
        output = tabs_result.get("output", "")
        lines = output.strip().split("\n")
        for line in lines:
            if "WhatsApp" in line and WHATSAPP_URL in line:
                m = re.search(r'\[use: (\S+)\]', line)
                if m:
                    tab = m.group(1)
                    logger.info(f"Found WhatsApp tab: {tab}")
                    return tab
                m2 = re.search(r'\bt(\d+)\b', line)
                if m2:
                    tab = f"t{m2.group(1)}"
                    logger.info(f"Found WhatsApp tab (alt): {tab}")
                    return tab
        return None

    async def login_whatsapp(self) -> bool:
        if self._logged_in:
            return True
        try:
            tabs = await openclaw_client.get_tabs()
            output = tabs.get("output", "")
            if "WhatsApp" in output and "web.whatsapp.com" in output:
                self._logged_in = True
                wa_tab = await self._find_whatsapp_tab()
                if wa_tab:
                    self._wa_tab_id = wa_tab
                session_file = self._session_dir / "session.json"
                session_file.write_text(json.dumps({"logged_in": True, "time": datetime.utcnow().isoformat()}))
                return True

            await openclaw_client.navigate(WHATSAPP_URL)
            snap = await openclaw_client.snapshot(efficient=True)
            out = snap.get("output", "")
            if "Chats" in out or "Search" in out or "New chat" in out:
                self._logged_in = True
                wa_tab = await self._find_whatsapp_tab()
                if wa_tab:
                    self._wa_tab_id = wa_tab
                session_file = self._session_dir / "session.json"
                session_file.write_text(json.dumps({"logged_in": True, "time": datetime.utcnow().isoformat()}))
                return True
            return False
        except Exception as e:
            logger.warning(f"WhatsApp login check failed: {e}")
            return False

    def _extract_ref(self, snapshot_output: str, pattern: str) -> Optional[str]:
        """Extract element ref from snapshot by matching a label/pattern."""
        lines = snapshot_output.strip().split("\n")
        for line in lines:
            if pattern.lower() in line.lower():
                m = re.search(r'\[ref=(\w+)\]', line)
                if m:
                    return m.group(1)
        return None

    async def _find_contact_ref(self, output: str, input_ref: str, new_chat_ref: str, phone_btn_ref: str) -> Optional[str]:
        lines = output.strip().split("\n")
        for line in lines:
            if re.search(r'\[ref=(\w+)\]', line) and not any(
                x in line for x in ["Chats", "Status", "Menu", "Back", "Phone number",
                                      "New group", "New contact", "New community", "Disabled", "textbox",
                                      "button"]
            ):
                m = re.search(r'\[ref=(\w+)\]', line)
                candidate = m.group(1)
                if candidate not in (input_ref, new_chat_ref, phone_btn_ref):
                    return candidate
        return None

    async def send_message(self, phone_number: str, message: str) -> Dict[str, Any]:
        try:
            if not await self.ensure_browser():
                return {
                    "success": False, "method": "wa_link",
                    "error": "OpenClaw unavailable",
                    "link": whatsapp_service.get_wa_link(message, phone_number),
                }

            if not await self.login_whatsapp():
                fallback_link = whatsapp_service.get_wa_link(message, phone_number)
                return {
                    "success": False, "method": "wa_link",
                    "error": "WhatsApp not logged in. Start browser and scan QR code first.",
                    "link": fallback_link,
                }

            if self._wa_tab_id:
                await openclaw_client.focus_tab(self._wa_tab_id)
                await openclaw_client.press("Escape")
                await openclaw_client.press("Escape")

            snap = await openclaw_client.snapshot(efficient=True)
            output = snap.get("output", "")

            new_chat_ref = self._extract_ref(output, "New chat")
            if not new_chat_ref:
                fallback_link = whatsapp_service.get_wa_link(message, phone_number)
                return {
                    "success": False, "method": "wa_link",
                    "error": "Could not find 'New chat' button",
                    "link": fallback_link,
                }

            await openclaw_client.click(new_chat_ref)
            await asyncio.sleep(2)

            snap2 = await openclaw_client.snapshot(efficient=True)
            out2 = snap2.get("output", "")

            phone_btn_ref = self._extract_ref(out2, "Phone number")
            if phone_btn_ref:
                await openclaw_client.click(phone_btn_ref)
                await asyncio.sleep(2)

                snap3 = await openclaw_client.snapshot(efficient=True)
                out3 = snap3.get("output", "")

                full_number = "88" + phone_number if not phone_number.startswith("+") and not phone_number.startswith("88") else phone_number
                full_number = full_number.lstrip("+")
                for ch in full_number:
                    await openclaw_client.press(ch)
                    await asyncio.sleep(0.1)

                await asyncio.sleep(3)

                snap4 = await openclaw_client.snapshot(efficient=True)
                out4 = snap4.get("output", "")

                contact_ref = self._extract_ref(out4, "Zakaria Himel")
                if not contact_ref:
                    contact_ref = await self._find_contact_ref(out4, "", new_chat_ref, phone_btn_ref)

                if contact_ref:
                    await openclaw_client.click(contact_ref)
                else:
                    await openclaw_client.press("Enter")

                await asyncio.sleep(3)
            else:
                search_ref = self._extract_ref(out2, "Search name or number")
                if search_ref:
                    await openclaw_client.type_text(search_ref, phone_number)
                    await asyncio.sleep(2)
                    snap_s = await openclaw_client.snapshot(efficient=True)
                    out_s = snap_s.get("output", "")
                    first_contact = self._extract_ref(out_s, "button")
                    if first_contact:
                        await openclaw_client.click(first_contact)
                        await asyncio.sleep(3)

            snap5 = await openclaw_client.snapshot(efficient=True)
            out5 = snap5.get("output", "")
            msg_ref = self._extract_ref(out5, "Type a message")
            if msg_ref:
                await openclaw_client.type_text(msg_ref, message, submit=True)
            else:
                textbox_refs = re.findall(r'\[ref=(\w+)\].*?textbox', out5)
                if textbox_refs:
                    last_ref = textbox_refs[-1]
                    await openclaw_client.type_text(last_ref, message, submit=True)
                else:
                    await asyncio.sleep(1)
                    snap_final = await openclaw_client.snapshot(efficient=True)
                    out_final = snap_final.get("output", "")
                    refs = re.findall(r'\[ref=(\w+)\]', out_final)
                    if refs:
                        await openclaw_client.type_text(refs[-1], message, submit=True)
                    else:
                        await openclaw_client.press("Enter")

            alert_record = {
                "phone": phone_number,
                "message": message[:100],
                "method": "openclaw",
                "status": "sent",
                "timestamp": datetime.utcnow().isoformat(),
            }
            alerts_file = self._session_dir / "sent_alerts.jsonl"
            with open(alerts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert_record, ensure_ascii=False) + "\n")

            return {"success": True, "method": "openclaw", "message": "Message sent via WhatsApp Web"}

        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            link = whatsapp_service.get_wa_link(message, phone_number)
            return {"success": False, "method": "wa_link", "error": str(e), "link": link}

    async def send_tender_alert(self, tender: Dict[str, Any], phone: str = "", lang: str = "bn") -> Dict[str, Any]:
        msg = whatsapp_service.format_tender_alert(tender, lang=lang)
        phone = phone or whatsapp_service.default_phone
        result = await self.send_message(phone, msg)
        whatsapp_service.save_alert(tender, lang=lang)
        return result

    async def send_batch_alerts(self, tenders: List[Dict[str, Any]], phone: str = "", lang: str = "bn") -> Dict[str, Any]:
        phone = phone or whatsapp_service.default_phone
        msg = whatsapp_service.format_summary(tenders, lang=lang)

        result = await self.send_message(phone, msg)

        summary_link = whatsapp_service.get_summary_wa_link(tenders, phone=phone, lang=lang)
        return {
            "success": result.get("success", False),
            "method": result.get("method", "wa_link"),
            "total": len(tenders),
            "single_result": result,
            "summary_link": summary_link,
            "summary_message": msg,
        }

    async def check_login_status(self) -> Dict[str, Any]:
        if not await self.ensure_browser():
            return {"logged_in": False, "openclaw_available": False}
        logged_in = await self.login_whatsapp()
        return {"logged_in": logged_in, "openclaw_available": True, "tab_id": self._wa_tab_id}

    async def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        alerts_file = self._session_dir / "sent_alerts.jsonl"
        if not alerts_file.exists():
            return []
        alerts = []
        with open(alerts_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    alerts.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return alerts[-limit:]


import asyncio
whatsapp_automation = WhatsAppAutomation()
