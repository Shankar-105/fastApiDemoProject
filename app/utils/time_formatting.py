from datetime import datetime, timezone, timedelta
from typing import Union

def format_timestamp(dt: Union[datetime, None]) -> str:
    """
    Converts a datetime (with or without timezone) into human-readable format
    Examples:
        Just now → if < 1 min ago
        5m ago   → if < 1 hour
        2h ago   → if < 1 day
        Today at 3:45 PM
        Yesterday at 3:45 PM
        Monday at 4:00 PM
        19-11-2025 04:00 PM
    """
    if not dt:
        return "N/A"

    # Ensure we're working with timezone-aware datetime
    if dt.tzinfo is None:
        # Assume UTC if naive
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC for consistent comparison
        dt = dt.astimezone(timezone.utc)

    # Get current time in UTC
    now = datetime.now(timezone.utc)
    diff = now - dt

    # Less than a minute ago
    if diff.total_seconds() < 60:
        return "Just now"
    
    # Less than an hour ago
    elif diff.total_seconds() < 3600:
        mins = int(diff.total_seconds() // 60)
        return f"{mins}m ago"
    
    # Less than 24 hours ago (today)
    elif diff.total_seconds() < 86400 and now.date() == dt.date():
        hours = int(diff.total_seconds() // 3600)
        return f"{hours}h ago"
    
    # Convert to local time for display
    local_dt = dt.astimezone(get_local_indian_time())
    local_now = now.astimezone(get_local_indian_time())
    
    # Yesterday
    if (local_now.date() - local_dt.date()).days == 1:
        return local_dt.strftime("Yesterday at %I:%M %p")
    
    # Within last week
    elif diff.days < 7:
        return local_dt.strftime("%A at %I:%M %p")  # Monday at 4:00 PM
    
    # Older than a week
    else:
        return local_dt.strftime("%d-%m-%Y %I:%M %p")


def get_local_indian_time():
    """Returns IST timezone (UTC +5:30)"""
    return timezone(timedelta(hours=5, minutes=30))
