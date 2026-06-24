from __future__ import annotations

import platform
import sys
from typing import Any, Dict, List
from urllib.parse import urlparse, urlunparse

from app.agents import AgentRegistry
from app.core.config import settings


def _sanitize_database_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    netloc = parsed.netloc
    if "@" in netloc:
        credentials, host = netloc.rsplit("@", 1)
        if ":" in credentials:
            username = credentials.split(":", 1)[0]
            netloc = f"{username}:***@{host}"
        else:
            netloc = f"***@{host}"
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def get_repo_facts() -> Dict[str, Any]:
    registry = AgentRegistry()
    supported_stack: List[str] = [
        "FastAPI",
        "React",
        "Vite",
        "TypeScript",
        "PostgreSQL",
        "Celery",
    ]
    if settings.OLLAMA_BASE_URL:
        supported_stack.append("Ollama")
    if settings.OPENAI_API_KEY:
        supported_stack.append("OpenAI")
    if settings.ANTHROPIC_API_KEY:
        supported_stack.append("Anthropic")

    return {
        "app": {
            "name": settings.APP_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        },
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "base_dir": settings.BASE_DIR,
            "tenderai_dir": settings.TENDERAI_DIR,
        },
        "counts": {
            "agents_registered": registry.count,
            "agents_expected": registry.count,
        },
        "backend": {
            "database_url": _sanitize_database_url(settings.DATABASE_URL),
            "ollama_base_url": settings.OLLAMA_BASE_URL,
            "openclaw_base_url": settings.OPENCLAW_BASE_URL,
        },
        "frontend": {
            "url": settings.FRONTEND_URL,
        },
        "supported_stack": supported_stack,
        "source_of_truth": {
            "agent_registry": "backend/app/main.py::register_all_agents",
            "runtime_config": "backend/app/core/config.py",
        },
    }
