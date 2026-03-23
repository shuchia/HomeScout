"""
Prometheus metrics service for Snugd.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Check if prometheus_client is available
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.info("prometheus_client not installed - metrics disabled")


class MetricsService:
    """
    Service for collecting and exposing Prometheus metrics.

    Metrics tracked:
    - Scrape job counts (by source, status)
    - Listing counts (by source, city)
    - Scrape duration
    - API request counts and latency
    - Error counts
    """

    def __init__(self):
        """Initialize metrics."""
        self._initialized = False

        if not PROMETHEUS_AVAILABLE:
            return

        # Scraping metrics
        self.scrape_jobs_total = Counter(
            "snugd_scrape_jobs_total",
            "Total number of scrape jobs",
            ["source", "status"]
        )

        self.scrape_duration_seconds = Histogram(
            "snugd_scrape_duration_seconds",
            "Time spent on scrape jobs",
            ["source"],
            buckets=[10, 30, 60, 120, 300, 600, 1800]
        )

        self.listings_scraped_total = Counter(
            "snugd_listings_scraped_total",
            "Total listings scraped",
            ["source"]
        )

        self.listings_new_total = Counter(
            "snugd_listings_new_total",
            "New listings added",
            ["source"]
        )

        self.listings_duplicates_total = Counter(
            "snugd_listings_duplicates_total",
            "Duplicate listings detected",
            ["source"]
        )

        # Database metrics
        self.listings_active = Gauge(
            "snugd_listings_active",
            "Number of active listings",
            ["city"]
        )

        self.listings_total = Gauge(
            "snugd_listings_total",
            "Total number of listings"
        )

        self.data_quality_score = Gauge(
            "snugd_data_quality_score_avg",
            "Average data quality score"
        )

        # API metrics
        self.api_requests_total = Counter(
            "snugd_api_requests_total",
            "Total API requests",
            ["endpoint", "method", "status"]
        )

        self.api_request_duration_seconds = Histogram(
            "snugd_api_request_duration_seconds",
            "API request latency",
            ["endpoint"],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
        )

        # Error metrics
        self.errors_total = Counter(
            "snugd_errors_total",
            "Total errors",
            ["type", "source"]
        )

        self._initialized = True
        logger.info("Prometheus metrics initialized")

    def record_scrape_job(
        self,
        source: str,
        status: str,
        duration_seconds: float,
        listings_found: int,
        listings_new: int,
        listings_duplicates: int
    ):
        """Record metrics for a completed scrape job."""
        if not self._initialized:
            return

        self.scrape_jobs_total.labels(source=source, status=status).inc()
        self.scrape_duration_seconds.labels(source=source).observe(duration_seconds)
        self.listings_scraped_total.labels(source=source).inc(listings_found)
        self.listings_new_total.labels(source=source).inc(listings_new)
        self.listings_duplicates_total.labels(source=source).inc(listings_duplicates)

    def record_api_request(
        self,
        endpoint: str,
        method: str,
        status: int,
        duration_seconds: float
    ):
        """Record metrics for an API request."""
        if not self._initialized:
            return

        status_class = f"{status // 100}xx"
        self.api_requests_total.labels(
            endpoint=endpoint,
            method=method,
            status=status_class
        ).inc()
        self.api_request_duration_seconds.labels(endpoint=endpoint).observe(duration_seconds)

    def record_error(self, error_type: str, source: str = "unknown"):
        """Record an error occurrence."""
        if not self._initialized:
            return

        self.errors_total.labels(type=error_type, source=source).inc()

    def update_listing_counts(self, total: int, by_city: dict):
        """Update current listing counts."""
        if not self._initialized:
            return

        self.listings_total.set(total)
        for city, count in by_city.items():
            self.listings_active.labels(city=city).set(count)

    def update_quality_score(self, avg_score: float):
        """Update average data quality score."""
        if not self._initialized:
            return

        self.data_quality_score.set(avg_score)

    def get_metrics(self) -> Optional[bytes]:
        """
        Get current metrics in Prometheus format.

        Returns:
            Metrics data as bytes, or None if unavailable
        """
        if not PROMETHEUS_AVAILABLE:
            return None

        return generate_latest()

    def get_content_type(self) -> str:
        """Get content type for metrics endpoint."""
        if PROMETHEUS_AVAILABLE:
            return CONTENT_TYPE_LATEST
        return "text/plain"


# Global metrics instance
_metrics_service: Optional[MetricsService] = None


def get_metrics_service() -> MetricsService:
    """Get or create the global metrics service."""
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService()
    return _metrics_service
