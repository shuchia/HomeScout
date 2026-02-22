"""Tests for the tier service."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.tier_service import TierService


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
    async def test_free_user_under_limit_allowed(self, mock_redis):
        r = AsyncMock()
        r.get.return_value = b"2"  # 2 of 3 used
        mock_redis.return_value = r
        allowed, remaining = await TierService.check_search_limit("user-123")
        assert allowed is True
        assert remaining == 1

    @pytest.mark.asyncio
    @patch("app.services.tier_service.TierService._get_redis")
    async def test_free_user_at_limit_blocked(self, mock_redis):
        r = AsyncMock()
        r.get.return_value = b"3"  # 3 of 3 used
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
