"""Sensor platform for the Tap Electric RFID Auth integration.

Two axes for the per-session sensors:

* *which* session - the currently **active** one, or the last **finished**
  one. These are kept strictly separate: a "current" sensor reads
  unknown/0 while nothing is charging, a "last" sensor keeps showing the
  most recently completed session and never jumps to the live one.
* *energy vs duration*, and for energy *Wh vs kWh* (same value, the kWh
  one just divides by 1000 - handy for the Energy dashboard).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SUBENTRY_TYPE_CHARGER
from .data import TapElectricConfigEntry
from .entity import TapElectricChargerEntity
from .util import parse_iso


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TapElectricConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tap Electric sensors, per charger subentry."""
    coordinator = entry.runtime_data.coordinator

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_CHARGER:
            continue
        async_add_entities(
            [
                TapElectricCurrentSessionEnergySensor(coordinator, subentry),
                TapElectricCurrentSessionEnergyKwhSensor(coordinator, subentry),
                TapElectricLastSessionEnergySensor(coordinator, subentry),
                TapElectricLastSessionEnergyKwhSensor(coordinator, subentry),
                TapElectricCurrentSessionDurationSensor(coordinator, subentry),
                TapElectricLastSessionDurationSensor(coordinator, subentry),
            ],
            config_subentry_id=subentry.subentry_id,
        )


def _session_attributes(session: dict[str, Any] | None) -> dict[str, Any]:
    """Common attribute set describing whichever session a sensor tracks."""
    session = session or {}
    return {
        "session_id": session.get("id"),
        "started_at": session.get("startedAt"),
        "ended_at": session.get("endedAt"),
        "updated_at": session.get("updatedAt"),
        "location": session.get("location"),
    }


class _TapElectricSessionEnergySensor(TapElectricChargerEntity, SensorEntity):
    """Shared base for the per-session energy sensors.

    Subclasses pick the session (`_session`) and the unit; the Wh vs kWh
    split is just `_attr_native_unit_of_measurement` plus `_divisor`.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _divisor = 1
    # What to report when there is no session to read energy from. The
    # "current session" sensors use 0 (nothing charging == 0 delivered,
    # mirroring the duration sensor); the "last session" ones use None so
    # they read unknown until a session has actually finished.
    _idle_value: float | None = None

    @property
    def _session(self) -> dict[str, Any] | None:
        """Return the session this sensor reports on."""
        raise NotImplementedError

    @property
    def native_value(self) -> float | None:
        """Return the session's delivered energy in this sensor's unit."""
        session = self._session
        wh = session.get("wh") if session else None
        if wh is None:
            return self._idle_value
        return wh / self._divisor if self._divisor != 1 else wh

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the session id (useful for automations) and timestamps."""
        return _session_attributes(self._session)


class TapElectricCurrentSessionEnergySensor(_TapElectricSessionEnergySensor):
    """Energy (Wh) delivered so far by the currently active session.

    Reads 0 whenever nothing is charging (like the duration sensor) - it
    never falls back to a finished session (that's what the "last session"
    sensors are for).
    """

    _attr_translation_key = "current_session"
    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    _idle_value = 0

    def __init__(self, coordinator, subentry) -> None:  # noqa: ANN001
        super().__init__(coordinator, subentry)
        self._attr_unique_id = f"{self.charger_id}_current_session"

    @property
    def _session(self) -> dict[str, Any] | None:
        return self.active_session


class TapElectricCurrentSessionEnergyKwhSensor(_TapElectricSessionEnergySensor):
    """Same as `TapElectricCurrentSessionEnergySensor`, but in kWh."""

    _attr_translation_key = "current_session_kwh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3
    _divisor = 1000
    _idle_value = 0

    def __init__(self, coordinator, subentry) -> None:  # noqa: ANN001
        super().__init__(coordinator, subentry)
        self._attr_unique_id = f"{self.charger_id}_current_session_kwh"

    @property
    def _session(self) -> dict[str, Any] | None:
        return self.active_session


class TapElectricLastSessionEnergySensor(_TapElectricSessionEnergySensor):
    """Energy (Wh) delivered by the last *finished* session.

    Always the most recently completed session - it does not switch to the
    live session once a new one starts.
    """

    _attr_translation_key = "last_session"
    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR

    def __init__(self, coordinator, subentry) -> None:  # noqa: ANN001
        super().__init__(coordinator, subentry)
        self._attr_unique_id = f"{self.charger_id}_last_session"

    @property
    def _session(self) -> dict[str, Any] | None:
        return self.last_finished_session


class TapElectricLastSessionEnergyKwhSensor(_TapElectricSessionEnergySensor):
    """Same as `TapElectricLastSessionEnergySensor`, but in kWh."""

    _attr_translation_key = "last_session_kwh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3
    _divisor = 1000

    def __init__(self, coordinator, subentry) -> None:  # noqa: ANN001
        super().__init__(coordinator, subentry)
        self._attr_unique_id = f"{self.charger_id}_last_session_kwh"

    @property
    def _session(self) -> dict[str, Any] | None:
        return self.last_finished_session


class TapElectricCurrentSessionDurationSensor(TapElectricChargerEntity, SensorEntity):
    """How long the *active* session has been running, in whole minutes.

    Deliberately does NOT fall back to the last (finished) session - it
    reads 0 whenever nothing is currently charging.
    """

    _attr_translation_key = "session_duration"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator, subentry) -> None:  # noqa: ANN001
        super().__init__(coordinator, subentry)
        self._attr_unique_id = f"{self.charger_id}_session_duration"

    @property
    def native_value(self) -> int:
        """Return the active session's duration in whole minutes, or 0."""
        session = self.active_session
        if not session:
            return 0
        started = parse_iso(session.get("startedAt"))
        if started is None:
            return 0
        return round((datetime.now(UTC) - started).total_seconds() / 60)


class TapElectricLastSessionDurationSensor(TapElectricChargerEntity, SensorEntity):
    """How long the last *finished* session lasted, in whole minutes.

    Complements `TapElectricCurrentSessionDurationSensor`: this one stays
    put on the duration of the most recently completed session and ignores
    whatever is charging now.
    """

    _attr_translation_key = "last_session_duration"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator, subentry) -> None:  # noqa: ANN001
        super().__init__(coordinator, subentry)
        self._attr_unique_id = f"{self.charger_id}_last_session_duration"

    @property
    def native_value(self) -> int | None:
        """Return the last finished session's duration in whole minutes."""
        session = self.last_finished_session
        if not session:
            return None
        started = parse_iso(session.get("startedAt"))
        ended = parse_iso(session.get("endedAt"))
        if started is None or ended is None:
            return None
        return round((ended - started).total_seconds() / 60)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose which session this duration belongs to."""
        return _session_attributes(self.last_finished_session)
