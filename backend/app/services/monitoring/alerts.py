"""
Alert service for Snugd monitoring.
Sends alerts via Slack webhooks or email for critical events.
"""
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertService:
    """
    Service for sending alerts on important events.

    Supports:
    - Slack webhooks
    - Email (via SMTP or API)
    - Log-based alerts
    """

    def __init__(self):
        """Initialize the alert service."""
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.email_enabled = os.getenv("ALERT_EMAIL_ENABLED", "false").lower() == "true"
        self.email_to = os.getenv("ALERT_EMAIL_TO")
        self.email_from = os.getenv("ALERT_EMAIL_FROM", "alerts@snugd.app")

        self._http_client = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.INFO,
        source: str = "snugd",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send an alert through configured channels.

        Args:
            title: Alert title
            message: Alert message
            severity: Severity level
            source: Source of the alert
            metadata: Additional context

        Returns:
            True if alert was sent successfully
        """
        success = True

        # Always log
        log_method = getattr(logger, severity.value, logger.info)
        log_method(f"[ALERT] {title}: {message}")

        # Send to Slack
        if self.slack_webhook_url:
            slack_success = await self._send_slack_alert(
                title, message, severity, source, metadata
            )
            success = success and slack_success

        # Send email
        if self.email_enabled and self.email_to:
            email_success = await self._send_email_alert(
                title, message, severity, source, metadata
            )
            success = success and email_success

        return success

    async def _send_slack_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        source: str,
        metadata: Optional[Dict[str, Any]]
    ) -> bool:
        """Send alert to Slack."""
        try:
            # Map severity to color
            color_map = {
                AlertSeverity.INFO: "#36a64f",     # Green
                AlertSeverity.WARNING: "#ffcc00",  # Yellow
                AlertSeverity.ERROR: "#ff6600",    # Orange
                AlertSeverity.CRITICAL: "#ff0000", # Red
            }

            # Map severity to emoji
            emoji_map = {
                AlertSeverity.INFO: ":information_source:",
                AlertSeverity.WARNING: ":warning:",
                AlertSeverity.ERROR: ":x:",
                AlertSeverity.CRITICAL: ":rotating_light:",
            }

            # Build Slack message
            fields = [
                {"title": "Source", "value": source, "short": True},
                {"title": "Severity", "value": severity.value.upper(), "short": True},
            ]

            if metadata:
                for key, value in metadata.items():
                    fields.append({
                        "title": key,
                        "value": str(value),
                        "short": True
                    })

            payload = {
                "attachments": [
                    {
                        "color": color_map[severity],
                        "pretext": f"{emoji_map[severity]} *{title}*",
                        "text": message,
                        "fields": fields,
                        "footer": "Snugd Alerts",
                        "ts": int(datetime.utcnow().timestamp()),
                    }
                ]
            }

            response = await self.http_client.post(
                self.slack_webhook_url,
                json=payload
            )

            if response.status_code == 200:
                logger.debug(f"Slack alert sent: {title}")
                return True
            else:
                logger.warning(f"Slack alert failed: {response.status_code}")
                return False

        except Exception as e:
            logger.exception(f"Failed to send Slack alert: {e}")
            return False

    async def _send_email_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        source: str,
        metadata: Optional[Dict[str, Any]]
    ) -> bool:
        """Send alert via email."""
        # Email sending would require SMTP or a service like SendGrid/SES
        # For now, just log that we would send an email
        logger.info(f"Would send email alert to {self.email_to}: {title}")
        return True

    async def alert_scrape_failed(
        self,
        source: str,
        error_message: str,
        job_id: Optional[str] = None
    ):
        """Send alert for a failed scrape job."""
        await self.send_alert(
            title=f"Scrape Job Failed: {source}",
            message=error_message,
            severity=AlertSeverity.ERROR,
            source=source,
            metadata={"job_id": job_id} if job_id else None
        )

    async def alert_data_quality_low(
        self,
        source: str,
        avg_quality: float,
        threshold: float = 50.0
    ):
        """Send alert for low data quality."""
        if avg_quality < threshold:
            await self.send_alert(
                title=f"Low Data Quality: {source}",
                message=f"Average quality score is {avg_quality:.1f}%, below threshold of {threshold}%",
                severity=AlertSeverity.WARNING,
                source=source,
                metadata={"avg_quality": avg_quality, "threshold": threshold}
            )

    async def alert_rate_limit_exceeded(
        self,
        source: str,
        limit_type: str
    ):
        """Send alert for rate limit exceeded."""
        await self.send_alert(
            title=f"Rate Limit Exceeded: {source}",
            message=f"{limit_type.title()} rate limit exceeded for {source}",
            severity=AlertSeverity.WARNING,
            source=source,
            metadata={"limit_type": limit_type}
        )

    async def alert_database_error(
        self,
        error_message: str,
        operation: str
    ):
        """Send alert for database errors."""
        await self.send_alert(
            title="Database Error",
            message=error_message,
            severity=AlertSeverity.CRITICAL,
            source="database",
            metadata={"operation": operation}
        )

    async def alert_listings_stale(
        self,
        city: str,
        stale_count: int,
        days_old: int
    ):
        """Send alert for stale listings."""
        await self.send_alert(
            title=f"Stale Listings: {city}",
            message=f"{stale_count} listings not updated in {days_old} days",
            severity=AlertSeverity.WARNING,
            source="maintenance",
            metadata={"city": city, "count": stale_count, "days": days_old}
        )

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# Global alert service instance
_alert_service: Optional[AlertService] = None


def get_alert_service() -> AlertService:
    """Get or create the global alert service."""
    global _alert_service
    if _alert_service is None:
        _alert_service = AlertService()
    return _alert_service
