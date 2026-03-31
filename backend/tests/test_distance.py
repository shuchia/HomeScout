"""Tests for Haversine distance calculation."""
import pytest
from app.services.distance import haversine_miles, add_distances


class TestHaversine:
    def test_same_point_returns_zero(self):
        assert haversine_miles(39.95, -75.16, 39.95, -75.16) == 0.0

    def test_known_distance_philly_to_bryn_mawr(self):
        dist = haversine_miles(39.9526, -75.1635, 40.0210, -75.3162)
        assert 9.0 < dist < 10.5

    def test_short_distance(self):
        dist = haversine_miles(39.9526, -75.1635, 39.9670, -75.1635)
        assert 0.5 < dist < 1.5

    def test_returns_float(self):
        result = haversine_miles(40.0, -75.0, 40.1, -75.1)
        assert isinstance(result, float)


class TestAddDistances:
    def test_adds_distance_to_apartments(self):
        apartments = [
            {"id": "a1", "latitude": 39.9526, "longitude": -75.1635},
            {"id": "a2", "latitude": 40.0210, "longitude": -75.3162},
        ]
        result = add_distances(apartments, near_lat=39.95, near_lng=-75.16)
        assert result[0]["distance_miles"] is not None
        assert result[1]["distance_miles"] is not None
        assert result[0]["distance_miles"] < result[1]["distance_miles"]

    def test_sorts_by_distance(self):
        apartments = [
            {"id": "far", "latitude": 40.5, "longitude": -75.5},
            {"id": "close", "latitude": 39.95, "longitude": -75.16},
        ]
        result = add_distances(apartments, near_lat=39.95, near_lng=-75.16)
        assert result[0]["id"] == "close"
        assert result[1]["id"] == "far"

    def test_missing_coords_placed_last(self):
        apartments = [
            {"id": "no-coords", "latitude": None, "longitude": None},
            {"id": "has-coords", "latitude": 39.95, "longitude": -75.16},
        ]
        result = add_distances(apartments, near_lat=39.95, near_lng=-75.16)
        assert result[0]["id"] == "has-coords"
        assert result[1]["id"] == "no-coords"
        assert result[1]["distance_miles"] is None

    def test_filters_by_max_distance(self):
        apartments = [
            {"id": "close", "latitude": 39.9526, "longitude": -75.1635},
            {"id": "far", "latitude": 40.5, "longitude": -75.5},
        ]
        result = add_distances(apartments, near_lat=39.95, near_lng=-75.16, max_distance_miles=5.0)
        assert len(result) == 1
        assert result[0]["id"] == "close"

    def test_no_filter_when_max_distance_none(self):
        apartments = [
            {"id": "close", "latitude": 39.9526, "longitude": -75.1635},
            {"id": "far", "latitude": 40.5, "longitude": -75.5},
        ]
        result = add_distances(apartments, near_lat=39.95, near_lng=-75.16, max_distance_miles=None)
        assert len(result) == 2

    def test_empty_list(self):
        result = add_distances([], near_lat=39.95, near_lng=-75.16)
        assert result == []
