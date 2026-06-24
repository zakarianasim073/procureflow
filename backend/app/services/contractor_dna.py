"""
Contractor DNA Service - Profile building from awards and pre-computed data.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Path to pre-computed contractor DNA profiles
DNA_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(__file__))), "imports", "runtime", "knowledge", "contractor_dna")
BACKUP_DIRS = [
    "imports/runtime/knowledge/contractor_dna",
    "imports/runtime/runtime/knowledge/contractor_dna",
]


def _find_dna_dir() -> str:
    """Find the contractor_dna data directory."""
    for d in [DNA_DATA_DIR] + BACKUP_DIRS:
        if os.path.isdir(d):
            return d
    return ""


def _load_all_profiles() -> Dict[str, Dict]:
    """Load all pre-computed contractor DNA profiles."""
    dna_dir = _find_dna_dir()
    if not dna_dir:
        logger.warning("Contractor DNA data directory not found")
        return {}
    
    profiles = {}
    for fn in os.listdir(dna_dir):
        if fn.endswith(".json"):
            try:
                path = os.path.join(dna_dir, fn)
                with open(path) as f:
                    profile = json.load(f)
                name = profile.get("contractor_name", fn.replace(".json", ""))
                profiles[name.lower()] = profile
            except Exception as e:
                logger.debug(f"Failed to load {fn}: {e}")
    
    logger.info(f"Loaded {len(profiles)} contractor DNA profiles")
    return profiles


# Cache loaded profiles
_profiles_cache: Optional[Dict[str, Dict]] = None


def get_contractor_dna(name: str) -> Optional[Dict]:
    """Get DNA profile for a specific contractor."""
    global _profiles_cache
    if _profiles_cache is None:
        _profiles_cache = _load_all_profiles()
    return _profiles_cache.get(name.lower())


class ContractorDNA:
    """Build and query contractor DNA profiles."""

    def __init__(self):
        self._profiles: Dict[str, Dict] = {}

    def build_all_profiles(self, awards: List[Dict] = None) -> Dict:
        """
        Build contractor profiles from awards data.
        Falls back to pre-computed profiles if available.
        """
        global _profiles_cache
        if _profiles_cache is None:
            _profiles_cache = _load_all_profiles()
        
        if _profiles_cache:
            return {
                "total_contractors": len(_profiles_cache),
                "total_awards_analyzed": sum(
                    p.get("total_wins", 0) for p in _profiles_cache.values()
                ),
                "source": "pre_computed",
            }
        
        # If no pre-computed data, build from awards
        if not awards:
            return {"total_contractors": 0, "total_awards_analyzed": 0, "source": "empty"}
        
        profiles = {}
        for a in awards:
            winner = str(a.get("winner", a.get("contractor", "Unknown"))).lower()
            if winner not in profiles:
                profiles[winner] = {
                    "contractor_name": winner,
                    "total_wins": 0,
                    "total_amount_bdt": 0.0,
                    "agencies": {},
                }
            profiles[winner]["total_wins"] += 1
            amt = float(a.get("amount_bdt", a.get("award_amount", 0)) or 0)
            profiles[winner]["total_amount_bdt"] += amt
            agency = a.get("agency_target", a.get("procuring_entity", "Unknown"))
            if agency not in profiles[winner]["agencies"]:
                profiles[winner]["agencies"][agency] = {"wins": 0, "total_amount": 0.0}
            profiles[winner]["agencies"][agency]["wins"] += 1
            profiles[winner]["agencies"][agency]["total_amount"] += amt
        
        _profiles_cache = profiles
        return {
            "total_contractors": len(profiles),
            "total_awards_analyzed": len(awards),
            "source": "from_awards",
        }

    def get_profile(self, name: str) -> Optional[Dict]:
        return get_contractor_dna(name)


# Singleton
contractor_dna = ContractorDNA()
