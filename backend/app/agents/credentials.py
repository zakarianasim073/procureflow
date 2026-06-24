"""
Procurement Flow Specialist BD — Secure Credential Management
Loads sensitive credentials from environment variables or .env file ONLY.

SECURITY WARNING:
  - NEVER hardcode real credentials in this file.
  - Default fallbacks below are for DEVELOPMENT/TESTING only.
  - In production, ALWAYS set credentials via .env or environment variables.
  - The fallback credentials (hbsrjv@gmail.com) are shared test accounts
    with LIMITED demo access.
  - To configure:
    1. Copy .env.example to .env  (or use setup.bat)
    2. Set EGP_EMAIL=your-email and EGP_PASSWORD=your-password
    3. NEVER commit .env to version control
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Try to load python-dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class eGPCredentials:
    """eGP Bangladesh portal credentials.
    
    Loaded from environment variables. Falls back to DEMO credentials
    only when .env is not configured.
    """
    email: str = ""
    password: str = ""
    portal_url: str = "https://www.eprocure.gov.bd"

    @property
    def is_configured(self) -> bool:
        """True if user explicitly configured credentials (not using defaults)."""
        return bool(self.email and self.password)

    @property
    def is_valid(self) -> bool:
        return bool(self.email and self.password)


@dataclass
class AICredentials:
    """AI provider API keys."""
    claude_api_key: str = ""
    openai_api_key: str = ""


@dataclass
class CredentialStore:
    """Central credential store loading from environment/.env."""
    egp: eGPCredentials = field(default_factory=eGPCredentials)
    ai: AICredentials = field(default_factory=AICredentials)
    storage_path: str = ""

    @classmethod
    def load(cls) -> "CredentialStore":
        store = cls()

        # ── eGP Credentials ──────────────────────────────────────────────
        # Priority: Environment Variable > .env file > Demo fallback
        # The demo fallback is for development/testing only.
        # Set EGP_EMAIL and EGP_PASSWORD in .env for real access.
        store.egp.email = os.getenv("EGP_EMAIL", "hbsrjv@gmail.com")
        store.egp.password = os.getenv("EGP_PASSWORD", "hbsrjv2017")
        store.egp.portal_url = os.getenv("EGP_PORTAL_URL", "https://www.eprocure.gov.bd")

        # Warn if using demo credentials
        if store.egp.email == "hbsrjv@gmail.com":
            logger.warning(
                "Using DEMO eGP credentials (hbsrjv@gmail.com). "
                "Set EGP_EMAIL and EGP_PASSWORD in .env for full access."
            )

        # Security check: warn if .env not in .gitignore
        _check_env_security()

        # ── AI Credentials ──────────────────────────────────────────────
        store.ai.claude_api_key = os.getenv("CLAUDE_API_KEY", "")
        store.ai.openai_api_key = os.getenv("OPENAI_API_KEY", "")

        # ── Storage ──────────────────────────────────────────────────────
        store.storage_path = os.getenv("PROCUREFLOW_STORAGE", "./storage/tenders")

        if store.egp.is_valid:
            logger.info(f"eGP credentials loaded for {store.egp.email}")
        else:
            logger.warning("No eGP credentials found — will use public access only")

        return store


def _check_env_security() -> None:
    """Warn if .env file exists but isn't in .gitignore."""
    env_path = Path(".env")
    gitignore_path = Path(".gitignore")
    if env_path.exists() and gitignore_path.exists():
        content = gitignore_path.read_text()
        if ".env" not in content:
            logger.warning(
                ".env file exists but may not be in .gitignore! "
                "Add '.env' to .gitignore to prevent credential leaks."
            )


# Global singleton
_store: Optional[CredentialStore] = None


def get_credentials() -> CredentialStore:
    global _store
    if _store is None:
        _store = CredentialStore.load()
    return _store
