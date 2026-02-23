"""Tests for daily email alert task."""
from unittest.mock import patch, MagicMock

from app.tasks.alert_tasks import send_daily_alerts


SAMPLE_SEARCH = {
    "id": "ss-001",
    "user_id": "user-123",
    "name": "Pittsburgh 2BR",
    "city": "Pittsburgh",
    "budget": 2000,
    "bedrooms": 2,
    "bathrooms": 1,
    "property_type": "Apartment",
    "is_active": True,
    "notify_new_matches": True,
    "last_alerted_at": None,
    "profiles": {
        "user_tier": "pro",
        "email": "jane@example.com",
        "name": "Jane",
    },
}

SAMPLE_APARTMENT = {
    "id": "apt-001",
    "address": "123 Main St, Pittsburgh, PA",
    "rent": 1800,
    "bedrooms": 2,
    "bathrooms": 1,
    "first_seen_at": "2026-02-22T00:00:00+00:00",
}


class TestSendDailyAlertsNoSearches:
    """When no saved searches found, returns sent: 0."""

    def test_no_supabase_client(self):
        """Returns 0 when supabase_admin is None."""
        with patch("app.services.tier_service.supabase_admin", None):
            result = send_daily_alerts()
        assert result == {"sent": 0}

    def test_empty_result(self):
        """Returns 0 when query returns no rows."""
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        with patch("app.services.tier_service.supabase_admin", mock_sb):
            result = send_daily_alerts()
        assert result == {"sent": 0}


class TestSendDailyAlertsWithMatches:
    """When searches exist with matching apartments, sends email and updates last_alerted_at."""

    def test_sends_email_and_updates(self):
        mock_sb = MagicMock()
        # Query returns one saved search
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[SAMPLE_SEARCH]
        )
        # Update call chain
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])

        mock_service = MagicMock()
        mock_service.search_apartments.return_value = [SAMPLE_APARTMENT]

        mock_resend = MagicMock()

        with (
            patch("app.services.tier_service.supabase_admin", mock_sb),
            patch("app.services.apartment_service.ApartmentService", return_value=mock_service),
            patch("app.tasks.alert_tasks.resend.Emails.send", mock_resend),
        ):
            result = send_daily_alerts()

        assert result == {"sent": 1}

        # Verify email was sent
        mock_resend.assert_called_once()
        call_args = mock_resend.call_args[0][0]
        assert call_args["to"] == "jane@example.com"
        assert "Pittsburgh" in call_args["subject"]
        assert "123 Main St" in call_args["text"]

        # Verify last_alerted_at was updated
        mock_sb.table.return_value.update.assert_called_once()


class TestSendDailyAlertsFiltering:
    """When no new apartments since last_alerted_at, skips sending."""

    def test_skips_when_no_new_apartments(self):
        search_with_recent_alert = {
            **SAMPLE_SEARCH,
            "last_alerted_at": "2026-02-23T00:00:00+00:00",  # After apartment first_seen_at
        }

        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[search_with_recent_alert]
        )

        mock_service = MagicMock()
        # Apartment was first seen before last_alerted_at, so it should be filtered out
        mock_service.search_apartments.return_value = [SAMPLE_APARTMENT]

        mock_resend = MagicMock()

        with (
            patch("app.services.tier_service.supabase_admin", mock_sb),
            patch("app.services.apartment_service.ApartmentService", return_value=mock_service),
            patch("app.tasks.alert_tasks.resend.Emails.send", mock_resend),
        ):
            result = send_daily_alerts()

        assert result == {"sent": 0}
        mock_resend.assert_not_called()


class TestSendDailyAlertsResendFailure:
    """When resend fails, logs error and continues to next search."""

    def test_continues_on_failure(self):
        search2 = {**SAMPLE_SEARCH, "id": "ss-002", "profiles": {
            "user_tier": "pro", "email": "bob@example.com", "name": "Bob",
        }}

        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[SAMPLE_SEARCH, search2]
        )
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])

        mock_service = MagicMock()
        mock_service.search_apartments.return_value = [SAMPLE_APARTMENT]

        # First call raises, second succeeds
        mock_resend = MagicMock(side_effect=[Exception("API error"), None])

        with (
            patch("app.services.tier_service.supabase_admin", mock_sb),
            patch("app.services.apartment_service.ApartmentService", return_value=mock_service),
            patch("app.tasks.alert_tasks.resend.Emails.send", mock_resend),
        ):
            result = send_daily_alerts()

        # Only the second search succeeded
        assert result == {"sent": 1}
        assert mock_resend.call_count == 2
