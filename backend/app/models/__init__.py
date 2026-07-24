"""
ORM models for Snugd database.
"""
from app.models.apartment import ApartmentModel
from app.models.apartment_floorplan import ApartmentFloorplanModel
from app.models.scrape_job import ScrapeJobModel
from app.models.data_source import DataSourceModel
from app.models.market_config import MarketConfigModel

__all__ = [
    "ApartmentModel",
    "ApartmentFloorplanModel",
    "ScrapeJobModel",
    "DataSourceModel",
    "MarketConfigModel",
]
