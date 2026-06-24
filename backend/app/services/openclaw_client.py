"""
OpenClaw Client — Local browser automation via openclaw CLI.
Controls Chromium for WhatsApp, eGP portal, and tender document scraping.
"""

import json
import logging
import os
import re
import shlex
import subprocess
import asyncio
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger("procureflow.openclaw")


class OpenClawError(Exception):
    pass


class OpenClawClient:
    def __init__(self, base_url: str = "http://localhost:18789"):
        self.base_url = base_url
        self._cli = self._find_cli()
        self._temp_dir = Path(os.getenv("TENDERAI_DIR", "./runtime")) / "openclaw"
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    def _find_cli(self) -> str:
        for candidate in ["openclaw", "npx openclaw", "claw"]:
            try:
                subprocess.run([candidate.split()[0], "--version"], capture_output=True, timeout=5)
                return candidate
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return "openclaw"

    async def _run(self, *args: str, timeout: int = 60) -> Dict[str, Any]:
        cmd = f"{self._cli} browser {' '.join(args)}"
        logger.debug(f"OpenClaw: {cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out = stdout.decode().strip()
            if stderr:
                err = stderr.decode().strip()
                if err:
                    logger.warning(f"OpenClaw stderr: {err}")
            return {"success": True, "output": out}
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Command timed out ({timeout}s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def is_available(self) -> bool:
        result = await self._run("status", "--json", timeout=10)
        return result.get("success", False)

    async def start(self, headless: bool = False) -> Dict[str, Any]:
        flag = "--headless" if headless else ""
        return await self._run("start", flag, timeout=30) if flag else await self._run("start", timeout=30)

    async def stop(self) -> Dict[str, Any]:
        return await self._run("stop", timeout=15)

    async def navigate(self, url: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        cmd = ["navigate", url]
        if tab_id:
            cmd.extend(["--tab", tab_id])
        return await self._run(*cmd, timeout=30)

    async def snapshot(self, tab_id: Optional[str] = None, efficient: bool = False) -> Dict[str, Any]:
        cmd = ["snapshot"]
        if efficient:
            cmd.append("--efficient")
        if tab_id:
            cmd.extend(["--tab", tab_id])
        return await self._run(*cmd, timeout=30)

    async def screenshot(self, path: Optional[str] = None, tab_id: Optional[str] = None) -> Dict[str, Any]:
        cmd = ["screenshot"]
        if path:
            cmd.extend(["--path", path])
        if tab_id:
            cmd.extend(["--tab", tab_id])
        return await self._run(*cmd, timeout=30)

    async def act(self, kind: str, ref: Optional[str] = None, value: Optional[str] = None, tab_id: Optional[str] = None) -> Dict[str, Any]:
        cmd = [kind]
        if ref:
            cmd.append(ref)
        if value:
            cmd.append(value)
        if tab_id:
            cmd.extend(["--tab", tab_id])
        return await self._run("act", *cmd, timeout=30)

    async def type_text(self, ref: str, text: str, submit: bool = False, tab_id: Optional[str] = None) -> Dict[str, Any]:
        args = ["type", ref, shlex.quote(text)]
        if submit:
            args.append("--submit")
        if tab_id:
            args.extend(["--tab", tab_id])
        return await self._run(*args, timeout=30)

    async def click(self, ref: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        cmd = ["click", ref]
        if tab_id:
            cmd.extend(["--tab", tab_id])
        return await self._run(*cmd, timeout=30)

    async def press(self, key: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        cmd = ["press", key]
        if tab_id:
            cmd.extend(["--tab", tab_id])
        return await self._run(*cmd, timeout=15)

    async def focus_tab(self, tab_id: str) -> Dict[str, Any]:
        return await self._run("focus", tab_id, timeout=10)

    async def wait_for(self, text: Optional[str] = None, timeout_ms: int = 10000, tab_id: Optional[str] = None) -> Dict[str, Any]:
        cmd = ["wait"]
        if text:
            cmd.extend(["--text", text])
        cmd.extend(["--timeout-ms", str(timeout_ms)])
        if tab_id:
            cmd.extend(["--tab", tab_id])
        return await self._run(*cmd, timeout=(timeout_ms // 1000) + 5)

    async def get_tabs(self) -> Dict[str, Any]:
        return await self._run("tabs", "--json", timeout=10)

    async def open_tab(self, url: Optional[str] = None) -> Dict[str, Any]:
        cmd = ["tab", "new"]
        if url:
            cmd.append(url)
        return await self._run(*cmd, timeout=15)

    async def close_tab(self, tab_id: str) -> Dict[str, Any]:
        return await self._run("tab", "close", tab_id, timeout=10)

    async def evaluate(self, js: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        cmd = ["evaluate", "--fn", js]
        if tab_id:
            cmd.extend(["--tab", tab_id])
        return await self._run(*cmd, timeout=15)


openclaw_client = OpenClawClient()
