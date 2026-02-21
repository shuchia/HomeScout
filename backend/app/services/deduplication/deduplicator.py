"""
Deduplication service for apartment listings.
Uses content hashing and fuzzy address matching.
"""
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from app.services.normalization.address_standardizer import AddressStandardizer

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
    """Result of deduplication check."""
    is_duplicate: bool
    content_hash: str
    matched_id: Optional[str] = None
    match_reason: Optional[str] = None
    similarity_score: float = 0.0


class DeduplicationService:
    """
    Service for detecting and handling duplicate apartment listings.

    Uses two methods:
    1. Content hash - SHA256 of normalized address + rent + beds/baths
    2. Fuzzy matching - Address similarity > 90% with same rent/beds

    Deduplication strategy:
    - Keep the listing with highest data quality score
    - Merge unique data from duplicates (e.g., additional images)
    """

    def __init__(self):
        """Initialize the deduplication service."""
        self.address_standardizer = AddressStandardizer()

    def generate_content_hash(self, listing: Dict[str, Any]) -> str:
        """
        Generate a content hash for a listing.

        Hash is based on:
        - Normalized address
        - Rent (rounded to nearest $50)
        - Bedrooms
        - Bathrooms

        Args:
            listing: Listing data dictionary

        Returns:
            SHA256 hash string
        """
        # Get normalized address
        address = listing.get("address_normalized") or listing.get("address", "")
        address_key = self.address_standardizer.get_address_key(address)

        # Round rent to reduce minor price differences
        rent = listing.get("rent", 0)
        rent_rounded = (rent // 50) * 50

        # Build hash content
        content = f"{address_key}|{rent_rounded}|{listing.get('bedrooms', 0)}|{listing.get('bathrooms', 0)}"

        # Generate SHA256 hash
        return hashlib.sha256(content.encode()).hexdigest()

    def check_duplicate(
        self,
        listing: Dict[str, Any],
        existing_hashes: Dict[str, str],
        existing_listings: Optional[List[Dict[str, Any]]] = None
    ) -> DeduplicationResult:
        """
        Check if a listing is a duplicate.

        Args:
            listing: Listing to check
            existing_hashes: Map of content_hash -> listing_id
            existing_listings: Optional list of existing listings for fuzzy matching

        Returns:
            DeduplicationResult
        """
        content_hash = self.generate_content_hash(listing)

        # Check exact hash match
        if content_hash in existing_hashes:
            return DeduplicationResult(
                is_duplicate=True,
                content_hash=content_hash,
                matched_id=existing_hashes[content_hash],
                match_reason="exact_hash",
                similarity_score=1.0,
            )

        # Check fuzzy address match if existing listings provided
        if existing_listings:
            match = self._find_fuzzy_match(listing, existing_listings)
            if match:
                return DeduplicationResult(
                    is_duplicate=True,
                    content_hash=content_hash,
                    matched_id=match[0],
                    match_reason="fuzzy_address",
                    similarity_score=match[1],
                )

        return DeduplicationResult(
            is_duplicate=False,
            content_hash=content_hash,
        )

    def _find_fuzzy_match(
        self,
        listing: Dict[str, Any],
        existing_listings: List[Dict[str, Any]],
        address_threshold: float = 0.9
    ) -> Optional[Tuple[str, float]]:
        """
        Find a fuzzy match for a listing based on address similarity.

        Args:
            listing: Listing to check
            existing_listings: Existing listings to compare against
            address_threshold: Minimum address similarity (0.0 to 1.0)

        Returns:
            Tuple of (matched_id, similarity_score) or None
        """
        listing_address = listing.get("address_normalized") or listing.get("address", "")
        listing_rent = listing.get("rent", 0)
        listing_beds = listing.get("bedrooms", 0)

        for existing in existing_listings:
            # Quick filters first
            existing_rent = existing.get("rent", 0)
            existing_beds = existing.get("bedrooms", 0)

            # Rent must be within 10%
            if abs(listing_rent - existing_rent) > listing_rent * 0.1:
                continue

            # Bedrooms must match
            if listing_beds != existing_beds:
                continue

            # Check address similarity
            existing_address = existing.get("address_normalized") or existing.get("address", "")
            if self.address_standardizer.addresses_match(
                listing_address, existing_address, address_threshold
            ):
                similarity = self._calculate_similarity(listing_address, existing_address)
                return (existing.get("id"), similarity)

        return None

    def _calculate_similarity(self, addr1: str, addr2: str) -> float:
        """Calculate similarity between two addresses."""
        key1 = self.address_standardizer.get_address_key(addr1)
        key2 = self.address_standardizer.get_address_key(addr2)

        if key1 == key2:
            return 1.0

        try:
            from fuzzywuzzy import fuzz
            return fuzz.ratio(key1, key2) / 100.0
        except ImportError:
            # Simple word overlap
            words1 = set(key1.split())
            words2 = set(key2.split())
            if not words1 or not words2:
                return 0.0
            overlap = len(words1 & words2)
            total = len(words1 | words2)
            return overlap / total

    def merge_listings(
        self,
        primary: Dict[str, Any],
        secondary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge two duplicate listings, keeping the best data from each.

        Args:
            primary: Primary listing (higher quality)
            secondary: Secondary listing to merge from

        Returns:
            Merged listing data
        """
        merged = primary.copy()

        # Merge images (deduplicated)
        primary_images = set(primary.get("images", []))
        secondary_images = set(secondary.get("images", []))
        merged["images"] = list(primary_images | secondary_images)

        # Merge amenities (deduplicated)
        primary_amenities = set(a.lower() for a in primary.get("amenities", []))
        secondary_amenities = set(a.lower() for a in secondary.get("amenities", []))
        all_amenities = primary_amenities | secondary_amenities
        merged["amenities"] = [a.title() for a in sorted(all_amenities)]

        # Use longer description
        if len(secondary.get("description", "") or "") > len(primary.get("description", "") or ""):
            merged["description"] = secondary["description"]

        # Fill in missing fields from secondary
        for field in ["sqft", "latitude", "longitude", "neighborhood", "available_date"]:
            if not merged.get(field) and secondary.get(field):
                merged[field] = secondary[field]

        # Update quality score
        merged["data_quality_score"] = max(
            primary.get("data_quality_score", 0),
            secondary.get("data_quality_score", 0)
        )

        return merged

    def deduplicate_batch(
        self,
        listings: List[Dict[str, Any]],
        existing_hashes: Optional[Dict[str, str]] = None,
        existing_listings: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
        """
        Deduplicate a batch of listings.

        Args:
            listings: List of listings to deduplicate
            existing_hashes: Existing content hashes from database
            existing_listings: Existing listings for fuzzy matching

        Returns:
            Tuple of (unique_listings, duplicates, merge_count)
        """
        existing_hashes = existing_hashes or {}
        existing_listings = existing_listings or []

        unique = []
        duplicates = []
        merge_count = 0

        # Track hashes within this batch
        batch_hashes: Dict[str, int] = {}

        for i, listing in enumerate(listings):
            # Check against existing data
            result = self.check_duplicate(listing, existing_hashes, existing_listings)

            if result.is_duplicate:
                duplicates.append({
                    "listing": listing,
                    "matched_id": result.matched_id,
                    "reason": result.match_reason,
                    "similarity": result.similarity_score,
                })
                continue

            # Check against this batch
            if result.content_hash in batch_hashes:
                # Merge with existing in batch
                idx = batch_hashes[result.content_hash]
                unique[idx] = self.merge_listings(unique[idx], listing)
                merge_count += 1
                duplicates.append({
                    "listing": listing,
                    "matched_id": unique[idx].get("id"),
                    "reason": "batch_duplicate",
                    "similarity": 1.0,
                })
            else:
                # Add content hash to listing
                listing["content_hash"] = result.content_hash
                batch_hashes[result.content_hash] = len(unique)
                unique.append(listing)

        logger.info(
            f"Deduplicated batch: {len(listings)} input, "
            f"{len(unique)} unique, {len(duplicates)} duplicates, "
            f"{merge_count} merged"
        )

        return unique, duplicates, merge_count

    def deduplicate_batch_with_updates(
        self,
        listings: List[Dict[str, Any]],
        existing_hashes: Dict[str, str],
        existing_listings: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Deduplicate a batch, returning new listings, updates for re-seen, and skipped duplicates.

        Unlike deduplicate_batch(), this separates duplicates into:
        - updates: re-seen listings that should have their confidence reset
        - skipped: true duplicates within the same batch

        Args:
            listings: New listings to check
            existing_hashes: Map of content_hash -> listing_id from DB
            existing_listings: Existing listings for fuzzy matching

        Returns:
            Tuple of (new_listings, updates_to_existing, skipped_duplicates)
        """
        new_listings = []
        updates = []
        skipped = []
        batch_hashes = {}  # Track hashes within this batch

        for listing in listings:
            content_hash = self.generate_content_hash(listing)
            listing["content_hash"] = content_hash

            # Check against existing DB data
            if content_hash in existing_hashes:
                updates.append({
                    "matched_id": existing_hashes[content_hash],
                    "content_hash": content_hash,
                    "images": listing.get("images", []),
                    "description": listing.get("description", ""),
                })
                continue

            # Check fuzzy match against existing
            if existing_listings:
                dup_result = self.check_duplicate(listing, existing_hashes, existing_listings)
                if dup_result.is_duplicate and dup_result.matched_id:
                    updates.append({
                        "matched_id": dup_result.matched_id,
                        "content_hash": content_hash,
                        "images": listing.get("images", []),
                        "description": listing.get("description", ""),
                    })
                    continue

            # Check within this batch
            if content_hash in batch_hashes:
                skipped.append(listing)
                continue

            batch_hashes[content_hash] = True
            new_listings.append(listing)

        logger.info(
            f"Dedup batch: {len(listings)} input → "
            f"{len(new_listings)} new, {len(updates)} re-seen, {len(skipped)} skipped"
        )
        return new_listings, updates, skipped
