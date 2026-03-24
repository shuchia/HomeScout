"""Tests for tour reminder notification task."""
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta, time as dt_time

from app.tasks.tour_reminder_tasks import check_tour_reminders


# Use a fixed "now" at noon UTC to avoid midnight-crossing issues
FIXED_NOW = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc)
FIXED_TODAY = FIXED_NOW.date().isoformat()  # "2026-03-23"


def _make_tour(tour_id, user_id, apartment_id, scheduled_time):
    return {
        "id": tour_id,
        "user_id": user_id,
        "apartment_id": apartment_id,
        "scheduled_date": FIXED_TODAY,
        "scheduled_time": scheduled_time,
    }


class TestCheckTourReminders:
    """Tests for the check_tour_reminders Celery task."""

    def test_creates_reminder_for_recent_tour(self):
        """Should create a notification for a tour that ended ~30 min ago."""
        tour_time = (FIXED_NOW - timedelta(minutes=30)).strftime("%H:%M")
        tour = _make_tour("tour-1", "user-1", "apt-1", tour_time)

        mock_sb = MagicMock()
        call_count = {"tour_pipeline": 0, "notifications": 0}

        def table_side_effect(name):
            call_count[name] = call_count.get(name, 0) + 1
            mock_table = MagicMock()
            if name == "tour_pipeline":
                # .select().eq().eq().execute() — 2 eq calls
                mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[tour]
                )
            elif name == "notifications":
                if call_count[name] == 1:
                    # .select().eq().eq().eq().execute() — 3 eq calls (check existing)
                    mock_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[]
                    )
                else:
                    # .insert().execute()
                    mock_table.insert.return_value.execute.return_value = MagicMock(data=[{}])
            return mock_table

        mock_sb.table.side_effect = table_side_effect

        with (
            patch("app.tasks.tour_reminder_tasks.supabase_admin", mock_sb),
            patch("app.tasks.tour_reminder_tasks.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = FIXED_NOW
            mock_dt.combine = datetime.combine
            check_tour_reminders()

        # Verify notification was inserted
        assert call_count["notifications"] == 2  # select (check) + insert

    def test_skips_already_toured(self):
        """Tours in 'toured' stage won't be returned by the eq('stage','scheduled') filter, so no notification."""
        mock_sb = MagicMock()

        def table_side_effect(name):
            mock_table = MagicMock()
            if name == "tour_pipeline":
                # .select().eq().eq().execute() — 2 eq calls, returns empty
                mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[]
                )
            return mock_table

        mock_sb.table.side_effect = table_side_effect

        with patch("app.tasks.tour_reminder_tasks.supabase_admin", mock_sb):
            check_tour_reminders()

        # Verify notifications table was never accessed
        for c in mock_sb.table.call_args_list:
            if c[0][0] == "notifications":
                assert False, "Should not access notifications table when no scheduled tours found"

    def test_skips_tour_without_time(self):
        """Tours with no scheduled_time should be skipped without error."""
        tour = _make_tour("tour-2", "user-2", "apt-2", None)

        mock_sb = MagicMock()

        def table_side_effect(name):
            mock_table = MagicMock()
            if name == "tour_pipeline":
                # .select().eq().eq().execute() — 2 eq calls
                mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[tour]
                )
            return mock_table

        mock_sb.table.side_effect = table_side_effect

        with (
            patch("app.tasks.tour_reminder_tasks.supabase_admin", mock_sb),
            patch("app.tasks.tour_reminder_tasks.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = FIXED_NOW
            mock_dt.combine = datetime.combine
            check_tour_reminders()

        # Should not crash, and notifications table should not be accessed
        for c in mock_sb.table.call_args_list:
            if c[0][0] == "notifications":
                assert False, "Should not access notifications table when tour has no scheduled_time"
