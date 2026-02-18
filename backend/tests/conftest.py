"""Pytest configuration for backend tests."""
import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Specify the async backend for pytest-asyncio."""
    return "asyncio"
