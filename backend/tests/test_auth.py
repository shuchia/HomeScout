"""Tests for Supabase JWT auth dependencies."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from app.auth import get_current_user, get_optional_user, UserContext


class TestGetCurrentUser:
    """Test mandatory auth dependency."""

    def test_missing_header_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                get_current_user(authorization=None)
            )
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                get_current_user(authorization="Bearer invalid-token")
            )
        assert exc_info.value.status_code == 401

    @patch("app.auth._decode_supabase_jwt")
    def test_valid_token_returns_user_context(self, mock_decode):
        mock_decode.return_value = {
            "sub": "user-123",
            "email": "test@example.com"
        }
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            get_current_user(authorization="Bearer valid-token")
        )
        assert isinstance(result, UserContext)
        assert result.user_id == "user-123"
        assert result.email == "test@example.com"


class TestGetOptionalUser:
    """Test optional auth dependency (returns None if no token)."""

    def test_no_header_returns_none(self):
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            get_optional_user(authorization=None)
        )
        assert result is None

    @patch("app.auth._decode_supabase_jwt")
    def test_valid_token_returns_user_context(self, mock_decode):
        mock_decode.return_value = {
            "sub": "user-456",
            "email": "pro@example.com"
        }
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            get_optional_user(authorization="Bearer valid-token")
        )
        assert result is not None
        assert result.user_id == "user-456"
        assert result.email == "pro@example.com"

    def test_invalid_token_returns_none(self):
        """Optional auth should return None for invalid tokens, not raise."""
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            get_optional_user(authorization="Bearer bad-token")
        )
        assert result is None
