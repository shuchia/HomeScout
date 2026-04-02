"""Pytest configuration for backend tests."""
import os
import pytest

# Disable rate limiting middleware during tests
os.environ["TESTING"] = "1"

# Force JSON mode for tests (avoid connecting to PostgreSQL)
os.environ["USE_DATABASE"] = "false"


@pytest.fixture(autouse=True)
def _force_json_mode(monkeypatch):
    """Ensure database mode is disabled for all tests."""
    import app.database
    monkeypatch.setattr(app.database, "USE_DATABASE", False)


@pytest.fixture(scope="session")
def anyio_backend():
    """Specify the async backend for pytest-asyncio."""
    return "asyncio"
