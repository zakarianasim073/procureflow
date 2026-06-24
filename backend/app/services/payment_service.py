"""
Procurement Flow Specialist BD — Payment Service (Stripe)
Handles subscription plans, checkout sessions, webhooks, and plan upgrades.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional
from datetime import datetime

logger = logging.getLogger("procureflow.payments")

# Stripe API key (optional — service works in demo mode without it)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

stripe = None
if STRIPE_SECRET_KEY:
    try:
        import stripe as stripe_lib
        stripe_lib.api_key = STRIPE_SECRET_KEY
        stripe = stripe_lib
        logger.info("Stripe initialized")
    except ImportError:
        logger.warning("stripe package not installed — payments in demo mode")


PLANS = {
    "free": {
        "name": "Free",
        "price_bdt": 0,
        "price_usd": 0,
        "stripe_price_id": None,
        "features": ["5 Tender Analyses / month", "Basic SOR Comparison", "PDF Export"],
        "quota_limit": 5,
    },
    "pro": {
        "name": "Professional",
        "price_bdt": 15_000,
        "price_usd": 125,
        "stripe_price_id": os.getenv("STRIPE_PRICE_PRO", "price_pro"),
        "features": [
            "Unlimited Tender Analyses",
            "PPR 2025 SLT/LERT Engine",
            "eGP Radar & Alerts",
            "Competitor Intelligence",
            "Priority AI Processing",
        ],
        "quota_limit": 999999,
    },
    "enterprise": {
        "name": "Enterprise",
        "price_bdt": 45_000,
        "price_usd": 375,
        "stripe_price_id": os.getenv("STRIPE_PRICE_ENTERPRISE", "price_enterprise"),
        "features": [
            "Everything in Pro",
            "5 User Seats",
            "Custom SOR Database",
            "API Access",
            "Dedicated Account Manager",
        ],
        "quota_limit": 999999,
    },
}


class PaymentService:
    """Handles Stripe subscription management."""

    def get_plans(self) -> list:
        """Return available subscription plans."""
        return [self._format_plan(key, p) for key, p in PLANS.items()]

    def get_plan(self, plan_name: str) -> Optional[Dict]:
        """Get a specific plan by name."""
        plan = PLANS.get(plan_name)
        if plan:
            return self._format_plan(plan_name, plan)
        return None

    def _format_plan(self, key: str, plan: Dict) -> Dict:
        return {
            "name": plan["name"],
            "price": f"৳{plan['price_bdt']:,}",
            "price_usd": plan["price_usd"],
            "price_bdt": plan["price_bdt"],
            "period": "/month",
            "description": plan.get("description", ""),
            "features": plan["features"],
            "plan_name": key,
            "popular": key == "pro",
            "stripe_price_id": plan["stripe_price_id"],
        }

    async def create_checkout_session(self, price_id: str, plan_name: str,
                                        user_id: str, user_email: str,
                                        success_url: str = None,
                                        cancel_url: str = None) -> Dict[str, Any]:
        """
        Create a Stripe Checkout Session.
        Falls back to demo mode if Stripe is not configured.
        """
        if not stripe or not STRIPE_SECRET_KEY:
            logger.info(f"Demo mode: checkout for {plan_name} / user {user_id}")
            return {
                "success": True,
                "session_url": f"/settings?plan={plan_name}",
                "session_id": f"demo_{user_id}",
                "mode": "demo",
            }

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                customer_email=user_email,
                client_reference_id=user_id,
                metadata={"plan_name": plan_name},
                success_url=success_url or f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/settings?success=true",
                cancel_url=cancel_url or f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/pricing?canceled=true",
            )
            return {
                "success": True,
                "session_url": session.url,
                "session_id": session.id,
                "mode": "live",
            }
        except Exception as e:
            logger.error(f"Stripe session creation failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    async def handle_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """
        Handle Stripe webhook events.
        Processes: checkout.session.completed, invoice.paid, customer.subscription.updated
        """
        if not stripe or not STRIPE_WEBHOOK_SECRET:
            return {"status": "ignored", "mode": "demo"}

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            logger.error(f"Webhook signature verification failed: {e}")
            return {"status": "error", "error": str(e)}

        event_type = event.get("type", "")
        data = event.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            user_id = data.get("client_reference_id", "")
            plan_name = data.get("metadata", {}).get("plan_name", "free")
            subscription_id = data.get("subscription", "")
            logger.info(f"Checkout completed: user={user_id} plan={plan_name} sub={subscription_id}")
            # Upgrade user's plan in database
            await self._upgrade_user_plan(user_id, plan_name, subscription_id)

        elif event_type == "invoice.paid":
            logger.info(f"Invoice paid: {data.get('id', '')}")

        elif event_type == "customer.subscription.updated":
            logger.info(f"Subscription updated: {data.get('id', '')}")

        return {"status": "processed", "event": event_type}

    async def _upgrade_user_plan(self, user_id: str, plan_name: str,
                                   subscription_id: str = "") -> None:
        """Upgrade user's plan in the database after successful payment."""
        from app.db.base import get_session_factory
        from app.models.user import User, UserPlan
        from sqlalchemy import select

        if plan_name not in ("pro", "enterprise"):
            return

        new_plan = UserPlan.PRO if plan_name == "pro" else UserPlan.ENTERPRISE

        factory = get_session_factory()
        async with factory() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                user.plan = new_plan
                if plan_name == "pro":
                    user.gpt_quota_limit = 500000
                else:
                    user.gpt_quota_limit = 9999999
                logger.info(f"Upgraded user {user_id} to {plan_name}")
                await session.commit()


payment_service = PaymentService()
