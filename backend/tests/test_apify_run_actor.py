"""Tests for running an Apify actor end to end, against a fake Apify API.

Every other Apify test mocks out _run_actor, so none of them noticed when it
started raising NameError on 2026-10-10 (fd54efe). The broad except in
_run_actor turned that into None, which _execute reports as "Actor run failed
or returned no data" — while the run itself succeeded on Apify. Every weekly
sweep and every saved-listing check failed for three weeks, and search emptied
out as the corpus decayed. These tests drive the real HTTP path instead.
"""
import httpx
import pytest

from app.services.scrapers import apify_service
from app.services.scrapers.apify_service import ApifyService


RUN = {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "ds-1"}
ITEM = {
    "id": "test-123",
    "address": "123 Main St",
    "location": {"fullAddress": "123 Main St, Pittsburgh, PA 15213", "city": "Pittsburgh", "state": "PA", "postalCode": "15213"},
    "rent": {"min": 1500, "max": 2000},
    "beds": "1 bd",
    "baths": "1 ba",
    "sqft": "600",
    "url": "https://www.apartments.com/test/123",
}


@pytest.fixture
def fake_apify(monkeypatch):
    """Route the service's httpx client to an in-process fake Apify API."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path.endswith("/runs"):
            return httpx.Response(201, json={"data": {"id": "run-1", "status": "RUNNING"}})
        if request.url.path.endswith("/actor-runs/run-1"):
            return httpx.Response(200, json={"data": RUN})
        if request.url.path.endswith("/datasets/ds-1/items"):
            return httpx.Response(200, json=[ITEM])
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        apify_service.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    return calls


async def test_bulk_scrape_collects_a_succeeded_run(fake_apify):
    result = await ApifyService(source_id="apartments_com").scrape("Pittsburgh", "PA", max_listings=10)

    assert result.errors == []
    assert result.status.value == "completed"
    assert result.total_found == 1
    assert len(result.listings) == 1


async def test_url_check_collects_a_succeeded_run(fake_apify):
    result = await ApifyService(source_id="apartments_com").scrape_url("https://www.apartments.com/test/123")

    assert result.errors == []
    assert result.status.value == "completed"
    assert len(result.listings) == 1
