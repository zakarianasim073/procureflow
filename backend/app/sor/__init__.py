"""
Procurement Flow Specialist BD — Schedule of Rates (SOR) Module
Agency-wise, zone-based unit rates (4 zones: A/B/C/D) for BOQ pricing.

Agencies:
  - BWDB: Bangladesh Water Development Board (931 items)
  - LGED: Local Government Engineering Department (parsing in progress)
  - PWD: Public Works Department (parsing in progress)
"""
from .bwdb import get_rate as bwdb_get_rate, get_rate_info, get_all_rates, search as bwdb_search, SOR_RATES as BWDB_RATES

# Combined lookup: try BWDB first, then LGED, then PWD
AGENCY_RATES = {"BWDB": BWDB_RATES}

def get_rate(code: str, zone: str = "A", agency: str = "BWDB") -> float | None:
    """Get SOR rate for a code, zone, and agency."""
    if agency.upper() == "BWDB":
        return bwdb_get_rate(code, zone)
    return None

def search(query: str, agency: str = "BWDB", max_results: int = 10):
    """Search SOR items."""
    if agency.upper() == "BWDB":
        return bwdb_search(query, max_results)
    return []

def list_agencies():
    """List all available agencies with item counts."""
    return [{"agency": "BWDB", "items": len(BWDB_RATES), "zones": 4},
            {"agency": "LGED", "items": 0, "zones": 4},
            {"agency": "PWD", "items": 0, "zones": 4}]
