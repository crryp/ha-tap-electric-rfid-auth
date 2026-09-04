"""Diagnostics support for Tap Electric RFID Auth."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY
from .data import TapElectricConfigEntry

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TapElectricConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "subentries": {
            sub.subentry_id: {
                "type": sub.subentry_type,
                "title": sub.title,
                "unique_id": sub.unique_id,
                "data": dict(sub.data),
            }
            for sub in entry.subentries.values()
        },
        "coordinator_data": entry.runtime_data.coordinator.data,
    }
