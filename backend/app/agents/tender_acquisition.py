"""
Compatibility wrapper for the tender acquisition agent.

The live registry in this codebase imports `app.agents.tender_acquisition`
directly in some places and `app.agents.discovery.tender_acquisition` in others.
Keep both entry points on the same implementation.
"""
from __future__ import annotations

from .discovery.tender_acquisition import TenderAcquisitionAgent

__all__ = ["TenderAcquisitionAgent"]
