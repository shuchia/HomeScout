"""Stripe billing endpoints."""
import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
import stripe

from app.auth import get_current_user, UserContext
from app.services.tier_service import TierService

logger = logging.getLogger(__name__)

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


@router.post("/api/billing/checkout")
async def create_checkout_session(
    user: UserContext = Depends(get_current_user),
):
    """Create Stripe Checkout Session for Pro upgrade."""
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            client_reference_id=user.user_id,
            customer_email=user.email,
            success_url=f"{FRONTEND_URL}/settings?upgrade=success",
            cancel_url=f"{FRONTEND_URL}/pricing",
        )
        return {"url": session.url}
    except stripe.StripeError as e:
        logger.error(f"Stripe checkout error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.post("/api/billing/portal")
async def create_portal_session(
    user: UserContext = Depends(get_current_user),
):
    """Create Stripe Customer Portal session for billing management."""
    try:
        from app.services.tier_service import supabase_admin
        if not supabase_admin:
            raise HTTPException(status_code=500, detail="Supabase not configured")
        result = (
            supabase_admin.table("profiles")
            .select("stripe_customer_id")
            .eq("id", user.user_id)
            .single()
            .execute()
        )
        customer_id = result.data.get("stripe_customer_id") if result.data else None
        if not customer_id:
            raise HTTPException(status_code=400, detail="No active subscription found")

        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{FRONTEND_URL}/settings",
        )
        return {"url": session.url}
    except HTTPException:
        raise
    except stripe.StripeError as e:
        logger.error(f"Stripe portal error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create portal session")


@router.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events. Verifies signature."""
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(body, sig, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError) as e:
        logger.warning(f"Stripe webhook verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id")
        customer_id = data.get("customer")
        if user_id:
            await TierService.update_user_tier(
                user_id, "pro",
                stripe_customer_id=customer_id,
                subscription_status="active",
            )
            logger.info(f"User {user_id} upgraded to pro")

    elif event_type == "customer.subscription.updated":
        customer_id = data.get("customer")
        status = data.get("status")
        cancel_at = data.get("cancel_at_period_end")
        current_period_end = data.get("current_period_end")
        user_id = await _lookup_user_by_customer(customer_id)
        if user_id:
            await TierService.update_user_tier(
                user_id, "pro" if status == "active" else "free",
                subscription_status="canceled" if cancel_at else status,
                current_period_end=current_period_end,
            )

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        user_id = await _lookup_user_by_customer(customer_id)
        if user_id:
            await TierService.update_user_tier(
                user_id, "free",
                subscription_status="canceled",
            )
            logger.info(f"User {user_id} downgraded to free")

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        user_id = await _lookup_user_by_customer(customer_id)
        if user_id:
            await TierService.update_user_tier(
                user_id, "pro",  # keep pro during retry period
                subscription_status="past_due",
            )

    return {"status": "ok"}


async def _lookup_user_by_customer(customer_id: str) -> str | None:
    """Look up user_id by Stripe customer ID."""
    from app.services.tier_service import supabase_admin
    if not supabase_admin or not customer_id:
        return None
    try:
        result = (
            supabase_admin.table("profiles")
            .select("id")
            .eq("stripe_customer_id", customer_id)
            .single()
            .execute()
        )
        return result.data.get("id") if result.data else None
    except Exception as e:
        logger.error(f"Failed to look up user by customer: {e}")
        return None
