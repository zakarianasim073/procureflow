"""
Knowledge Graph Builder — Creates relationships between data entities.
Connects tenders → awards → contractors → agencies → patterns.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import text

from app.db.database import get_sync_engine

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """
    Builds a procurement knowledge graph from the database.
    
    Relationships tracked:
      - Contractor → Tenders they bid on
      - Contractor → Awards they won
      - Agency → Tenders they publish
      - Agency → Contractors they award to
      - Tender → Opening Report → Bidders
      - Tender → Award → Contractor
      - Pattern: Same bidders across multiple tenders (syndicate detection)
      - Pattern: Contractor win rates by agency/zone
    
    The graph is stored as structured data in the database,
    queryable by all agents.
    """
    
    def __init__(self):
        self._engine = get_sync_engine()

    @staticmethod
    def _normalize_query(value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return ""
        raw = raw.replace("\\", "/")
        raw = " ".join(raw.split())
        return raw

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        return dict(row._mapping) if row is not None else {}

    def _first(self, conn, sql: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        row = conn.execute(text(sql), params).mappings().first()
        return dict(row) if row else None

    def get_contractor_dna(self, contractor_name: str) -> Dict:
        """Build a contractor's DNA profile from all available data sources."""
        query = self._normalize_query(contractor_name)
        like = f"%{query}%"
        with self._engine.connect() as conn:
            contractor = self._first(
                conn,
                """
                SELECT
                    c.id AS contractor_id,
                    c.contractor_name,
                    c.total_contracts,
                    c.total_amount_bdt,
                    c.agencies_worked,
                    c.districts_worked,
                    c.avg_npp,
                    c.first_award_date,
                    c.last_award_date,
                    cd.total_contracts AS dna_total_contracts,
                    cd.total_amount_bdt AS dna_total_amount_bdt,
                    cd.avg_award_bdt,
                    cd.agencies_worked AS dna_agencies_worked,
                    cd.districts_worked AS dna_districts_worked,
                    cd.preferred_agency,
                    cd.preferred_zone,
                    cd.avg_npp AS dna_avg_npp,
                    cd.npp_volatility,
                    cd.win_rate,
                    cd.avg_discount_pct,
                    cd.completion_rate,
                    cd.on_time_rate,
                    cd.avg_delay_days,
                    cd.total_experience_contracts,
                    cd.total_experience_value_bdt,
                    cd.health_score
                FROM contractors c
                LEFT JOIN contractor_dna cd ON cd.contractor_id = c.id
                WHERE c.contractor_name ILIKE :like OR c.id = :query
                ORDER BY c.total_amount_bdt DESC NULLS LAST, c.contractor_name ASC
                LIMIT 1
                """,
                {"query": query, "like": like},
            )
            if not contractor and query.upper().startswith("M/S "):
                stripped = query[4:].strip()
                contractor = self._first(
                    conn,
                    """
                    SELECT
                        c.id AS contractor_id,
                        c.contractor_name,
                        c.total_contracts,
                        c.total_amount_bdt,
                        c.agencies_worked,
                        c.districts_worked,
                        c.avg_npp,
                        c.first_award_date,
                        c.last_award_date,
                        cd.total_contracts AS dna_total_contracts,
                        cd.total_amount_bdt AS dna_total_amount_bdt,
                        cd.avg_award_bdt,
                        cd.agencies_worked AS dna_agencies_worked,
                        cd.districts_worked AS dna_districts_worked,
                        cd.preferred_agency,
                        cd.preferred_zone,
                        cd.avg_npp AS dna_avg_npp,
                        cd.npp_volatility,
                        cd.win_rate,
                        cd.avg_discount_pct,
                        cd.completion_rate,
                        cd.on_time_rate,
                        cd.avg_delay_days,
                        cd.total_experience_contracts,
                        cd.total_experience_value_bdt,
                        cd.health_score
                    FROM contractors c
                    LEFT JOIN contractor_dna cd ON cd.contractor_id = c.id
                    WHERE c.contractor_name ILIKE :like
                    ORDER BY c.total_amount_bdt DESC NULLS LAST, c.contractor_name ASC
                    LIMIT 1
                    """,
                    {"like": f"%{stripped}%"},
                )

            recent_awards = conn.execute(
                text(
                    """
                    SELECT
                        COALESCE(source_tender_id, package_no, procurement_tender_id::text, '') AS tender_ref,
                        COALESCE(agency_code, '') AS agency_code,
                        COALESCE(contractor_name, '') AS contractor_name,
                        COALESCE(amount_bdt, 0) AS amount_bdt,
                        award_date
                    FROM award_records_v2
                    WHERE contractor_name ILIKE :like
                    ORDER BY created_at DESC
                    LIMIT 10
                    """
                ),
                {"like": like},
            ).mappings().all()

            lifecycle_summary = self._first(
                conn,
                """
                SELECT
                    COUNT(*) AS lifecycle_rows,
                    COUNT(*) FILTER (WHERE match_type = 'package_exact') AS exact_matches,
                    COUNT(*) FILTER (WHERE data_source = 'matched') AS matched_rows,
                    COALESCE(SUM(award_amount_bdt), 0) AS total_award_value,
                    COALESCE(AVG(npp_ratio), 0) AS avg_npp
                FROM procurement_lifecycle
                WHERE winner ILIKE :like
                """,
                {"like": like},
            ) or {"lifecycle_rows": 0, "exact_matches": 0, "matched_rows": 0, "total_award_value": 0, "avg_npp": 0}

        contractor_name_value = contractor.get("contractor_name") if contractor else contractor_name
        agencies = contractor.get("agencies_worked") if contractor and contractor.get("agencies_worked") else []
        districts = contractor.get("districts_worked") if contractor and contractor.get("districts_worked") else []
        if contractor and contractor.get("dna_agencies_worked") and not agencies:
            agencies = contractor.get("dna_agencies_worked") or []
        if contractor and contractor.get("dna_districts_worked") and not districts:
            districts = contractor.get("dna_districts_worked") or []

        return {
            "contractor": contractor_name_value,
            "contractor_id": contractor.get("contractor_id") if contractor else None,
            "total_awards": int(contractor.get("total_contracts") or contractor.get("dna_total_contracts") or 0) if contractor else len(recent_awards),
            "total_value": float(contractor.get("total_amount_bdt") or contractor.get("dna_total_amount_bdt") or 0) if contractor else float(sum(float(row["amount_bdt"] or 0) for row in recent_awards)),
            "avg_award_bdt": float(contractor.get("avg_award_bdt") or 0) if contractor else 0,
            "agencies": [a for a in agencies if a],
            "districts": [d for d in districts if d],
            "preferred_agency": contractor.get("preferred_agency") if contractor else None,
            "preferred_zone": contractor.get("preferred_zone") if contractor else None,
            "win_rate": float(contractor.get("win_rate") or 0) if contractor else 0,
            "health_score": float(contractor.get("health_score") or 0) if contractor else 0,
            "completion_rate": float(contractor.get("completion_rate") or 0) if contractor else 0,
            "on_time_rate": float(contractor.get("on_time_rate") or 0) if contractor else 0,
            "avg_delay_days": float(contractor.get("avg_delay_days") or 0) if contractor else 0,
            "recent_awards": [
                {
                    "tender_id": row["tender_ref"],
                    "agency": row["agency_code"],
                    "contractor_name": row["contractor_name"],
                    "amount": float(row["amount_bdt"] or 0),
                    "award_date": row["award_date"],
                }
                for row in recent_awards
            ],
            "lifecycle_summary": lifecycle_summary,
        }
    
    def get_agency_intelligence(self, agency_name: str) -> Dict:
        """Build agency behavior profile."""
        with self._engine.connect() as conn:
            # Total tenders
            tenders = conn.execute(text(
                "SELECT COUNT(*), COALESCE(SUM(estimated_cost), 0) FROM tenders WHERE COALESCE(sor_agency, procuring_entity, '') = :name"
            ), {"name": agency_name}).fetchone()
            
            # Top contractors directly from awards (agency now populated from raw_data)
            top = conn.execute(text(
                "SELECT contractor_name, COUNT(*) as cnt, SUM(amount_bdt) as total "
                "FROM awards WHERE agency = :name "
                "AND contractor_name IS NOT NULL AND contractor_name != '' "
                "AND amount_bdt IS NOT NULL AND amount_bdt > 0 "
                "GROUP BY contractor_name ORDER BY cnt DESC LIMIT 10"
            ), {"name": agency_name}).fetchall()
            
            # Average discount (using tenders directly)
            avg_discount = conn.execute(text(
                "SELECT AVG(estimated_cost - :zero) FROM tenders "
                "WHERE COALESCE(sor_agency, procuring_entity, '') = :name AND estimated_cost > 0 LIMIT 1"
            ), {"name": agency_name, "zero": 0}).fetchone()
        
        return {
            "agency": agency_name,
            "total_tenders": tenders[0] if tenders else 0,
            "total_value": float(tenders[1]) if tenders and tenders[1] else 0,
            "top_contractors": [
                {"name": c[0], "awards": c[1], "total_value": float(c[2]) if c[2] else 0}
                for c in top if c[0]
            ],
            "avg_discount": float(avg_discount[0]) if avg_discount and avg_discount[0] else 0,
        }
    
    def find_syndicate_patterns(self) -> List[Dict]:
        """Find patterns where same bidders appear together repeatedly."""
        # This uses opening_reports bidder data
        # Simplified: find tenders with 3+ same bidders
        patterns = []
        with self._engine.connect() as conn:
            # Check for repeated bidder combinations
            result = conn.execute(text(
                "SELECT tender_id, bidders FROM opening_reports WHERE bidders IS NOT NULL LIMIT 100"
            )).fetchall()
        
        # Simple analysis: look for overlapping bidder sets
        bidder_sets = {}
        for r in result:
            bidders = r[1]
            if isinstance(bidders, list):
                key = frozenset([b.get("name", "") for b in bidders if isinstance(b, dict)])
                if key and len(key) >= 3:
                    if key not in bidder_sets:
                        bidder_sets[key] = []
                    bidder_sets[key].append(r[0])
        
        for bidders, tenders in bidder_sets.items():
            if len(tenders) >= 3:
                patterns.append({
                    "bidders": list(bidders),
                    "shared_tenders": tenders,
                    "frequency": len(tenders),
                    "pattern_type": "repeat_collaboration" if len(bidders) >= 4 else "frequent_competition",
                })
        
        return patterns
    
    def get_tender_lifecycle(self, tender_id: str) -> Dict:
        """Get the full lifecycle of a tender from APP → live notice → award."""
        query = self._normalize_query(tender_id)
        like = f"%{query}%"
        lifecycle = {"tender_id": tender_id, "stages": []}

        with self._engine.connect() as conn:
            lifecycle_row = self._first(
                conn,
                """
                SELECT *
                FROM procurement_lifecycle
                WHERE package_no = :query
                   OR tender_id = :query
                   OR package_no ILIKE :like
                   OR tender_id ILIKE :like
                ORDER BY award_date DESC NULLS LAST, created_at DESC
                LIMIT 1
                """,
                {"query": query, "like": like},
            )
            if lifecycle_row:
                lifecycle["stages"].append({"stage": "lifecycle", "data": lifecycle_row})

            tender_row = self._first(
                conn,
                """
                SELECT *
                FROM procurement_tenders
                WHERE id = :query
                   OR package_no = :query
                   OR package_no ILIKE :like
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"query": query, "like": like},
            )
            tender_id_value = tender_row.get("id") if tender_row else None
            package_no = tender_row.get("package_no") if tender_row else (lifecycle_row.get("package_no") if lifecycle_row else query)
            if tender_row:
                lifecycle["stages"].append({"stage": "tender", "data": tender_row})

            app_row = self._first(
                conn,
                """
                SELECT *
                FROM app_records
                WHERE procurement_tender_id = :tender_id
                   OR source_tender_id = :package_no
                   OR source_tender_id = :query
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"tender_id": tender_id_value, "package_no": package_no, "query": query},
            )
            if app_row:
                lifecycle["stages"].append({"stage": "app", "data": app_row})

            live_row = self._first(
                conn,
                """
                SELECT *
                FROM live_tender_sources
                WHERE procurement_tender_id = :tender_id
                   OR source_tender_id = :package_no
                   OR source_tender_id = :query
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"tender_id": tender_id_value, "package_no": package_no, "query": query},
            )
            if live_row:
                lifecycle["stages"].append({"stage": "live", "data": live_row})

            opening_row = self._first(
                conn,
                """
                SELECT *
                FROM opening_reports
                WHERE tender_id = :query
                   OR tender_id = :package_no
                   OR tender_id = :tender_id
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"query": query, "package_no": package_no, "tender_id": tender_id_value},
            )
            if opening_row:
                lifecycle["stages"].append({"stage": "opening", "data": opening_row})

            award_row = self._first(
                conn,
                """
                SELECT *
                FROM award_records_v2
                WHERE procurement_tender_id = :tender_id
                   OR source_tender_id = :package_no
                   OR package_no = :package_no
                   OR source_tender_id = :query
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"tender_id": tender_id_value, "package_no": package_no, "query": query},
            )
            if award_row:
                lifecycle["stages"].append({"stage": "award", "data": award_row})

        lifecycle["summary"] = {
            "stage_count": len(lifecycle["stages"]),
            "has_app": any(stage["stage"] == "app" for stage in lifecycle["stages"]),
            "has_live": any(stage["stage"] == "live" for stage in lifecycle["stages"]),
            "has_opening": any(stage["stage"] == "opening" for stage in lifecycle["stages"]),
            "has_award": any(stage["stage"] == "award" for stage in lifecycle["stages"]),
            "has_lifecycle": any(stage["stage"] == "lifecycle" for stage in lifecycle["stages"]),
        }
        return lifecycle
