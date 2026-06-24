"""
Procurement Flow Specialist BD — Configuration
Central configuration for the entire agent system.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AppConfig:
    # Application
    app_name: str = "Procurement Flow Specialist BD"
    version: str = "1.0.0"
    environment: str = os.getenv("PROCUREFLOW_ENV", "development")
    debug: bool = os.getenv("PROCUREFLOW_DEBUG", "true").lower() in ("true", "1", "yes")

    # Server
    host: str = os.getenv("PROCUREFLOW_HOST", "0.0.0.0")
    port: int = int(os.getenv("PROCUREFLOW_PORT", "8000"))

    # Database
    database_url: str = os.getenv("DATABASE_URL", "")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Storage
    storage_path: str = os.getenv("PROCUREFLOW_STORAGE", "./storage")
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "procureflow")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "") or __import__("secrets").token_urlsafe(32)

    # Auth
    jwt_secret: str = os.getenv("JWT_SECRET", "") or __import__("secrets").token_urlsafe(48)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # AI Providers
    claude_api_key: Optional[str] = os.getenv("CLAUDE_API_KEY")
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")

    # Agent System
    default_pipeline_mode: str = "full"  # full, phase, agents
    pipeline_stop_on_failure: bool = True
    max_concurrent_agents: int = 5

    # Company Profile (default)
    company_profile: Dict = field(default_factory=lambda: {
        "name": "Your Company Ltd",
        "years_experience": 10,
        "avg_turnover": 80_000_000,
        "engineers_count": 25,
        "deployed_engineers": 15,
        "ongoing_projects": 4,
        "equipment": ["Excavator", "Paver", "Roller", "Concrete Mixer", "Crane"],
        "equipment_availability_pct": 80,
        "licenses": ["LGED", "RHD", "PWD"],
        "agency_wins": {"LGED": 3, "RHD": 2, "PWD": 1},
        "working_capital": 15_000_000,
    })

    # SOR Data Paths
    sor_paths: Dict[str, str] = field(default_factory=lambda: {
        "bwdb": "app/sor/bwdb",
        "lged": "app/sor/lged",
        "pwd": "app/sor/pwd",
    })


config = AppConfig()
