"""Tests for apartment detail and batch endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_get_apartment_not_found():
    """Test that a non-existent apartment returns 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/apartments/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_apartments_batch_empty():
    """Test that an empty batch request returns an empty list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/apartments/batch", json=[])
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_apartment_success():
    """Test fetching an existing apartment by ID."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/apartments/apt-001")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "apt-001"
    assert "address" in data
    assert "rent" in data


@pytest.mark.asyncio
async def test_get_apartments_batch_success():
    """Test fetching multiple apartments by ID."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/apartments/batch", json=["apt-001", "apt-002"])
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    ids = [apt["id"] for apt in data]
    assert "apt-001" in ids
    assert "apt-002" in ids


@pytest.mark.asyncio
async def test_get_apartments_batch_partial():
    """Test batch request with some non-existent IDs."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/batch",
            json=["apt-001", "nonexistent-id", "apt-002"]
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3

    # Find the nonexistent entry
    nonexistent = next(apt for apt in data if apt["id"] == "nonexistent-id")
    assert nonexistent["is_available"] is False

    # Existing apartments should have full data
    apt_001 = next(apt for apt in data if apt["id"] == "apt-001")
    assert "address" in apt_001
    assert "rent" in apt_001


@pytest.mark.asyncio
async def test_get_apartments_batch_max_length():
    """Test that batch request with more than 50 IDs returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a list of 51 IDs
        ids = [f"apt-{i:03d}" for i in range(51)]
        response = await client.post("/api/apartments/batch", json=ids)
    assert response.status_code == 422


# === Comparison endpoint tests ===


@pytest.mark.asyncio
async def test_compare_apartments_empty():
    """Test that comparing zero apartments returns empty list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/compare",
            json={"apartment_ids": []}
        )
    assert response.status_code == 200
    assert response.json()["apartments"] == []


@pytest.mark.asyncio
async def test_compare_apartments_max_three():
    """Test that comparing more than 3 apartments returns validation error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/compare",
            json={"apartment_ids": ["apt-001", "apt-002", "apt-003", "apt-004"]}
        )
    assert response.status_code == 422  # Validation error from Field max_length


@pytest.mark.asyncio
async def test_compare_apartments_success():
    """Test successful comparison of valid apartments."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/compare",
            json={"apartment_ids": ["apt-001", "apt-002"]}
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["apartments"]) == 2
    assert "comparison_fields" in data
    assert "rent" in data["comparison_fields"]
    assert "bedrooms" in data["comparison_fields"]


@pytest.mark.asyncio
async def test_compare_apartments_with_nonexistent():
    """Test comparison with some non-existent apartment IDs."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/compare",
            json={"apartment_ids": ["apt-001", "nonexistent-id"]}
        )
    assert response.status_code == 200
    data = response.json()
    # Only the existing apartment should be returned
    assert len(data["apartments"]) == 1
    assert data["apartments"][0]["id"] == "apt-001"


@pytest.mark.asyncio
async def test_compare_apartments_with_preferences():
    """Test comparison with preferences triggers analysis."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/compare",
            json={
                "apartment_ids": ["apt-001", "apt-002"],
                "preferences": "parking, quiet neighborhood",
                "search_context": {
                    "city": "Bryn Mawr, PA",
                    "budget": 2000,
                    "bedrooms": 1,
                    "bathrooms": 1,
                    "property_type": "Apartment",
                    "move_in_date": "2026-03-01"
                }
            }
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["apartments"]) == 2
    assert "comparison_analysis" in data
    analysis = data["comparison_analysis"]
    assert "winner" in analysis
    assert analysis["winner"]["apartment_id"] in ["apt-001", "apt-002"]
    assert "reason" in analysis["winner"]
    assert "categories" in analysis
    assert len(analysis["categories"]) >= 3  # At least Value, Space, Amenities
    assert "apartment_scores" in analysis
    assert len(analysis["apartment_scores"]) == 2
    for score in analysis["apartment_scores"]:
        assert "overall_score" in score
        assert 0 <= score["overall_score"] <= 100
        assert "category_scores" in score
        for cat in analysis["categories"]:
            assert cat in score["category_scores"]


@pytest.mark.asyncio
async def test_compare_apartments_without_preferences_no_analysis():
    """Test comparison without preferences returns no analysis."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/apartments/compare",
            json={"apartment_ids": ["apt-001", "apt-002"]}
        )
    assert response.status_code == 200
    data = response.json()
    assert data.get("comparison_analysis") is None
