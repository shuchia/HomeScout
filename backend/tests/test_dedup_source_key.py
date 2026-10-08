"""Deduplication on the source's own listing id.

The content hash and the fuzzy matcher both key on *rent*, so a building whose
advertised headline price moves far enough is inserted as a brand new row. The
source id does not move.

Measured on QA 2026-10-03: 583 of 3,737 rows (15.6%) were repeat captures of a
property already in the corpus — every market between 12.7% and 26%,
accumulating over a median 50 days between first and last capture. 235 Old
Colony was in twice under property id j5ve2k4, its URL slug having changed from
`south-standard` to `south-standard-boston-ma`.
"""
from app.services.deduplication.deduplicator import DeduplicationService, source_key


class TestSourceKey:
    def test_prefers_external_id(self):
        assert source_key({
            "source": "apartments_com",
            "external_id": "j5ve2k4",
            "source_url": "https://www.apartments.com/south-standard/j5ve2k4/",
        }) == "apartments_com:j5ve2k4"

    def test_falls_back_to_url_token(self):
        """external_id was written but never read, so it may be absent on old
        rows; the URL carries the same id."""
        assert source_key({
            "source": "apartments_com",
            "source_url": "https://www.apartments.com/south-standard/j5ve2k4/",
        }) == "apartments_com:j5ve2k4"

    def test_slug_change_yields_the_same_key(self):
        """The exact 235 Old Colony case."""
        a = source_key({"source": "apartments_com",
                        "source_url": "https://www.apartments.com/south-standard/j5ve2k4/"})
        b = source_key({"source": "apartments_com",
                        "source_url": "https://www.apartments.com/south-standard-boston-ma/j5ve2k4/"})
        assert a == b

    def test_query_string_ignored(self):
        assert source_key({
            "source": "apartments_com",
            "source_url": "https://www.apartments.com/x/j5ve2k4/?utm_source=z",
        }) == "apartments_com:j5ve2k4"

    def test_distinct_properties_stay_distinct(self):
        """9 Hancock St has three by-the-room listings at one address, each
        with its own property id. They must NOT collapse."""
        ids = {source_key({"source": "apartments_com",
                           "source_url": f"https://www.apartments.com/x/{i}/"})
               for i in ("vyjj1df", "xctkzwn", "b48qnwb")}
        assert len(ids) == 3

    def test_sources_are_namespaced(self):
        assert source_key({"source": "zillow", "external_id": "123"}) != \
               source_key({"source": "apartments_com", "external_id": "123"})

    def test_returns_none_without_signal(self):
        assert source_key({"source": "apartments_com"}) is None
        assert source_key({"external_id": "abc"}) is None
        assert source_key({}) is None


class TestDedupUsesSourceKey:
    def _listing(self, rent, url="https://www.apartments.com/south-standard/j5ve2k4/"):
        return {
            "source": "apartments_com",
            "source_url": url,
            "address": "235 Old Colony Ave, Boston, MA 02127",
            "address_normalized": "235 old colony ave boston ma 02127",
            "rent": rent,
            "bedrooms": 0,
            "bathrooms": 1,
        }

    def test_price_move_past_the_fuzzy_window_is_still_the_same_listing(self):
        """A 36% move clears both the $50 hash bucket and the 10% fuzzy window.
        Before this check, that inserted a second row for one property."""
        svc = DeduplicationService()
        existing = {"apartments_com:j5ve2k4": "row-1"}
        r = svc.check_duplicate(self._listing(3410), {}, [], existing)
        assert r.is_duplicate
        assert r.matched_id == "row-1"
        assert r.match_reason == "source_key"

    def test_slug_change_is_not_a_new_listing(self):
        svc = DeduplicationService()
        existing = {"apartments_com:j5ve2k4": "row-1"}
        r = svc.check_duplicate(
            self._listing(3290, "https://www.apartments.com/south-standard-boston-ma/j5ve2k4/"),
            {}, [], existing,
        )
        assert r.is_duplicate and r.matched_id == "row-1"

    def test_unknown_property_is_new(self):
        svc = DeduplicationService()
        r = svc.check_duplicate(
            self._listing(3290, "https://www.apartments.com/other/zzzzzzz/"),
            {}, [], {"apartments_com:j5ve2k4": "row-1"},
        )
        assert not r.is_duplicate

    def test_batch_routes_a_reseen_property_to_update_not_insert(self):
        svc = DeduplicationService()
        new, updates, skipped = svc.deduplicate_batch_with_updates(
            [self._listing(3410)], {}, [], {"apartments_com:j5ve2k4": "row-1"},
        )
        assert new == [] and skipped == []
        assert len(updates) == 1 and updates[0]["matched_id"] == "row-1"

    def test_batch_collapses_a_property_repeated_within_one_scrape(self):
        svc = DeduplicationService()
        new, updates, skipped = svc.deduplicate_batch_with_updates(
            [self._listing(3290), self._listing(3410)], {}, [], {},
        )
        assert len(new) == 1
        assert len(skipped) == 1

    def test_absent_source_keys_preserve_old_behaviour(self):
        """Callers that pass nothing must behave exactly as before."""
        svc = DeduplicationService()
        new, updates, skipped = svc.deduplicate_batch_with_updates(
            [self._listing(3290)], {}, [],
        )
        assert len(new) == 1 and not updates and not skipped
