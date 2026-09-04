"""Binary sensor platform for the Tap Electric RFID Auth integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SUBENTRY_TYPE_CHARGER
from .data import TapElectricConfigEntry
from .entity import TapElectricChargerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TapElectricConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tap Electric binary sensors, one pair per charger subentry."""
    coordinator = entry.runtime_data.coordinator

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_CHARGER:
            continue
        async_add_entities(
            [
                TapElectricOnlineSensor(coordinator, subentry),
                TapElectricActiveSessionSensor(coordinator, subentry),
            ],
            config_subentry_id=subentry.subentry_id,
        )


class TapElectricOnlineSensor(TapElectricChargerEntity, BinarySensorEntity):
    """Whether the charger is currently online."""

    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, subentry) -> None:  # noqa: ANN001
        super().__init__(coordinator, subentry)
        self._attr_unique_id = f"{self.charger_id}_online"

    @property
    def is_on(self) -> bool | None:
        charger = self.charger
        return charger.get("online") if charger else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        charger = self.charger or {}
        return {"offline_since": charger.get("offlineSince")}


class TapElectricActiveSessionSensor(TapElectricChargerEntity, BinarySensorEntity):
    """Whether a charging session is currently active on this charger.

    This is deliberately its own entity (rather than only an attribute on
    the "last session" sensor) so "no active session" has a clear, explicit
    state instead of the energy sensor just going blank/unknown.
    """

    _attr_translation_key = "active_session"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator, subentry) -> None:  # noqa: ANN001
        super().__init__(coordinator, subentry)
        self._attr_unique_id = f"{self.charger_id}_active_session"

    @property
    def is_on(self) -> bool:
        return self.active_session is not None
