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
