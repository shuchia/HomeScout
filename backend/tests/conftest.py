"""Pytest configuration for backend tests."""
import os
import pytest

# Disable rate limiting middleware during tests
os.environ["TESTING"] = "1"


@pytest.fixture(scope="session")
def anyio_backend():
    """Specify the async backend for pytest-asyncio."""
    return "asyncio"
