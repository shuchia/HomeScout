"""Tests for Redis-based rate limiting middleware."""
import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.rate_limit import (
    RateLimitMiddleware,
    GLOBAL_LIMIT,
    EXPENSIVE_LIMIT,
    ANON_LIMIT,
)
import app.middleware.rate_limit as rl_module


@pytest.fixture(autouse=True)
def _clear_testing_env(monkeypatch):
    """Clear TESTING env var so rate limit middleware runs during these tests."""
    monkeypatch.delenv("TESTING", raising=False)


def _build_app_and_client(mock_redis_client=None):
    """Build a minimal FastAPI app with rate limiting middleware and return a TestClient."""
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/search")
    async def search():
        return {"results": []}

    @app.post("/api/apartments/compare")
    async def compare():
        return {"comparison": {}}

    @app.get("/api/apartments/list")
    async def list_apartments():
        return {"apartments": []}

    patcher = patch.object(rl_module, "redis")
    mock_redis_mod = patcher.start()
    if mock_redis_client is None:
        mock_redis_mod.from_url.side_effect = Exception("No Redis")
    else:
        mock_redis_mod.from_url.return_value = mock_redis_client

    app.add_middleware(RateLimitMiddleware)
    client = TestClient(app)
    return client, patcher


def _make_mock_redis(counter_value=1):
    """Create a mock Redis client that returns the given counter value on incr."""
    mock = MagicMock()
    mock.incr.return_value = counter_value
    mock.expire.return_value = True
    return mock


class TestRateLimitNormalRequests:
    """Test that normal requests pass through under the limit."""

    def test_authenticated_request_under_limit(self):
        mock_redis = _make_mock_redis(counter_value=1)
        client, patcher = _build_app_and_client(mock_redis)
        try:
            response = client.get(
                "/health",
                headers={"Authorization": "Bearer test-token-123"},
            )
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
        finally:
            patcher.stop()

    def test_anonymous_request_under_limit(self):
        mock_redis = _make_mock_redis(counter_value=1)
        client, patcher = _build_app_and_client(mock_redis)
        try:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
        finally:
            patcher.stop()

    def test_multiple_requests_under_limit(self):
        """Simulate multiple requests all under the limit."""
        call_count = 0

        def incr_side_effect(key):
            nonlocal call_count
            call_count += 1
            return call_count

        mock_redis = MagicMock()
        mock_redis.incr.side_effect = incr_side_effect
        mock_redis.expire.return_value = True

        client, patcher = _build_app_and_client(mock_redis)
        try:
            for _ in range(5):
                response = client.get("/health")
                assert response.status_code == 200
        finally:
            patcher.stop()


class TestRateLimitExceeded:
    """Test that 429 is returned when rate limit is exceeded."""

    def test_returns_429_when_limit_exceeded(self):
        mock_redis = _make_mock_redis(counter_value=GLOBAL_LIMIT + 1)
        client, patcher = _build_app_and_client(mock_redis)
        try:
            response = client.get(
                "/health",
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status_code == 429
            assert "Rate limit exceeded" in response.json()["detail"]
        finally:
            patcher.stop()

    def test_anonymous_429_at_lower_limit(self):
        """Anonymous users hit the limit at ANON_LIMIT (10)."""
        mock_redis = _make_mock_redis(counter_value=ANON_LIMIT + 1)
        client, patcher = _build_app_and_client(mock_redis)
        try:
            response = client.get("/health")
            assert response.status_code == 429
            assert "Rate limit exceeded" in response.json()["detail"]
        finally:
            patcher.stop()

    def test_authenticated_at_anon_limit_still_passes(self):
        """Authenticated users have higher limit (GLOBAL_LIMIT=60), so
        a count of ANON_LIMIT+1 should still pass for them."""
        mock_redis = _make_mock_redis(counter_value=ANON_LIMIT + 1)
        client, patcher = _build_app_and_client(mock_redis)
        try:
            response = client.get(
                "/health",
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status_code == 200
        finally:
            patcher.stop()


class TestExpensivePaths:
    """Test that expensive paths (/api/search, /api/apartments/compare) get
    a stricter limit of EXPENSIVE_LIMIT (10)."""

    def test_search_gets_expensive_limit(self):
        mock_redis = _make_mock_redis(counter_value=EXPENSIVE_LIMIT + 1)
        client, patcher = _build_app_and_client(mock_redis)
        try:
            response = client.post(
                "/api/search",
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status_code == 429
        finally:
            patcher.stop()

    def test_compare_gets_expensive_limit(self):
        mock_redis = _make_mock_redis(counter_value=EXPENSIVE_LIMIT + 1)
        client, patcher = _build_app_and_client(mock_redis)
        try:
            response = client.post(
                "/api/apartments/compare",
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status_code == 429
        finally:
            patcher.stop()

    def test_non_expensive_path_not_limited_at_expensive_threshold(self):
        """Non-expensive paths should NOT be limited at EXPENSIVE_LIMIT
        for authenticated users."""
        mock_redis = _make_mock_redis(counter_value=EXPENSIVE_LIMIT + 1)
        client, patcher = _build_app_and_client(mock_redis)
        try:
            response = client.get(
                "/api/apartments/list",
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status_code == 200
        finally:
            patcher.stop()


class TestRedisUnavailable:
    """Test fail-open behaviour when Redis is unavailable."""

    def test_no_redis_passes_through(self):
        """When Redis connection fails, all requests pass through."""
        client, patcher = _build_app_and_client(mock_redis_client=None)
        try:
            response = client.get("/health")
            assert response.status_code == 200
        finally:
            patcher.stop()

    def test_redis_error_passes_through(self):
        """When Redis raises an exception on incr, request still passes."""
        mock_redis = MagicMock()
        mock_redis.incr.side_effect = Exception("Redis connection lost")
        client, patcher = _build_app_and_client(mock_redis)
        try:
            response = client.get("/health")
            assert response.status_code == 200
        finally:
            patcher.stop()


class TestRedisKeyManagement:
    """Test that Redis keys are set with correct expiry."""

    def test_expire_set_on_first_request(self):
        """On the first request (incr returns 1), expire should be called."""
        mock_redis = _make_mock_redis(counter_value=1)
        client, patcher = _build_app_and_client(mock_redis)
        try:
            client.get("/health")
            mock_redis.expire.assert_called()
            call_args = mock_redis.expire.call_args
            assert call_args[0][1] == 120
        finally:
            patcher.stop()

    def test_expire_not_set_on_subsequent_requests(self):
        """On subsequent requests (incr returns >1), expire should NOT be called."""
        mock_redis = _make_mock_redis(counter_value=5)
        client, patcher = _build_app_and_client(mock_redis)
        try:
            client.get("/health")
            mock_redis.expire.assert_not_called()
        finally:
            patcher.stop()
