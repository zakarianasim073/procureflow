import os
import sys
import secrets
from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from dotenv import load_dotenv

# Explicitly load .env from the project root directory first
root_dir = Path(__file__).resolve().parent.parent.parent.parent
root_env = root_dir / ".env"
if root_env.exists():
    load_dotenv(dotenv_path=root_env)
else:
    load_dotenv()


def get_default_base_dir() -> str:
    override = os.environ.get("BOQ_BASE_DIR")
    if override:
        return str(Path(override).resolve())
    """Get platform-appropriate base directory"""
    if sys.platform == "win32":
        return str(Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "procurementflow-system")
    # Termux/Android: use shared storage
    sdcard = Path("/sdcard")
    if sdcard.exists():
        return str(sdcard / "tender" / ".procurementflow-system")
    return str(Path.home() / ".procurementflow-system")


def get_tenderai_dir() -> str:
    """Get tenderai output directory - user-facing reports folder (override with TENDERAI_DIR env var)"""
    override = os.environ.get("TENDERAI_DIR")
    if override:
        return str(Path(override).resolve())
    if sys.platform == "win32":
        return str(Path.home() / "Documents" / "tenderai")
    # Termux/Android: Documents/tenderai
    sdcard = Path("/sdcard")
    if sdcard.exists():
        return str(sdcard / "Documents" / "tenderai")
    return str(Path.home() / "tenderai")


class Settings(BaseSettings):
    APP_NAME: str = "Procurement Flow Specialist BD"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    ALLOWED_ORIGINS: List[str] = []

    @field_validator('ALLOWED_ORIGINS', mode='before')
    @classmethod
    def parse_allowed_origins(cls, v):
        """Parse comma-separated env var into list"""
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return []
        if isinstance(v, str):
            return [i.strip() for i in v.split(',') if i]
        return v

    JWT_SECRET: str = os.environ.get("JWT_SECRET", "").strip() or secrets.token_urlsafe(48)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    FRONTEND_URL: str = "http://localhost:5173"
    OPENCLAW_BASE_URL: str = "http://localhost:18789"
    OPENCLAW_ENABLED: bool = True
    BASE_DIR: str = ""
    TENDERAI_DIR: str = ""
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "").strip()
    SYSTEM_USER_PASSWORD: str = os.environ.get("SYSTEM_USER_PASSWORD", "").strip() or secrets.token_urlsafe(32)

    class Config:
        env_file = ".env"
        extra = "ignore"





def get_settings() -> Settings:
    s = Settings()
    if not s.BASE_DIR:
        s.BASE_DIR = get_default_base_dir()
    if not s.TENDERAI_DIR:
        s.TENDERAI_DIR = get_tenderai_dir()
    return s


settings = get_settings()
# Normalize ALLOWED_ORIGINS: if loaded as a comma‑separated string, split into a list
if isinstance(settings.ALLOWED_ORIGINS, str):
    settings.ALLOWED_ORIGINS = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(',') if origin]
