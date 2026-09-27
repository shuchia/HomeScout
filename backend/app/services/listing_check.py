"""Check a saved listing against its source.

Search runs off the scraped corpus, which is swept weekly, so a search result
can be up to a week old. Measured churn is a median 6% of a market's listings
per week counting new arrivals alone — price moves and withdrawals are on top
of that. Keeping the whole corpus fresh enough to close that gap would mean
scraping constantly; instead we check a single listing at the moment the user
commits to it, which costs about $0.0005 and takes 10-20 seconds.

"Commits to it" means favouriting, adding to a comparison, or adding to the
tour pipeline. Those are the points where a stale number stops being a browsing
inconvenience and starts being something the product asserted: a true-cost
figure, a comparison ranking, a decision brief, an inquiry email quoting a rent
to a landlord.

Checking stops once a decision is recorded. A listing the user applied for or
passed on should keep the state it was decided on rather than drifting
afterwards.
"""
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Fields worth telling the user about. Deliberately short: a changed
# description or a reshuffled image list is noise, a changed rent is not.
_MATERIAL_FIELDS = (
    "rent",
    "true_cost_monthly",
    "true_cost_move_in",
    "available_date",
    "bedrooms",
    "bathrooms",
    "sqft",
)

# Result of a check, in the shape saved_listings expects.
LIVE = "live"
GONE = "gone"
UNKNOWN = "unknown"


def diff_listing(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Material changes between two versions of a listing.

    Returns {field: {"from": old, "to": new}}, empty when nothing material
    moved. This is also the record we keep: `listing` is overwritten by each
    check, so without logging the diff the fact that a price ever moved is lost
    (see the note in migration 011 about listing_as_saved).
    """
    changes: Dict[str, Dict[str, Any]] = {}
    for field in _MATERIAL_FIELDS:
        old = before.get(field)
        new = after.get(field)
        if old == new:
            continue
        # Treat absent and empty as the same thing, so a field the scrape
        # simply didn't populate this time doesn't read as a change.
        if old in (None, "", 0) and new in (None, "", 0):
            continue
        changes[field] = {"from": old, "to": new}
    return changes


async def check_listing(
    source_url: Optional[str],
    current: Dict[str, Any],
) -> Tuple[str, Optional[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Fetch a listing from its source and compare it to what we hold.

    Returns (availability_status, fresh_listing_or_None, changes).

    A failed fetch returns UNKNOWN and leaves the caller holding what it had.
    That distinction matters: apartments.com is Akamai-fenced and blocks direct
    HTTP, which is exactly how the old corpus-wide verification ended up
    certifying every listing as alive because it was being refused. Going
    through the scraper is the only route that can actually answer, and when it
    can't answer we say so rather than guessing in either direction.
    """
    if not source_url:
        return UNKNOWN, None, {}

    from app.services.scrapers.apify_service import ApifyService

    scraper = ApifyService("apartments_com")
    try:
        result = await scraper.scrape_url(source_url)
    except Exception as e:
        logger.warning(f"Listing check failed for {source_url}: {e}")
        return UNKNOWN, None, {}
    finally:
        try:
            await scraper.close()
        except Exception:
            pass

    if result.status.value == "failed":
        logger.warning(f"Listing check errored for {source_url}: {result.errors}")
        return UNKNOWN, None, {}

    if not result.listings:
        # The actor ran and found nothing at a well-formed listing URL. That is
        # good evidence the listing has been taken down.
        return GONE, None, {}

    # Put it through the same normalizer the scrape pipeline uses, so the check
    # and the corpus agree on field names, units and how true cost is derived.
    # A ScrapedListing is not the shape stored in saved_listings.listing —
    # that is ApartmentModel.to_dict() — so it cannot be written through raw.
    from app.services.normalization.normalizer import NormalizationService

    norm = NormalizationService().normalize(result.listings[0])
    if not norm.success or not norm.listing:
        logger.warning(f"Listing check normalization failed for {source_url}: {norm.errors}")
        return UNKNOWN, None, {}

    # Patch only the volatile fields rather than replacing the stored listing.
    # The normalizer's output and ApartmentModel.to_dict() overlap but are not
    # identical — to_dict() carries derived display fields (beds_label,
    # baths_label) and prefers cached image URLs — so a wholesale swap would
    # quietly drop things the UI depends on. The check exists to answer "is it
    # still there and did the numbers move", and those are the numbers.
    updated = dict(current)
    for field in _MATERIAL_FIELDS:
        value = norm.listing.get(field)
        if value not in (None, "", [], {}):
            updated[field] = value

    return LIVE, updated, diff_listing(current, updated)
