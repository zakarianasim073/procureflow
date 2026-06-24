"""SOR Zone Matcher Agent - Ensures correct zone selection per agency + location."""
from __future__ import annotations
import logging
import re
from typing import Any, Dict, Optional
from app.agents.core.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

# ── Agency Zone Definitions ────────────────────────────────────────────
# Based on actual SOR documents from LGED, BWDB, PWD

DISTRICT_ZONES = {
    "BWDB": {
        "A": ["dhaka", "mymensingh", "sylhet", "chattogram", "comilla", "brahmanbaria",
              "kishoreganj", "netrokona", "sherpur", "jamalpur", "narsingdi", "gazipur",
              "narayanganj", "munshiganj", "manikganj", "tangail", "habiganj", "moulvibazar",
              "sunamganj", "chandpur", "noakhali", "lakshmipur", "feni", "khagrachari",
              "rangamati", "bandarban", "coxsbazar"],
        "B": ["khulna", "barishal", "bagerhat", "sathkhira", "jessore", "narail", "magura",
              "jhenaidah", "kushtia", "chudanga", "meherpur", "patuakhali", "bhola",
              "barguna", "jhalokati", "pirojpur", "gopalganj", "madaripur", "shariatpur",
              "faridpur", "rajbari"],
        "C": ["rajshahi", "nawabganj", "natore", "pabna", "sirajganj", "bogra", "naogaon",
              "joypurhat", "dinajpur", "thakurgaon", "panchagarh", "rangpur",
              "kurigram", "gaibandha", "lalmonirhat", "nilphamari"],
        "D": [],  # Not used/other zones
    },
    "LGED": {
        "A": ["dhaka", "mymensingh", "gazipur", "narayanganj", "tangail", "kishoreganj",
              "netrokona", "sherpur", "jamalpur", "narsingdi", "munshiganj", "manikganj"],
        "B": ["chattogram", "sylhet", "coxsbazar", "brahmanbaria", "comilla", "chandpur",
              "lakshmipur", "noakhali", "feni", "khagrachari", "rangamati", "bandarban",
              "habiganj", "moulvibazar", "sunamganj"],
        "C": ["rajshahi", "rangpur", "dinajpur", "thakurgaon", "panchagarh", "nilphamari",
              "lalmonirhat", "kurigram", "gaibandha", "joypurhat", "naogaon", "nawabganj",
              "natore", "pabna", "sirajganj", "bogra"],
        "D": ["khulna", "barishal", "bagerhat", "sathkhira", "jessore", "magura", "narail",
              "jhenaidah", "kushtia", "chudanga", "meherpur", "patuakhali", "bhola",
              "barguna", "jhalokati", "pirojpur", "gopalganj", "madaripur", "shariatpur",
              "faridpur", "rajbari"],
    },
    "PWD": {
        "A": ["dhaka", "mymensingh", "gazipur", "narayanganj", "tangail", "narsingdi",
              "munshiganj", "manikganj", "madaripur", "shariatpur", "faridpur", "rajbari",
              "gopalganj", "kishoreganj", "netrokona", "jamalpur", "sherpur"],
        "B": ["chattogram", "sylhet", "comilla", "brahmanbaria", "chandpur", "lakshmipur",
              "feni", "noakhali", "habiganj", "moulvibazar", "sunamganj",
              "khagrachari", "rangamati", "bandarban", "coxsbazar"],
        "C": ["khulna", "barishal", "bagerhat", "sathkhira", "jessore", "magura", "narail",
              "jhenaidah", "kushtia", "chudanga", "meherpur", "patuakhali", "bhola",
              "barguna", "jhalokati", "pirojpur"],
        "D": ["rajshahi", "rangpur", "dinajpur", "thakurgaon", "panchagarh", "nilphamari",
              "lalmonirhat", "kurigram", "gaibandha", "joypurhat", "naogaon", "nawabganj",
              "natore", "pabna", "sirajganj", "bogra"],
    },
}

ZONE_LABELS = {
    "BWDB": {
        "A": "Zone-A: Dhaka, Mymensingh, Sylhet, Chattogram",
        "B": "Zone-B: Khulna, Barisal",
        "C": "Zone-C: Rajshahi, Rangpur",
        "D": "Zone-D: Rest of districts",
    },
    "LGED": {
        "A": "Zone-A: Dhaka, Mymensingh Division",
        "B": "Zone-B: Chattogram, Sylhet Division",
        "C": "Zone-C: Rajshahi, Rangpur Division",
        "D": "Zone-D: Khulna, Barishal Division",
    },
    "PWD": {
        "A": "Zone-A: Dhaka, Mymensingh",
        "B": "Zone-B: Chattogram, Sylhet",
        "C": "Zone-C: Khulna, Barishal",
        "D": "Zone-D: Rajshahi, Rangpur",
    },
}


class SORZoneMatcherAgent(BaseAgent):
    agent_id = "agent-044-sor-zone-matcher"
    agent_name = "SOR Zone Matcher"
    description = "Maps districts to correct SOR zones per agency (LGED/BWDB/PWD)"
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "lookup")
        if action == "lookup":
            result = self.lookup_rate(context)
        elif action == "validate":
            result = self.validate_zone(context)
        elif action == "agency_zones":
            result = self.get_agency_zones(context.get("agency", ""))
        else:
            result = {"error": f"Unknown action: {action}"}
        return AgentResult(status=AgentStatus.SUCCESS, output=result)

    def _resolve(self, agency: str, location: str) -> Optional[str]:
        """Resolve zone for a given agency and district/division location."""
        if not location or agency not in DISTRICT_ZONES:
            return None
        loc = location.lower().replace(" ", "").replace("'", "").replace("-", "").replace(".", "")
        for zone, districts in DISTRICT_ZONES[agency].items():
            for d in districts:
                if loc == d:
                    return zone
            # Partial match for longer strings
            for d in districts:
                if len(loc) > 4 and (loc in d or d in loc):
                    return zone
        return None

    def _detect_agency(self, item_code: str) -> Optional[str]:
        code = str(item_code or "").strip().upper()
        if "(BWDB)" in code:
            return "BWDB"
        if "(LGED)" in code:
            return "LGED"
        if "(PWD)" in code or code.startswith("PWD ") or code.startswith("EM"):
            return "PWD"
        if "-" in code and "." not in code:
            return "BWDB" if len(code.split("-")) >= 2 else None
        if code.startswith(tuple(str(i) + "." for i in range(2, 10))):
            return "LGED"
        if re.match(r"^\d{2}\.\d", code):
            return "PWD"
        return None

    def lookup_rate(self, ctx: Dict) -> Dict:
        agency = str(ctx.get("agency", "") or "").upper()
        location = (ctx.get("district") or ctx.get("division") or ctx.get("location") or "").strip()
        item_code = ctx.get("item_code", "")
        if agency not in DISTRICT_ZONES:
            agency = self._detect_agency(item_code) or "BWDB"

        if agency not in DISTRICT_ZONES:
            return {"found": False, "error": f"Unknown agency: {agency}. Supported: {', '.join(DISTRICT_ZONES.keys())}"}
        
        zone = self._resolve(agency, location)
        if not zone:
            return {"found": False, "error": f"Cannot determine zone for {agency} at '{location}'"}
        
        rate = self._get_rate(agency, item_code, zone)
        r = {
            "found": bool(rate),
            "agency": agency,
            "location": location,
            "zone": zone,
            "zone_label": ZONE_LABELS.get(agency, {}).get(zone, f"Zone-{zone}"),
            "item_code": item_code,
        }
        if rate:
            r["sor_rate"] = float(rate)
            r["all_zones"] = self._get_all_rates(agency, item_code)
        return r

    def validate_zone(self, ctx: Dict) -> Dict:
        agency = ctx.get("agency", "").upper()
        location = (ctx.get("district") or ctx.get("division") or "").strip()
        proposed = ctx.get("zone", "").upper()
        actual = self._resolve(agency, location)
        if not actual:
            return {"valid": False, "error": f"Cannot resolve zone for {agency} at '{location}'"}
        return {
            "valid": actual == proposed,
            "agency": agency,
            "location": location,
            "proposed_zone": proposed,
            "correct_zone": actual,
            "zone_label": ZONE_LABELS.get(agency, {}).get(actual, f"Zone-{actual}"),
        }

    def get_agency_zones(self, agency: str) -> Dict:
        agency = agency.upper()
        if agency not in DISTRICT_ZONES:
            return {"error": f"Unknown agency: {agency}. Supported: {', '.join(DISTRICT_ZONES.keys())}"}
        zones = DISTRICT_ZONES[agency]
        return {
            "agency": agency,
            "zone_count": len(zones),
            "zones": {
                z: {
                    "districts": districts,
                    "count": len(districts),
                    "label": ZONE_LABELS.get(agency, {}).get(z, f"Zone-{z}"),
                }
                for z, districts in zones.items()
            },
        }

    def _get_rate(self, agency: str, item_code: str, zone: str) -> Optional[float]:
        try:
            from app.db.database import get_sync_session
            from app.db.models import RateAnalysis
            session = get_sync_session()
            r = session.query(RateAnalysis).filter(
                RateAnalysis.agency == agency,
                RateAnalysis.item_code == item_code,
                RateAnalysis.zone.in_([zone, f"Zone-{zone}"]),
            ).first()
            session.close()
            return float(r.sor_rate) if r and r.sor_rate else None
        except Exception as e:
            logger.warning(f"Rate lookup error for {agency} {item_code} Z{zone}: {e}")
            return None

    def _get_all_rates(self, agency: str, item_code: str) -> Dict:
        """Get rates for all zones for the same item."""
        rates = {}
        try:
            from app.db.database import get_sync_session
            from app.db.models import RateAnalysis
            session = get_sync_session()
            results = session.query(RateAnalysis).filter_by(agency=agency, item_code=item_code).all()
            for r in results:
                zone_letter = str(r.zone or "").replace("Zone-", "")
                rates[zone_letter] = float(r.sor_rate) if r.sor_rate else 0
            session.close()
        except Exception as e:
            logger.warning(f"All rates lookup error: {e}")
        return rates
