"""
Backfill fee fields for existing apartments from their raw_data.

Run with:
    cd backend && source .venv/bin/activate && python scripts/backfill_fees.py
"""
import asyncio
import json
import logging
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import _get_session_maker
from app.services.scrapers.apify_service import ApifyService
from app.services.normalization.normalizer import NormalizationService
from app.services.pricing_model_detector import detect_pricing_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def backfill():
    from sqlalchemy import text

    session_maker = _get_session_maker()
    svc = ApifyService()
    normalizer = NormalizationService()

    async with session_maker() as session:
        # Get all active listings with raw_data
        r = await session.execute(text(
            "SELECT id, address, rent, bedrooms, zip_code, raw_data, amenities, source "
            "FROM apartments WHERE is_active = 1 AND raw_data IS NOT NULL"
        ))
        rows = r.fetchall()
        logger.info(f"Found {len(rows)} listings to backfill")

        updated = 0
        skipped = 0
        errors = 0

        for row in rows:
            apt_id, address, rent, bedrooms, zip_code, raw_data, amenities, source = row
            try:
                raw = raw_data if isinstance(raw_data, dict) else json.loads(raw_data)

                # Re-extract fees from raw data using the fixed scraper
                if source == "apartments_com":
                    listing = svc._normalize_apartments_com_listing(raw)
                else:
                    skipped += 1
                    continue

                if not listing:
                    skipped += 1
                    continue

                # Compute true cost using normalizer's cost estimator
                scraped_fees = {
                    "pet_rent": listing.pet_rent,
                    "parking_fee": listing.parking_fee,
                    "amenity_fee": listing.amenity_fee,
                    "application_fee": listing.application_fee,
                    "admin_fee": listing.admin_fee,
                    "security_deposit": listing.security_deposit,
                    "other_monthly_fees": listing.other_monthly_fees,
                }

                cost = normalizer.cost_estimator.compute_true_cost(
                    rent=rent,
                    zip_code=zip_code,
                    bedrooms=bedrooms,
                    amenities=listing.amenities or amenities or [],
                    scraped_fees=scraped_fees,
                )

                utilities_included = {
                    "heat": cost["est_gas"] == 0,
                    "water": cost["est_water"] == 0,
                    "electric": cost["est_electric"] == 0,
                }

                detection = detect_pricing_model(
                    description=listing.description or "",
                    bedrooms=bedrooms,
                    bathrooms=float(listing.bathrooms),
                    rent=rent,
                    city=listing.city or "",
                )

                await session.execute(text("""
                    UPDATE apartments SET
                        pet_rent = :pet_rent,
                        parking_fee = :parking_fee,
                        amenity_fee = :amenity_fee,
                        application_fee = :application_fee,
                        admin_fee = :admin_fee,
                        security_deposit = :security_deposit,
                        other_monthly_fees = :other_monthly_fees,
                        est_electric = :est_electric,
                        est_gas = :est_gas,
                        est_water = :est_water,
                        est_internet = :est_internet,
                        est_renters_insurance = :est_renters_insurance,
                        est_laundry = :est_laundry,
                        utilities_included = :utilities_included,
                        true_cost_monthly = :true_cost_monthly,
                        true_cost_move_in = :true_cost_move_in,
                        pricing_model = :pricing_model,
                        pricing_model_confidence = :pricing_model_confidence
                    WHERE id = :id
                """), {
                    "id": apt_id,
                    "pet_rent": listing.pet_rent,
                    "parking_fee": listing.parking_fee,
                    "amenity_fee": listing.amenity_fee,
                    "application_fee": listing.application_fee,
                    "admin_fee": listing.admin_fee,
                    "security_deposit": listing.security_deposit,
                    "other_monthly_fees": listing.other_monthly_fees,
                    "est_electric": cost["est_electric"],
                    "est_gas": cost["est_gas"],
                    "est_water": cost["est_water"],
                    "est_internet": cost["est_internet"],
                    "est_renters_insurance": cost["est_renters_insurance"],
                    "est_laundry": cost["est_laundry"],
                    "utilities_included": json.dumps(utilities_included),
                    "true_cost_monthly": cost["true_cost_monthly"],
                    "true_cost_move_in": cost["true_cost_move_in"],
                    "pricing_model": detection["pricing_model"],
                    "pricing_model_confidence": detection["confidence"],
                })
                updated += 1

            except Exception as e:
                errors += 1
                logger.warning(f"Error backfilling {address}: {e}")

        await session.commit()
        logger.info(f"Backfill complete: {updated} updated, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    asyncio.run(backfill())
