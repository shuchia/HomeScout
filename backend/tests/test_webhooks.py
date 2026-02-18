"""Tests for Supabase webhook endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_webhook_unauthorized():
    """Test that webhook rejects requests without secret."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/supabase/check-matches",
            json={"city": "Bryn Mawr"}
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_authorized():
    """Test that webhook accepts requests with valid secret."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/supabase/check-matches",
            json={"city": "San Francisco", "budget": 3000},
            headers={"x-webhook-secret": "test-secret"}
        )
    assert response.status_code == 200
    assert "matches" in response.json()
    assert "count" in response.json()
