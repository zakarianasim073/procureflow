"""Ollama Client - Optional local AI integration for BOQ queries"""

from typing import List, Dict, Any, Optional
import httpx
from app.core.config import settings


class OllamaClient:
    """Client for local Ollama LLM integration"""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self._available = None

    async def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                self._available = r.status_code == 200
        except Exception:
            self._available = False
        return self._available

    async def chat(self, messages: List[Dict[str, str]], lang: str = "en", system_override: Optional[str] = None) -> Dict[str, Any]:
        if not await self.is_available():
            return {"success": False, "content": "Ollama not available", "engine": "ollama"}

        system = system_override or (
            "You are a BOQ (Bill of Quantities) expert assistant for Bangladesh government tenders. "
            "You understand BWDB, LGED, PWD SOR rates, zone classifications, eGP system, "
            "and Bengali tender terminology. Be concise and practical."
        )
        if lang == "bn" and not system_override:
            system += " Respond in formal Bengali using standard tender terminology."

        full = [{"role": "system", "content": system}] + messages

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(f"{self.base_url}/api/chat", json={
                    "model": self.model,
                    "messages": full,
                    "stream": False,
                })
                data = r.json()
                return {
                    "success": True,
                    "content": data.get("message", {}).get("content", ""),
                    "tokens_used": data.get("total_tokens", 0),
                    "engine": f"ollama/{self.model}",
                }
        except Exception as e:
            return {"success": False, "content": f"Ollama error: {str(e)}", "engine": "ollama"}

    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models from Ollama."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                if r.status_code == 200:
                    data = r.json()
                    return data.get("models", [])
                return []
        except Exception:
            return []
