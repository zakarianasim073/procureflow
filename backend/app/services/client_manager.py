"""Client Manager — Multi-tenant client lifecycle, subscription, quota management."""
from __future__ import annotations
import logging, uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from decimal import Decimal
from app.db.database import get_sync_engine, get_sync_session
from app.db.models import Tenant, Organization, ClientSubscription, SubscriptionPlan, TenderUsageLog
logger = logging.getLogger(__name__)

class ClientManager:
    DEFAULT_PLANS = {
        "free": {"name": "Free", "monthly_limit": 5, "price": 0, "features": {"pre_screen": True}},
        "starter": {"name": "Starter", "monthly_limit": 20, "price": 5000, "features": {"pre_screen": True, "win_prob": True}},
        "professional": {"name": "Professional", "monthly_limit": 100, "price": 15000, "features": {"pre_screen": True, "win_prob": True, "bid_opt": True, "pipeline": True}},
        "enterprise": {"name": "Enterprise", "monthly_limit": 999999, "price": 50000, "features": {"pre_screen": True, "win_prob": True, "bid_opt": True, "pipeline": True, "api_access": True}},
    }

    def __init__(self):
        self._engine = get_sync_engine()

    def create_client(self, name: str, slug: str, email: str = "", phone: str = "", plan: str = "starter") -> Dict:
        session = get_sync_session()
        try:
            plan_data = self.DEFAULT_PLANS.get(plan, self.DEFAULT_PLANS["starter"])
            now = datetime.now(timezone.utc)
            tenant = session.query(Tenant).filter((Tenant.slug == slug) | (Tenant.name == name)).first()
            if tenant:
                tenant.name = name
                tenant.slug = slug
                tenant.plan = plan
                config = dict(tenant.config or {})
                config.update({"email": email, "phone": phone})
                tenant.config = config
            else:
                tenant = Tenant(name=name, slug=slug, plan=plan, config={"email": email, "phone": phone})
                session.add(tenant)
                session.flush()

            org = session.query(Organization).filter_by(tenant_id=tenant.id).first()
            if org:
                org.name = name
                org.contact_email = email
                org.contact_phone = phone
            else:
                org = Organization(tenant_id=tenant.id, name=name, contact_email=email, contact_phone=phone)
                session.add(org)

            sub = session.query(ClientSubscription).filter_by(tenant_id=tenant.id).first()
            if sub:
                sub.plan_id = self._get_or_create_plan(session, plan)
                sub.status = "active"
                sub.tender_quota_limit = plan_data["monthly_limit"]
                sub.tender_quota_used = min(sub.tender_quota_used or 0, plan_data["monthly_limit"])
                sub.billing_cycle_start = sub.billing_cycle_start or now
                sub.billing_cycle_end = sub.billing_cycle_end or (now + timedelta(days=30))
                sub.quota_reset_date = sub.quota_reset_date or (now + timedelta(days=30))
            else:
                sub = ClientSubscription(tenant_id=tenant.id, plan_id=self._get_or_create_plan(session, plan),
                    status="active", tender_quota_limit=plan_data["monthly_limit"],
                    tender_quota_used=0, billing_cycle_start=now, billing_cycle_end=now+timedelta(days=30),
                    quota_reset_date=now+timedelta(days=30))
                session.add(sub)

            session.commit()
            return {"id": tenant.id, "name": name, "slug": slug, "plan": plan, "tender_limit": plan_data["monthly_limit"]}
        except Exception as e:
            session.rollback(); return {"error": str(e)}
        finally:
            session.close()

    def get_client(self, tenant_id: str) -> Optional[Dict]:
        session = get_sync_session()
        try:
            tenant = session.query(Tenant).filter_by(id=tenant_id).first()
            if not tenant: return None
            sub = session.query(ClientSubscription).filter_by(tenant_id=tenant_id, status="active").first()
            org = session.query(Organization).filter_by(tenant_id=tenant_id).first()
            return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "plan": tenant.plan,
                "is_active": tenant.is_active, "config": tenant.config or {},
                "subscription": {"status": sub.status if sub else "none",
                    "tender_quota_used": sub.tender_quota_used if sub else 0,
                    "tender_quota_limit": sub.tender_quota_limit if sub else 0,
                    "quota_remaining": (sub.tender_quota_limit - sub.tender_quota_used) if sub else 0,
                    "billing_end": str(sub.billing_cycle_end)[:19] if sub and sub.billing_cycle_end else ""} if sub else None,
                "organization": {"name": org.name if org else tenant.name, "email": org.contact_email if org else "", "phone": org.contact_phone if org else ""} if org else None,
                "created_at": str(tenant.created_at)[:19] if tenant.created_at else ""}
        except Exception as e: logger.error(f"get_client error: {e}"); return None
        finally: session.close()

    def list_clients(self) -> List[Dict]:
        session = get_sync_session()
        try: return [self.get_client(t.id) or {"id": t.id, "name": t.name} for t in session.query(Tenant).all()]
        finally: session.close()

    def check_quota(self, tenant_id: str) -> Dict:
        session = get_sync_session()
        try:
            sub = session.query(ClientSubscription).filter_by(tenant_id=tenant_id, status="active").first()
            if not sub: return {"has_quota": False, "reason": "No active subscription", "remaining": 0}
            now = datetime.now(timezone.utc)
            if sub.quota_reset_date and now > sub.quota_reset_date:
                sub.tender_quota_used = 0; sub.quota_reset_date = now+timedelta(days=30)
                sub.billing_cycle_start = now; sub.billing_cycle_end = now+timedelta(days=30)
                session.commit()
            remaining = sub.tender_quota_limit - sub.tender_quota_used
            return {"has_quota": remaining > 0, "remaining": max(0, remaining),
                "used": sub.tender_quota_used, "limit": sub.tender_quota_limit}
        except Exception as e: return {"has_quota": False, "error": str(e)}
        finally: session.close()

    def consume_quota(self, tenant_id: str, tender_id: str, action: str = "full_pipeline") -> Dict:
        session = get_sync_session()
        try:
            sub = session.query(ClientSubscription).filter_by(tenant_id=tenant_id, status="active").first()
            if not sub: return {"consumed": False, "reason": "No active subscription"}
            if sub.tender_quota_used >= sub.tender_quota_limit: return {"consumed": False, "reason": "Quota exhausted"}
            sub.tender_quota_used += 1
            session.add(TenderUsageLog(tenant_id=tenant_id, tender_id=tender_id, action=action, quota_consumed=1))
            session.commit()
            remaining = sub.tender_quota_limit - sub.tender_quota_used
            return {"consumed": True, "remaining": max(0, remaining), "used": sub.tender_quota_used, "limit": sub.tender_quota_limit}
        except Exception as e: session.rollback(); return {"consumed": False, "error": str(e)}
        finally: session.close()

    def get_usage_history(self, tenant_id: str, days: int = 30) -> Dict:
        session = get_sync_session()
        try:
            tenant = session.query(Tenant).filter_by(id=tenant_id).first()
            if not tenant:
                return {"tenant_id": tenant_id, "days": days, "logs": [], "summary": {"total_events": 0, "total_quota_consumed": 0, "by_action": {}}}

            since = datetime.now(timezone.utc) - timedelta(days=max(1, int(days or 30)))
            logs = (
                session.query(TenderUsageLog)
                .filter(TenderUsageLog.tenant_id == tenant_id, TenderUsageLog.created_at >= since)
                .order_by(TenderUsageLog.created_at.desc())
                .all()
            )
            items = []
            by_action: Dict[str, Dict[str, Any]] = {}
            total_quota = 0
            for log in logs:
                consumed = int(log.quota_consumed or 0)
                total_quota += consumed
                action_key = log.action or "unknown"
                bucket = by_action.setdefault(action_key, {"count": 0, "quota_consumed": 0})
                bucket["count"] += 1
                bucket["quota_consumed"] += consumed
                items.append({
                    "id": log.id,
                    "tender_id": log.tender_id,
                    "action": action_key,
                    "quota_consumed": consumed,
                    "created_at": str(log.created_at)[:19] if log.created_at else "",
                })

            daily: Dict[str, int] = {}
            for item in items:
                day_key = item["created_at"][:10] if item["created_at"] else ""
                if day_key:
                    daily[day_key] = daily.get(day_key, 0) + item["quota_consumed"]

            return {
                "tenant_id": tenant_id,
                "tenant_name": tenant.name,
                "days": days,
                "logs": items,
                "summary": {
                    "total_events": len(items),
                    "total_quota_consumed": total_quota,
                    "by_action": by_action,
                    "daily": [{"date": k, "quota_consumed": v} for k, v in sorted(daily.items())],
                },
            }
        except Exception as e:
            return {"tenant_id": tenant_id, "days": days, "logs": [], "summary": {"total_events": 0, "total_quota_consumed": 0, "by_action": {}}, "error": str(e)}
        finally:
            session.close()

    def build_client_profile(self, tenant_id: str, overrides: Dict = None) -> Dict:
        client = self.get_client(tenant_id) or {}
        profile = {"tenant_id": tenant_id, "company_name": client.get("name", ""),
            "preferred_agencies": [], "preferred_zones": [], "experience_years": 5,
            "max_tender_value": 50000000, "min_tender_value": 1000000, "manpower": 10,
            "equipment": [], "risk_appetite": "moderate", "margin_target": 12.0,
            "running_projects_count": 0, "bank_limit": 0, "current_commitment": 0,
            "financial_headroom": 0, "need_for_work_score": 50, "recent_awards": [],
            "target_agencies": [], "target_zones": []}
        config = client.get("config", {}) if isinstance(client, dict) else {}
        if isinstance(config, dict): profile.update(config)
        if overrides: profile.update(overrides)
        profile["financial_headroom"] = max(0, profile.get("bank_limit", 0) - profile.get("current_commitment", 0))
        profile["need_for_work_score"] = self._compute_need_score(profile)
        return profile

    def update_client_profile(self, tenant_id: str, profile: Dict) -> Dict:
        session = get_sync_session()
        try:
            tenant = session.query(Tenant).filter_by(id=tenant_id).first()
            if not tenant: return {"error": "Client not found"}
            config = dict(tenant.config or {}); config.update(profile); tenant.config = config
            session.commit(); return {"status": "updated", "tenant_id": tenant_id}
        except Exception as e: session.rollback(); return {"error": str(e)}
        finally: session.close()

    def _compute_need_score(self, profile: Dict) -> int:
        score = 50
        running = profile.get("running_projects_count", 0)
        awards = len(profile.get("recent_awards", []))
        headroom = profile.get("financial_headroom", 0)
        if running <= 2: score += 20
        elif running >= 8: score -= 20
        if awards <= 1: score += 15
        if headroom > 50000000: score -= 10
        elif headroom <= 10000000: score += 15
        return max(0, min(100, score))

    def _get_or_create_plan(self, session, plan_key: str) -> str:
        plan_data = self.DEFAULT_PLANS.get(plan_key, self.DEFAULT_PLANS["starter"])
        existing = session.query(SubscriptionPlan).filter_by(name=plan_data["name"]).first()
        if existing: return existing.id
        plan = SubscriptionPlan(name=plan_data["name"], monthly_tender_limit=plan_data["monthly_limit"],
            monthly_price_bdt=Decimal(str(plan_data["price"])), features=plan_data["features"])
        session.add(plan); session.flush(); return plan.id

_client_manager = None
def get_client_manager() -> ClientManager:
    global _client_manager
    if _client_manager is None: _client_manager = ClientManager()
    return _client_manager
