"""Tests for the tier service."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.tier_service import TierService, DAILY_SEARCH_LIMIT, DAILY_AI_LIMIT


class TestGetUserTier:
    @pytest.mark.asyncio
    @patch("app.services.tier_service.supabase_admin")
    async def test_returns_free_for_default_user(self, mock_sb):
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"user_tier": "free"}
        )
        tier = await TierService.get_user_tier("user-123")
        assert tier == "free"

    @pytest.mark.asyncio
    @patch("app.services.tier_service.supabase_admin")
    async def test_returns_pro_for_upgraded_user(self, mock_sb):
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"user_tier": "pro"}
        )
        tier = await TierService.get_user_tier("user-456")
        assert tier == "pro"


class TestCheckSearchLimit:
    @pytest.mark.asyncio
    @patch("app.services.tier_service.TierService._get_redis")
    async def test_user_under_limit_allowed(self, mock_redis):
        r = AsyncMock()
        r.get.return_value = b"10"
        mock_redis.return_value = r
        allowed, remaining = await TierService.check_search_limit("user-123")
        assert allowed is True
        assert remaining == DAILY_SEARCH_LIMIT - 10

    @pytest.mark.asyncio
    @patch("app.services.tier_service.TierService._get_redis")
    async def test_user_at_limit_blocked(self, mock_redis):
        r = AsyncMock()
        r.get.return_value = str(DAILY_SEARCH_LIMIT).encode()
        mock_redis.return_value = r
        allowed, remaining = await TierService.check_search_limit("user-123")
        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    @patch("app.services.tier_service.TierService._get_redis")
    async def test_no_redis_fails_open(self, mock_redis):
        mock_redis.side_effect = Exception("Redis down")
        allowed, remaining = await TierService.check_search_limit("user-123")
        assert allowed is True  # Fail open


def _consent(mock_sb, value):
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"ai_consent_at": value}
    )


class TestAiConsent:
    @pytest.mark.asyncio
    @patch("app.services.tier_service.supabase_admin")
    async def test_consented_user(self, mock_sb):
        _consent(mock_sb, "2026-10-18T00:00:00Z")
        assert await TierService.has_ai_consent("user-1") is True

    @pytest.mark.asyncio
    @patch("app.services.tier_service.supabase_admin")
    async def test_never_consented(self, mock_sb):
        _consent(mock_sb, None)
        assert await TierService.has_ai_consent("user-1") is False

    @pytest.mark.asyncio
    @patch("app.services.tier_service.supabase_admin")
    async def test_lookup_error_fails_closed(self, mock_sb):
        mock_sb.table.side_effect = Exception("column ai_consent_at does not exist")
        assert await TierService.has_ai_consent("user-1") is False


class TestConsumeAiCall:
    @pytest.mark.asyncio
    @patch("app.services.tier_service.TierService._get_redis")
    async def test_last_call_in_cap_allowed(self, mock_redis):
        r = AsyncMock()
        r.incr.return_value = DAILY_AI_LIMIT
        mock_redis.return_value = r
        assert await TierService.consume_ai_call("user-1") is True
        r.expire.assert_awaited()

    @pytest.mark.asyncio
    @patch("app.services.tier_service.TierService._get_redis")
    async def test_over_cap_refused(self, mock_redis):
        r = AsyncMock()
        r.incr.return_value = DAILY_AI_LIMIT + 1
        mock_redis.return_value = r
        assert await TierService.consume_ai_call("user-1") is False

    @pytest.mark.asyncio
    @patch("app.services.tier_service.TierService._get_redis")
    async def test_no_redis_fails_open(self, mock_redis):
        mock_redis.side_effect = Exception("Redis down")
        assert await TierService.consume_ai_call("user-1") is True


class TestAiDenial:
    @pytest.mark.asyncio
    @patch.object(TierService, "consume_ai_call", new_callable=AsyncMock)
    @patch.object(TierService, "has_ai_consent", new_callable=AsyncMock, return_value=False)
    async def test_no_consent_is_403_and_spends_nothing(self, _consent, consume):
        denial = await TierService.ai_denial("user-1")
        assert denial.status_code == 403
        consume.assert_not_awaited()

    @pytest.mark.asyncio
    @patch.object(TierService, "consume_ai_call", new_callable=AsyncMock, return_value=False)
    @patch.object(TierService, "has_ai_consent", new_callable=AsyncMock, return_value=True)
    async def test_cap_spent_is_429(self, _consent, _consume):
        denial = await TierService.ai_denial("user-1")
        assert denial.status_code == 429

    @pytest.mark.asyncio
    @patch.object(TierService, "consume_ai_call", new_callable=AsyncMock, return_value=True)
    @patch.object(TierService, "has_ai_consent", new_callable=AsyncMock, return_value=True)
    async def test_allowed(self, _consent, _consume):
        assert await TierService.ai_denial("user-1") is None
