"""Tests for 12-hour time parsing functionality."""

import pytest
from datetime import time
from received.views import parse_12hour_time


class TestParse12HourTime:
    """Test cases for parse_12hour_time function."""

    def test_valid_am_times(self):
        """Test valid AM times."""
        # 12:XX AM cases (midnight hour)
        assert parse_12hour_time("12:00 AM") == time(0, 0)
        assert parse_12hour_time("12:30 AM") == time(0, 30)
        assert parse_12hour_time("12:59 AM") == time(0, 59)
        
        # Regular AM times
        assert parse_12hour_time("1:00 AM") == time(1, 0)
        assert parse_12hour_time("6:15 AM") == time(6, 15)
        assert parse_12hour_time("11:45 AM") == time(11, 45)

    def test_valid_pm_times(self):
        """Test valid PM times."""
        # 12:XX PM cases (noon hour)
        assert parse_12hour_time("12:00 PM") == time(12, 0)
        assert parse_12hour_time("12:30 PM") == time(12, 30)
        assert parse_12hour_time("12:59 PM") == time(12, 59)
        
        # Regular PM times
        assert parse_12hour_time("1:00 PM") == time(13, 0)
        assert parse_12hour_time("6:15 PM") == time(18, 15)
        assert parse_12hour_time("11:45 PM") == time(23, 45)

    def test_case_insensitive(self):
        """Test that AM/PM is case insensitive."""
        assert parse_12hour_time("2:30 am") == time(2, 30)
        assert parse_12hour_time("2:30 AM") == time(2, 30)
        assert parse_12hour_time("2:30 pm") == time(14, 30)
        assert parse_12hour_time("2:30 PM") == time(14, 30)

    def test_leading_zero_optional(self):
        """Test that leading zero is optional."""
        assert parse_12hour_time("2:30 AM") == time(2, 30)
        assert parse_12hour_time("02:30 AM") == time(2, 30)
        assert parse_12hour_time("9:15 PM") == time(21, 15)
        assert parse_12hour_time("09:15 PM") == time(21, 15)

    def test_24hour_fallback(self):
        """Test that 24-hour format still works as fallback."""
        assert parse_12hour_time("14:30") == time(14, 30)
        assert parse_12hour_time("00:00") == time(0, 0)
        assert parse_12hour_time("23:59") == time(23, 59)

    def test_invalid_formats(self):
        """Test invalid time formats raise ValueError."""
        with pytest.raises(ValueError, match="Invalid time format"):
            parse_12hour_time("25:00 AM")
        
        with pytest.raises(ValueError, match="Invalid time format"):
            parse_12hour_time("2:30")  # Missing AM/PM
        
        with pytest.raises(ValueError, match="Invalid time format"):
            parse_12hour_time("2:30 XM")  # Invalid period
        
        with pytest.raises(ValueError, match="Invalid time format"):
            parse_12hour_time("invalid")

    def test_invalid_hour_values(self):
        """Test invalid hour values."""
        with pytest.raises(ValueError, match="Hour must be between 1 and 12"):
            parse_12hour_time("0:30 AM")
        
        with pytest.raises(ValueError, match="Hour must be between 1 and 12"):
            parse_12hour_time("13:30 AM")

    def test_invalid_minute_values(self):
        """Test invalid minute values."""
        with pytest.raises(ValueError, match="Minutes must be between 0 and 59"):
            parse_12hour_time("2:60 AM")
        
        with pytest.raises(ValueError, match="Minutes must be between 0 and 59"):
            parse_12hour_time("2:-1 AM")

    def test_empty_or_none_input(self):
        """Test empty or None input."""
        with pytest.raises(ValueError, match="Time string is required"):
            parse_12hour_time("")
        
        with pytest.raises(ValueError, match="Time string is required"):
            parse_12hour_time(None)

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        assert parse_12hour_time("  2:30 PM  ") == time(14, 30)
        assert parse_12hour_time("2:30  PM") == time(14, 30)
        assert parse_12hour_time("2:30 PM ") == time(14, 30)
