"""Small shared helpers for the Tap Electric RFID Auth integration."""

from __future__ import annotations

from datetime import datetime


def parse_iso(value: str | None) -> datetime | None:
    """Parse a Tap Electric ISO-8601 timestamp, tolerating a trailing Z."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
