"""Tests for listing verification and freshness decay.

The bug these exist to prevent: _verify_listing used to treat anything that
wasn't a 404 or a 200-with-removal-text as proof the listing was alive. Since
apartments.com is Akamai-fenced and 403s every automated request, that marked
the entire corpus "verified" *because* we were blocked — and because the
deactivation guard skips anything marked "verified", those rows then became
permanently immune to expiry.
"""
import pytest

from app.models.market_config import (
    TIER_DECAY_RATES,
    DEFAULT_DECAY_RATE,
    SEARCH_FLOOR,
    MarketConfigModel,
)


class _FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeClient:
    """Stands in for httpx.AsyncClient as an async context manager."""

    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url):
        if self._raises:
            raise self._raises
        return self._response


class _FakeApartment:
    def __init__(self, source_url="https://www.apartments.com/aera/g5qm48y/"):
        self.id = "apt-1"
        self.source_url = source_url
        self.verified_at = None


def _patch_verification(monkeypatch, response=None, raises=None):
    """Wire up _verify_listing against a fake DB session and HTTP client.

    Returns the list that captures every .values(...) payload written, so a
    test can assert on what the task tried to persist.
    """
    import httpx
    from app.tasks import maintenance_tasks as mt

    written = []

    class _FakeResult:
        def scalar_one_or_none(self):
            return _FakeApartment()

    class _FakeSession:
        async def execute(self, stmt):
            # SQLAlchemy Update objects expose their SET clause here; selects
            # don't, and fall through to the apartment fetch.
            compiled = getattr(stmt, "_values", None)
            if compiled is not None:
                written.append({str(k.name): v.value for k, v in compiled.items()})
                return None
            return _FakeResult()

        async def commit(self):
            return None

    class _FakeSessionCtx:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, *exc_info):
            return False

    monkeypatch.setattr(mt, "get_session_context", lambda: _FakeSessionCtx())
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: _FakeClient(response=response, raises=raises)
    )
    return mt, written


class TestVerifyListing:
    """A verification must never turn 'we were blocked' into 'it's alive'."""

    @pytest.mark.asyncio
    async def test_403_is_unknown_not_verified(self, monkeypatch):
        """Akamai blocking us tells us nothing about the listing."""
        mt, written = _patch_verification(monkeypatch, response=_FakeResponse(403))

        result = await mt._verify_listing("apt-1")

        assert result["status"] == "unknown"
        assert "403" in result["detail"]
        # Only verified_at may be touched — never the listing's standing.
        assert written == [{"verified_at": written[0]["verified_at"]}]
        assert "verification_status" not in written[0]
        assert "freshness_confidence" not in written[0]
        assert "is_active" not in written[0]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [429, 500, 502, 503])
    async def test_other_non_200_codes_are_unknown(self, monkeypatch, status_code):
        mt, written = _patch_verification(monkeypatch, response=_FakeResponse(status_code))

        result = await mt._verify_listing("apt-1")

        assert result["status"] == "unknown"
        assert "verification_status" not in written[0]

    @pytest.mark.asyncio
    async def test_network_error_is_unknown(self, monkeypatch):
        mt, written = _patch_verification(monkeypatch, raises=TimeoutError("timed out"))

        result = await mt._verify_listing("apt-1")

        assert result["status"] == "unknown"
        assert "verification_status" not in written[0]

    @pytest.mark.asyncio
    async def test_404_marks_gone_and_deactivates(self, monkeypatch):
        mt, written = _patch_verification(monkeypatch, response=_FakeResponse(404))

        result = await mt._verify_listing("apt-1")

        assert result["status"] == "gone"
        assert written[0]["verification_status"] == "gone"
        assert written[0]["is_active"] == 0

    @pytest.mark.asyncio
    async def test_removal_notice_in_body_marks_gone(self, monkeypatch):
        mt, written = _patch_verification(
            monkeypatch,
            response=_FakeResponse(200, "<h1>This listing has been removed</h1>"),
        )

        result = await mt._verify_listing("apt-1")

        assert result["status"] == "gone"
        assert written[0]["is_active"] == 0

    @pytest.mark.asyncio
    async def test_clean_200_marks_verified(self, monkeypatch):
        """The only response that actually proves the listing is live."""
        mt, written = _patch_verification(
            monkeypatch, response=_FakeResponse(200, "<h1>Aera — 2 beds available</h1>")
        )

        result = await mt._verify_listing("apt-1")

        assert result["status"] == "verified"
        assert written[0]["verification_status"] == "verified"
        assert written[0]["freshness_confidence"] == 80

    @pytest.mark.asyncio
    async def test_skips_listing_without_source_url(self, monkeypatch):
        mt, _ = _patch_verification(monkeypatch, response=_FakeResponse(200))

        class _NoUrlResult:
            def scalar_one_or_none(self):
                return _FakeApartment(source_url=None)

        class _NoUrlSession:
            async def execute(self, stmt):
                return _NoUrlResult()

            async def commit(self):
                return None

        class _Ctx:
            async def __aenter__(self):
                return _NoUrlSession()

            async def __aexit__(self, *exc_info):
                return False

        monkeypatch.setattr(mt, "get_session_context", lambda: _Ctx())

        result = await mt._verify_listing("apt-1")
        assert result["status"] == "skipped"


class TestBulkVerificationDefault:
    def test_bulk_verification_is_off_by_default(self):
        """A corpus-wide sweep of a host that blocks us is all cost, no answer."""
        from app.tasks import maintenance_tasks as mt

        assert mt.BULK_VERIFICATION_ENABLED is False


class TestDecayRates:
    """Decay decides how long an un-re-seen listing stays visible."""

    def test_rates_are_derived_from_days_to_search_floor(self):
        """Recalibrated 2026-09-25 when sweeps moved to weekly."""
        for tier, expected_days in (("hot", 21), ("standard", 28), ("cool", 35)):
            rate = TIER_DECAY_RATES[tier]
            days_to_floor = (100 - SEARCH_FLOOR) / rate / 24
            assert days_to_floor == pytest.approx(expected_days, abs=0.01)

    @pytest.mark.parametrize("tier", ["hot", "standard", "cool"])
    def test_a_listing_survives_several_missed_weekly_sweeps(self, tier):
        """The invariant that matters, independent of the exact rates.

        Sweeps run weekly. At the old 3/hr a hot listing was hidden 20h after a
        scrape; at 7 days it reached the floor the very hour its next weekly
        sweep was due, so any delay dropped the market out of search. A listing
        must outlive at least two missed sweeps.
        """
        WEEK = 24 * 7
        hours_to_floor = (100 - SEARCH_FLOOR) / TIER_DECAY_RATES[tier]
        assert hours_to_floor > WEEK * 2

    @pytest.mark.parametrize("tier", ["hot", "standard", "cool"])
    def test_confidence_stays_above_the_floor_across_one_sweep(self, tier):
        """A listing re-seen on schedule must never dip below the search floor."""
        WEEK = 24 * 7
        assert 100 - WEEK * TIER_DECAY_RATES[tier] > SEARCH_FLOOR

    def test_ordering_is_hot_fastest_cool_slowest(self):
        assert TIER_DECAY_RATES["hot"] > TIER_DECAY_RATES["standard"]
        assert TIER_DECAY_RATES["standard"] > TIER_DECAY_RATES["cool"]

    def test_model_property_matches_shared_table(self):
        """MarketConfig.decay_rate and the decay task must not drift apart."""
        for tier in ("hot", "standard", "cool"):
            market = MarketConfigModel(id="m", display_name="M", city="C", state="XX", tier=tier)
            assert market.decay_rate == TIER_DECAY_RATES[tier]

    def test_unknown_tier_falls_back_to_default(self):
        market = MarketConfigModel(id="m", display_name="M", city="C", state="XX", tier="bogus")
        assert market.decay_rate == DEFAULT_DECAY_RATE


class TestUrlModeInput:
    """scrape_url is the acquisition primitive for add-by-URL."""

    def test_apartments_com_url_input_uses_start_urls(self):
        from app.services.scrapers.apify_service import ApifyService

        actor_input = ApifyService("apartments_com")._build_url_input(
            "https://www.apartments.com/aera/g5qm48y/"
        )
        # Bare strings are rejected by these actors — must be {"url": ...}.
        assert actor_input["startUrls"] == [
            {"url": "https://www.apartments.com/aera/g5qm48y/"}
        ]
        assert actor_input["maxItems"] == 1
        assert actor_input["includeWalkScore"] is True

    def test_zillow_url_input_uses_search_urls(self):
        from app.services.scrapers.apify_service import ApifyService

        actor_input = ApifyService("zillow")._build_url_input("https://www.zillow.com/x/")
        assert actor_input["searchUrls"] == [{"url": "https://www.zillow.com/x/"}]
        assert "startUrls" not in actor_input

    def test_search_mode_input_is_unchanged(self):
        """URL mode must not disturb the bulk path."""
        from app.services.scrapers.apify_service import ApifyService

        actor_input = ApifyService("apartments_com")._build_apartments_com_input(
            "Boston", "MA", 100
        )
        assert actor_input["search"] == "Boston, MA"
        assert actor_input["maxItems"] == 100
