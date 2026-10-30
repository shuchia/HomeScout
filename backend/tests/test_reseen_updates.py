"""Tests for what a re-seen listing carries forward.

The bug these exist to prevent: the re-seen update payload omitted `rent`, so a
listing we already held kept its original price forever while its freshness was
reset to 100 — a stale price displayed as maximally fresh. The fuzzy matcher
accepts a rent within 10%, so a match never implied the price was unchanged.
"""
import pytest

from app.services.deduplication.deduplicator import DeduplicationService


def _listing(**overrides):
    base = {
        "id": "new-1",
        "address": "338 W College Ave",
        "address_normalized": "338 w college ave",
        "rent": 2000,
        "bedrooms": 2,
        "bathrooms": 1.0,
        "property_type": "Apartment",
        "true_cost_monthly": 2350,
        "true_cost_move_in": 4700,
        "images": ["a.jpg"],
        "description": "x" * 150,
        "available_date": "2026-10-01",
        "contact_phone": "555-0100",
        "contact_email": "leasing@example.com",
    }
    base.update(overrides)
    return base


class TestReseenPayload:
    def setup_method(self):
        self.dedup = DeduplicationService()

    def test_payload_carries_rent(self):
        upd = self.dedup._build_reseen_update(_listing(rent=1850), "existing-1", "hash-1")
        assert upd["rent"] == 1850
        assert upd["matched_id"] == "existing-1"
        assert upd["content_hash"] == "hash-1"

    def test_payload_carries_true_cost_with_rent(self):
        """Rent and its derived costs must travel together or the listing is
        internally inconsistent."""
        upd = self.dedup._build_reseen_update(
            _listing(rent=1850, true_cost_monthly=2200, true_cost_move_in=4400),
            "existing-1",
            "hash-1",
        )
        assert upd["true_cost_monthly"] == 2200
        assert upd["true_cost_move_in"] == 4400

    def test_payload_still_carries_existing_fields(self):
        upd = self.dedup._build_reseen_update(_listing(), "existing-1", "hash-1")
        assert upd["images"] == ["a.jpg"]
        assert upd["available_date"] == "2026-10-01"
        assert upd["contact_phone"] == "555-0100"
        assert upd["contact_email"] == "leasing@example.com"

    def test_hash_matched_reseen_carries_rent(self):
        """A content-hash match is the common re-see path."""
        listing = _listing(rent=1950)
        content_hash = self.dedup.generate_content_hash(listing)

        _new, updates, _skipped = self.dedup.deduplicate_batch_with_updates(
            [listing], {content_hash: "existing-1"}, []
        )

        assert len(updates) == 1
        assert updates[0]["matched_id"] == "existing-1"
        assert updates[0]["rent"] == 1950

    def test_fuzzy_matched_reseen_carries_the_new_rent(self):
        """The case the old code got most wrong.

        A price move under 10% still fuzzy-matches the existing row, so it was
        recorded as a re-see — and the new price was then discarded.
        """
        existing = [{
            "id": "existing-1",
            "address": "338 W College Ave",
            "address_normalized": "338 w college ave",
            "rent": 2000,
            "bedrooms": 2,
            "bathrooms": 1.0,
        }]
        # 2000 -> 1900 is a 5% drop: inside the fuzzy tolerance, so it matches,
        # and a real price change the user should see.
        moved = _listing(rent=1900, true_cost_monthly=2250)

        _new, updates, _skipped = self.dedup.deduplicate_batch_with_updates(
            [moved], {}, existing
        )

        assert len(updates) == 1, "a sub-10% price move should match, not insert"
        assert updates[0]["rent"] == 1900, "the new price must survive the match"
        assert updates[0]["true_cost_monthly"] == 2250

    def test_new_listing_is_not_treated_as_reseen(self):
        _new, updates, _skipped = self.dedup.deduplicate_batch_with_updates(
            [_listing()], {}, []
        )
        assert len(_new) == 1
        assert updates == []


class TestReseenRefreshesBuildingState:
    """Floorplan buckets are rebuilt from the stored row after a re-see, so the
    row must carry the new floorplans. It didn't: every building kept its
    first-insert floorplan prices and unit list forever, stamped fresh."""

    def setup_method(self):
        self.dedup = DeduplicationService()

    def test_payload_carries_floorplans_units_fees_and_pricing_model(self):
        plans = [{"modelName": "A1", "rentLabel": "$1,900", "availability": "2 Available"}]
        upd = self.dedup._build_reseen_update(
            _listing(
                floor_plans=plans,
                available_units=[],
                pricing_model="per_person",
                pricing_model_confidence=0.9,
                parking_fee=150,
                specials={"description": "1 month free"},
            ),
            "existing-1",
            "hash-1",
        )
        assert upd["floor_plans"] == plans
        assert upd["available_units"] == []
        assert upd["pricing_model"] == "per_person"
        assert upd["pricing_model_confidence"] == 0.9
        assert upd["parking_fee"] == 150
        assert upd["specials"] == {"description": "1 month free"}

    def test_fields_the_scrape_did_not_carry_are_none(self):
        upd = self.dedup._build_reseen_update(_listing(), "existing-1", "hash-1")
        assert upd["floor_plans"] is None
        assert upd["available_units"] is None


class _FakeSession:
    def __init__(self, log, fail_ids):
        self._log = log
        self._fail_ids = fail_ids

    async def execute(self, stmt):
        params = stmt.compile().params
        if params.get("id_1") in self._fail_ids:
            raise RuntimeError("duplicate key value violates unique constraint")
        self._log.append(params)

    async def commit(self):
        return None


def _patch_sessions(monkeypatch, fail_ids=()):
    from contextlib import asynccontextmanager
    import app.tasks.scrape_tasks as mod

    log = []

    @asynccontextmanager
    async def ctx():
        yield _FakeSession(log, set(fail_ids))

    monkeypatch.setattr(mod, "get_session_context", ctx)
    return log


class TestUpdateReseenListings:
    async def test_writes_refreshed_floorplans_and_keeps_what_the_scrape_lacked(self, monkeypatch):
        from app.tasks.scrape_tasks import _update_reseen_listings

        log = _patch_sessions(monkeypatch)
        plans = [{"modelName": "B2"}]
        dedup = DeduplicationService()
        upd = dedup._build_reseen_update(
            _listing(floor_plans=plans, available_units=[], pricing_model="per_unit"),
            "existing-1",
            "hash-1",
        )

        assert await _update_reseen_listings([upd]) == 1
        written = log[0]
        assert written["floor_plans"] == plans
        # An empty unit list is the source saying the building leased up.
        assert written["available_units"] == []
        assert written["pricing_model"] == "per_unit"
        # Fields the scrape didn't carry must not wipe what we hold.
        assert "parking_fee" not in written
        assert "specials" not in written

    async def test_one_bad_row_does_not_roll_back_the_rest(self, monkeypatch):
        from app.tasks.scrape_tasks import _update_reseen_listings

        log = _patch_sessions(monkeypatch, fail_ids={"existing-2"})
        dedup = DeduplicationService()
        updates = [
            dedup._build_reseen_update(_listing(), f"existing-{i}", f"hash-{i}")
            for i in (1, 2, 3)
        ]

        assert await _update_reseen_listings(updates) == 2
        assert [p["id_1"] for p in log] == ["existing-1", "existing-3"]
