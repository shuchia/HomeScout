"""Celery tasks for recomputing true cost estimates."""
import logging
from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="recompute_true_costs", bind=True)
def recompute_true_costs(self):
    """Recompute true cost estimates for all active listings.

    Run this after updating cost_estimates.json or changing the
    estimation logic. Processes all active listings.
    """
    import asyncio
    from app.database import get_session_context
    from app.models.apartment import ApartmentModel
    from app.services.cost_estimator import CostEstimator
    from sqlalchemy import select

    estimator = CostEstimator()
    updated = 0

    async def _recompute():
        nonlocal updated
        async with get_session_context() as session:
            stmt = (
                select(ApartmentModel)
                .where(ApartmentModel.is_active == 1)
                .order_by(ApartmentModel.id)
            )
            result = await session.execute(stmt)
            apartments = result.scalars().all()

            for apt in apartments:
                scraped_fees = {
                    "pet_rent": apt.pet_rent,
                    "parking_fee": apt.parking_fee,
                    "amenity_fee": apt.amenity_fee,
                    "application_fee": apt.application_fee,
                    "security_deposit": apt.security_deposit,
                    "other_monthly_fees": apt.other_monthly_fees,
                }
                breakdown = estimator.compute_true_cost(
                    rent=apt.rent,
                    zip_code=apt.zip_code,
                    bedrooms=apt.bedrooms,
                    amenities=apt.amenities or [],
                    scraped_fees=scraped_fees,
                )
                apt.true_cost_monthly = breakdown["true_cost_monthly"]
                apt.true_cost_move_in = breakdown["true_cost_move_in"]
                apt.est_electric = breakdown["est_electric"]
                apt.est_gas = breakdown["est_gas"]
                apt.est_water = breakdown["est_water"]
                apt.est_internet = breakdown["est_internet"]
                apt.est_renters_insurance = breakdown["est_renters_insurance"]
                apt.est_laundry = breakdown["est_laundry"]
                apt.utilities_included = {
                    "heat": breakdown["est_gas"] == 0,
                    "water": breakdown["est_water"] == 0,
                    "electric": breakdown["est_electric"] == 0,
                }
                updated += 1

            await session.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_recompute())
    finally:
        loop.close()

    logger.info(f"Recomputed true costs for {updated} listings")
    return {"updated": updated}


@celery_app.task(name="backfill_fees", bind=True, soft_time_limit=600, time_limit=900)
def backfill_fees_task(self):
    """Re-extract fees from raw_data and recompute true costs for all listings.

    Use when fee extraction logic has been updated but existing listings
    were scraped with old code. Reads raw Apify data stored in each listing
    and re-runs fee extraction + cost computation.
    """
    import asyncio
    import json as _json
    from app.database import get_session_context
    from app.services.scrapers.apify_service import ApifyService
    from app.services.cost_estimator import CostEstimator
    from sqlalchemy import text

    svc = ApifyService()
    estimator = CostEstimator()
    updated = 0
    errors = 0

    async def _backfill():
        nonlocal updated, errors
        async with get_session_context() as session:
            r = await session.execute(text(
                "SELECT id, address, rent, bedrooms, zip_code, raw_data, amenities, source "
                "FROM apartments WHERE is_active = 1 AND raw_data IS NOT NULL"
            ))
            rows = r.fetchall()
            logger.info(f"Backfill: processing {len(rows)} listings")

            for row in rows:
                apt_id, address, rent, bedrooms, zip_code, raw_data, amenities, source = row
                try:
                    raw = raw_data if isinstance(raw_data, dict) else _json.loads(raw_data)
                    if source != "apartments_com":
                        continue
                    listing = svc._normalize_apartments_com_listing(raw)
                    if not listing:
                        continue

                    scraped_fees = {
                        "pet_rent": listing.pet_rent,
                        "parking_fee": listing.parking_fee,
                        "amenity_fee": listing.amenity_fee,
                        "application_fee": listing.application_fee,
                        "admin_fee": listing.admin_fee,
                        "security_deposit": listing.security_deposit,
                        "other_monthly_fees": listing.other_monthly_fees,
                    }
                    cost = estimator.compute_true_cost(
                        rent=rent, zip_code=zip_code, bedrooms=bedrooms,
                        amenities=listing.amenities or amenities or [],
                        scraped_fees=scraped_fees,
                    )
                    utilities_included = {
                        "heat": cost["est_gas"] == 0,
                        "water": cost["est_water"] == 0,
                        "electric": cost["est_electric"] == 0,
                    }

                    await session.execute(text("""
                        UPDATE apartments SET
                            pet_rent = :pet_rent, parking_fee = :parking_fee,
                            amenity_fee = :amenity_fee, application_fee = :application_fee,
                            admin_fee = :admin_fee, security_deposit = :security_deposit,
                            other_monthly_fees = :other_monthly_fees,
                            est_electric = :est_electric, est_gas = :est_gas,
                            est_water = :est_water, est_internet = :est_internet,
                            est_renters_insurance = :est_renters_insurance,
                            est_laundry = :est_laundry,
                            utilities_included = :utilities_included,
                            true_cost_monthly = :true_cost_monthly,
                            true_cost_move_in = :true_cost_move_in
                        WHERE id = :id
                    """), {
                        "id": apt_id,
                        "pet_rent": listing.pet_rent, "parking_fee": listing.parking_fee,
                        "amenity_fee": listing.amenity_fee, "application_fee": listing.application_fee,
                        "admin_fee": listing.admin_fee, "security_deposit": listing.security_deposit,
                        "other_monthly_fees": listing.other_monthly_fees,
                        "est_electric": cost["est_electric"], "est_gas": cost["est_gas"],
                        "est_water": cost["est_water"], "est_internet": cost["est_internet"],
                        "est_renters_insurance": cost["est_renters_insurance"],
                        "est_laundry": cost["est_laundry"],
                        "utilities_included": _json.dumps(utilities_included),
                        "true_cost_monthly": cost["true_cost_monthly"],
                        "true_cost_move_in": cost["true_cost_move_in"],
                    })
                    updated += 1
                except Exception as e:
                    errors += 1
                    logger.warning(f"Backfill error for {address}: {e}")

            await session.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_backfill())
    finally:
        loop.close()

    logger.info(f"Backfill complete: {updated} updated, {errors} errors")
    return {"updated": updated, "errors": errors}
