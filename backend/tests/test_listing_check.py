"""Tests for checking a saved listing against its source.

Search runs off a weekly-swept corpus, so a result can be days old. The check
closes that gap at the moments it matters — favouriting, comparing, adding to
tours — rather than by scraping constantly.

The property these tests defend hardest: a check that could not reach the
source must record 'unknown', never 'live'. Getting that backwards is what made
the old corpus-wide verification certify every listing as alive purely because
apartments.com was refusing the request.
"""
import pytest

from app.services.listing_check import check_listing, diff_listing, LIVE, GONE, UNKNOWN


class _Status:
    def __init__(self, value):
        self.value = value


class _FakeResult:
    def __init__(self, status="completed", listings=None, errors=None):
        self.status = _Status(status)
        self.listings = listings or []
        self.errors = errors or []


class _FakeScraper:
    def __init__(self, result=None, raises=None):
        self._result = result
        self._raises = raises

    async def scrape_url(self, url):
        if self._raises:
            raise self._raises
        return self._result

    async def close(self):
        return None


def _patch_scraper(monkeypatch, result=None, raises=None):
    import app.services.scrapers.apify_service as mod
    monkeypatch.setattr(
        mod, "ApifyService", lambda source_id: _FakeScraper(result, raises)
    )


class _Norm:
    def __init__(self, success, listing):
        self.success = success
        self.listing = listing
        self.errors = [] if success else ["normalization failed"]


def _patch_normalizer(monkeypatch, listing=None, success=True):
    import app.services.normalization.normalizer as mod

    class _Svc:
        def normalize(self, _listing):
            return _Norm(success, listing)

    monkeypatch.setattr(mod, "NormalizationService", _Svc)


class TestDiffListing:
    def test_detects_a_rent_change(self):
        assert diff_listing({"rent": 2100}, {"rent": 1950}) == {
            "rent": {"from": 2100, "to": 1950}
        }

    def test_ignores_immaterial_fields(self):
        """A reworded description is not something to interrupt the user over."""
        assert diff_listing(
            {"rent": 2100, "description": "a", "images": ["x"]},
            {"rent": 2100, "description": "b", "images": ["y"]},
        ) == {}

    def test_absent_and_empty_are_not_a_change(self):
        """A field the scrape simply didn't populate must not read as a move."""
        assert diff_listing({"sqft": None}, {"sqft": 0}) == {}
        assert diff_listing({"available_date": ""}, {"available_date": None}) == {}

    def test_true_cost_is_material(self):
        d = diff_listing({"true_cost_monthly": 2480}, {"true_cost_monthly": 2330})
        assert d["true_cost_monthly"] == {"from": 2480, "to": 2330}

    def test_no_change_is_empty(self):
        assert diff_listing({"rent": 2100, "sqft": 800}, {"rent": 2100, "sqft": 800}) == {}


class TestCheckListing:
    @pytest.mark.asyncio
    async def test_no_source_url_is_unknown(self):
        status, updated, changes = await check_listing(None, {"rent": 2100})
        assert status == UNKNOWN
        assert updated is None

    @pytest.mark.asyncio
    async def test_scraper_exception_is_unknown_not_gone(self, monkeypatch):
        """A failure to reach the source says nothing about the listing."""
        _patch_scraper(monkeypatch, raises=RuntimeError("apify down"))
        status, updated, _ = await check_listing("https://x/y/", {"rent": 2100})
        assert status == UNKNOWN
        assert updated is None

    @pytest.mark.asyncio
    async def test_failed_run_is_unknown_not_gone(self, monkeypatch):
        _patch_scraper(monkeypatch, result=_FakeResult(status="failed", errors=["boom"]))
        status, updated, _ = await check_listing("https://x/y/", {"rent": 2100})
        assert status == UNKNOWN
        assert updated is None

    @pytest.mark.asyncio
    async def test_empty_result_means_gone(self, monkeypatch):
        """The actor ran fine and found nothing at a valid listing URL."""
        _patch_scraper(monkeypatch, result=_FakeResult(listings=[]))
        status, updated, _ = await check_listing("https://x/y/", {"rent": 2100})
        assert status == GONE
        assert updated is None

    @pytest.mark.asyncio
    async def test_normalization_failure_is_unknown(self, monkeypatch):
        _patch_scraper(monkeypatch, result=_FakeResult(listings=[object()]))
        _patch_normalizer(monkeypatch, listing=None, success=False)
        status, updated, _ = await check_listing("https://x/y/", {"rent": 2100})
        assert status == UNKNOWN

    @pytest.mark.asyncio
    async def test_live_with_a_price_move(self, monkeypatch):
        _patch_scraper(monkeypatch, result=_FakeResult(listings=[object()]))
        _patch_normalizer(
            monkeypatch,
            listing={"rent": 1950, "true_cost_monthly": 2330, "sqft": 800},
        )
        status, updated, changes = await check_listing(
            "https://x/y/", {"rent": 2100, "true_cost_monthly": 2480, "sqft": 800}
        )
        assert status == LIVE
        assert updated["rent"] == 1950
        assert changes["rent"] == {"from": 2100, "to": 1950}
        assert changes["true_cost_monthly"] == {"from": 2480, "to": 2330}

    @pytest.mark.asyncio
    async def test_only_volatile_fields_are_patched(self, monkeypatch):
        """The stored listing is ApartmentModel.to_dict() shape; the normalizer
        emits something adjacent but not identical. Replacing wholesale would
        drop display fields the UI needs, so the check patches in place."""
        _patch_scraper(monkeypatch, result=_FakeResult(listings=[object()]))
        _patch_normalizer(monkeypatch, listing={"rent": 1950})

        current = {
            "rent": 2100,
            "beds_label": "2 bd",
            "baths_label": "1 ba",
            "images": ["cached.jpg"],
            "address": "1 Test St",
        }
        status, updated, _ = await check_listing("https://x/y/", current)

        assert status == LIVE
        assert updated["rent"] == 1950
        # Everything the normalizer didn't speak to survives untouched.
        assert updated["beds_label"] == "2 bd"
        assert updated["images"] == ["cached.jpg"]
        assert updated["address"] == "1 Test St"

    @pytest.mark.asyncio
    async def test_sparse_result_does_not_blank_fields(self, monkeypatch):
        _patch_scraper(monkeypatch, result=_FakeResult(listings=[object()]))
        _patch_normalizer(monkeypatch, listing={"rent": 2100, "sqft": None})
        _, updated, changes = await check_listing("https://x/y/", {"rent": 2100, "sqft": 800})
        assert updated["sqft"] == 800
        assert changes == {}


class TestChangeMarker:
    """The correction surfaces as an explicit marker, so the diff has to be
    readable by the frontend — analytics_events is service-role only."""

    def test_diff_shape_is_renderable(self):
        """{field: {from, to}} is what last_change stores and the marker reads."""
        d = diff_listing(
            {"rent": 2100, "true_cost_monthly": 2480},
            {"rent": 1950, "true_cost_monthly": 2330},
        )
        assert d == {
            "rent": {"from": 2100, "to": 1950},
            "true_cost_monthly": {"from": 2480, "to": 2330},
        }
        # Every entry must carry both sides, or the marker cannot say
        # "was X, now Y".
        for change in d.values():
            assert set(change) == {"from", "to"}

    def test_no_marker_when_nothing_material_moved(self):
        """An empty diff must stay empty, so last_change is not set and no
        marker appears for a check that found nothing."""
        assert diff_listing({"rent": 2100, "description": "old"},
                            {"rent": 2100, "description": "new"}) == {}


class _FakeScrapedBuilding:
    """A scraped apartments.com building with two floorplans, one unpriced."""

    floor_plans = [
        {
            "modelId": "m1",
            "details": ["1 bed", "1 bath", "600 sq ft"],
            "totalPrice": "$2,400",
            "squareFeet": "600",
            "availability": "3 Available",
        },
        {
            "modelId": "m2",
            "details": ["2 beds", "2 baths", "950 sq ft"],
            "totalPrice": "Call for Rent",
            "squareFeet": "950",
            "availability": "2 Available",
        },
    ]
    available_units = []
    bedrooms = 1
    bathrooms = 1.0
    rent = 2400
    sqft = 600
    available_date = None
    description = ""
    city = "Boston"


class TestFloorplanReprojection:
    """A saved copy that names a floorplan must be re-checked as that floorplan.

    The patch the check applies is building-level, so without re-projection it
    overwrites the bucket's rent with the building's. That is how a card reading
    "Price on request" became a favourite reading "$3,390/mo" — and the
    substitution was then reported to the user as a price change.
    """

    @pytest.mark.asyncio
    async def test_unpriced_floorplan_stays_unpriced(self, monkeypatch):
        _patch_scraper(
            monkeypatch,
            result=_FakeResult(listings=[_FakeScrapedBuilding()]),
        )
        _patch_normalizer(monkeypatch, listing={"rent": 2400, "bedrooms": 1, "sqft": 600})

        saved = {
            "rent": None,
            "bedrooms": 2,
            "bathrooms": 2,
            "sqft": 950,
            "matched_floorplan": {"bedrooms": 2, "bathrooms": 2.0, "price_on_request": True},
        }
        status, updated, changes = await check_listing("https://x/y/", saved)

        assert status == LIVE
        # The building's $2,400 one-bed must not become this unit's price.
        assert updated["rent"] is None
        assert updated["matched_floorplan"]["price_on_request"] is True
        assert updated["bedrooms"] == 2
        assert "rent" not in changes

    @pytest.mark.asyncio
    async def test_priced_floorplan_tracks_its_own_rent(self, monkeypatch):
        _patch_scraper(
            monkeypatch,
            result=_FakeResult(listings=[_FakeScrapedBuilding()]),
        )
        _patch_normalizer(monkeypatch, listing={"rent": 2400, "bedrooms": 1})

        saved = {
            "rent": 2200,
            "bedrooms": 1,
            "bathrooms": 1,
            "matched_floorplan": {"bedrooms": 1, "bathrooms": 1.0, "price_on_request": False},
        }
        _, updated, changes = await check_listing("https://x/y/", saved)

        assert updated["rent"] == 2400
        assert changes["rent"] == {"from": 2200, "to": 2400}

    @pytest.mark.asyncio
    async def test_withdrawn_floorplan_keeps_its_identity(self, monkeypatch):
        """The building is live but no longer lists this plan. The user asked
        about a 3-bed; answering with the building's 1-bed rent would be a
        different listing wearing the same name."""
        _patch_scraper(
            monkeypatch,
            result=_FakeResult(listings=[_FakeScrapedBuilding()]),
        )
        _patch_normalizer(monkeypatch, listing={"rent": 2400, "bedrooms": 1})

        saved = {
            "rent": 3100,
            "bedrooms": 3,
            "bathrooms": 2,
            "matched_floorplan": {
                "bedrooms": 3,
                "bathrooms": 2.0,
                "min_rent": 3100,
                "max_rent": 3100,
                "available_units": 1,
            },
        }
        status, updated, _ = await check_listing("https://x/y/", saved)

        assert status == LIVE
        assert updated["bedrooms"] == 3
        assert updated["matched_floorplan"]["available_units"] == 0
        assert updated["rent"] == 3100  # still the plan's own price, not the building's

    @pytest.mark.asyncio
    async def test_building_copy_is_untouched(self, monkeypatch):
        """A listing saved without a floorplan keeps the old building-level
        behaviour — reprojection must not leak into that path."""
        _patch_scraper(monkeypatch, result=_FakeResult(listings=[object()]))
        _patch_normalizer(monkeypatch, listing={"rent": 2400})

        _, updated, changes = await check_listing("https://x/y/", {"rent": 2200})

        assert updated["rent"] == 2400
        assert "matched_floorplan" not in updated
        assert changes["rent"] == {"from": 2200, "to": 2400}
