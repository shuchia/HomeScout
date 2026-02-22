"""Tests for Stripe billing router."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from app.auth import get_current_user, UserContext
from app.main import app

client = TestClient(app)


def _mock_user():
    """Return a UserContext for testing."""
    return UserContext(user_id="user-123", email="test@test.com")


class TestCheckoutEndpoint:
    def test_creates_checkout_session(self):
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            with patch("app.routers.billing.stripe") as mock_stripe:
                mock_stripe.checkout.Session.create.return_value = MagicMock(
                    url="https://checkout.stripe.com/123"
                )
                mock_stripe.StripeError = Exception

                response = client.post(
                    "/api/billing/checkout",
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 200
            assert response.json()["url"] == "https://checkout.stripe.com/123"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_requires_auth(self):
        response = client.post("/api/billing/checkout")
        assert response.status_code == 401


class TestPortalEndpoint:
    def test_creates_portal_session(self):
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"stripe_customer_id": "cus_abc"}
            )

            with (
                patch("app.routers.billing.stripe") as mock_stripe,
                patch("app.services.tier_service.supabase_admin", mock_sb),
            ):
                mock_stripe.billing_portal.Session.create.return_value = MagicMock(
                    url="https://billing.stripe.com/portal"
                )
                mock_stripe.StripeError = Exception

                response = client.post(
                    "/api/billing/portal",
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 200
            assert response.json()["url"] == "https://billing.stripe.com/portal"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_no_customer_returns_400(self):
        app.dependency_overrides[get_current_user] = lambda: _mock_user()
        try:
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={}
            )

            with (
                patch("app.routers.billing.stripe") as mock_stripe,
                patch("app.services.tier_service.supabase_admin", mock_sb),
            ):
                mock_stripe.StripeError = Exception

                response = client.post(
                    "/api/billing/portal",
                    headers={"Authorization": "Bearer fake-token"},
                )
            assert response.status_code == 400
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_requires_auth(self):
        response = client.post("/api/billing/portal")
        assert response.status_code == 401


class TestStripeWebhook:
    @patch("app.routers.billing.stripe")
    @patch("app.routers.billing.TierService")
    def test_handles_checkout_completed(self, mock_tier, mock_stripe):
        mock_tier.update_user_tier = AsyncMock()
        mock_stripe.Webhook.construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "user-123",
                    "customer": "cus_abc",
                    "subscription": "sub_xyz",
                }
            },
        }
        mock_stripe.SignatureVerificationError = Exception

        response = client.post(
            "/api/webhooks/stripe",
            content=b"raw-body",
            headers={
                "stripe-signature": "fake-sig",
                "content-type": "application/json",
            },
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_tier.update_user_tier.assert_awaited_once_with(
            "user-123",
            "pro",
            stripe_customer_id="cus_abc",
            subscription_status="active",
        )

    @patch("app.routers.billing.stripe")
    @patch("app.routers.billing.TierService")
    def test_handles_subscription_deleted(self, mock_tier, mock_stripe):
        mock_tier.update_user_tier = AsyncMock()
        mock_stripe.Webhook.construct_event.return_value = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": "cus_abc",
                }
            },
        }
        mock_stripe.SignatureVerificationError = Exception

        with patch(
            "app.routers.billing._lookup_user_by_customer",
            new_callable=AsyncMock,
        ) as mock_lookup:
            mock_lookup.return_value = "user-123"
            response = client.post(
                "/api/webhooks/stripe",
                content=b"raw-body",
                headers={
                    "stripe-signature": "fake-sig",
                    "content-type": "application/json",
                },
            )
        assert response.status_code == 200
        mock_tier.update_user_tier.assert_awaited_once_with(
            "user-123",
            "free",
            subscription_status="canceled",
        )

    @patch("app.routers.billing.stripe")
    @patch("app.routers.billing.TierService")
    def test_handles_payment_failed(self, mock_tier, mock_stripe):
        mock_tier.update_user_tier = AsyncMock()
        mock_stripe.Webhook.construct_event.return_value = {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "customer": "cus_abc",
                }
            },
        }
        mock_stripe.SignatureVerificationError = Exception

        with patch(
            "app.routers.billing._lookup_user_by_customer",
            new_callable=AsyncMock,
        ) as mock_lookup:
            mock_lookup.return_value = "user-123"
            response = client.post(
                "/api/webhooks/stripe",
                content=b"raw-body",
                headers={
                    "stripe-signature": "fake-sig",
                    "content-type": "application/json",
                },
            )
        assert response.status_code == 200
        mock_tier.update_user_tier.assert_awaited_once_with(
            "user-123",
            "pro",
            subscription_status="past_due",
        )

    @patch("app.routers.billing.stripe")
    def test_invalid_signature_returns_400(self, mock_stripe):
        mock_stripe.Webhook.construct_event.side_effect = ValueError(
            "Invalid signature"
        )
        mock_stripe.SignatureVerificationError = type(
            "SignatureVerificationError", (Exception,), {}
        )

        response = client.post(
            "/api/webhooks/stripe",
            content=b"raw-body",
            headers={
                "stripe-signature": "bad-sig",
                "content-type": "application/json",
            },
        )
        assert response.status_code == 400


class TestLookupUserByCustomer:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_supabase(self):
        from app.routers.billing import _lookup_user_by_customer

        with patch("app.services.tier_service.supabase_admin", None):
            result = await _lookup_user_by_customer("cus_abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_customer_id(self):
        from app.routers.billing import _lookup_user_by_customer

        result = await _lookup_user_by_customer("")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_user_id_on_success(self):
        from app.routers.billing import _lookup_user_by_customer

        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"id": "user-123"}
        )

        with patch("app.services.tier_service.supabase_admin", mock_sb):
            result = await _lookup_user_by_customer("cus_abc")
        assert result == "user-123"

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        from app.routers.billing import _lookup_user_by_customer

        mock_sb = MagicMock()
        mock_sb.table.side_effect = Exception("DB error")

        with patch("app.services.tier_service.supabase_admin", mock_sb):
            result = await _lookup_user_by_customer("cus_abc")
        assert result is None
