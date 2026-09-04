# dateTime.py
from datetime import datetime


def get_current_datetime() -> str:
    """Return the current date and time as a human-readable string."""
    now = datetime.now()
    return now.strftime("Current date/time: %A, %d %B %Y, %H:%M:%S")
