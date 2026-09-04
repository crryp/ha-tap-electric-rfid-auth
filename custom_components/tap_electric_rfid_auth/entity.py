"""Base entity for the Tap Electric RFID Auth integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TapElectricDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigSubentry


class TapElectricChargerEntity(CoordinatorEntity[TapElectricDataUpdateCoordinator]):
    """Base entity tied to a single charger (= config subentry)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TapElectricDataUpdateCoordinator,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.subentry = subentry
        self.charger_id: str = subentry.unique_id  # type: ignore[assignment]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.charger_id)},
            name=subentry.title,
            manufacturer="Tap Electric",
        )
        self._cancel_delayed_refresh = None

    @property
    def charger(self) -> dict[str, Any] | None:
        """Return the raw charger payload for this device."""
        return self.coordinator.data["chargers"].get(self.charger_id)

    @property
    def sessions(self) -> list[dict[str, Any]]:
        """Return this charger's known sessions, newest startedAt first."""
        return self.coordinator.data["sessions"].get(self.charger_id, [])

    @property
    def active_session(self) -> dict[str, Any] | None:
        """Return the session that is still ongoing (`endedAt` is None), if any.

        Scans all known sessions rather than only the most recently started
        one, so an ongoing session on one connector isn't missed just
        because a newer (already finished) session exists on another
        connector of the same charger.
        """
        for session in self.sessions:
            if session.get("endedAt") is None:
                return session
        return None

    @property
    def last_finished_session(self) -> dict[str, Any] | None:
        """Return the most recently *finished* session (`endedAt` set), if any.

        Sessions are ordered newest `startedAt` first, so the first one
        that carries an `endedAt` is the last completed session - even when
        a newer session is still active.
        """
        for session in self.sessions:
            if session.get("endedAt") is not None:
                return session
        return None

    @property
    def available(self) -> bool:
        """Entity is only available while its charger is still known to the API."""
        return super().available and self.charger is not None

    def _schedule_delayed_refresh(self, delay: float) -> None:
        """Schedule a coordinator refresh in `delay` seconds.

        Used after actions (authorize/stop) whose effect on
        Tap Electric's side may take a moment to show up, so the UI
        doesn't have to wait for the next regular (hourly) poll. Replaces
        any refresh already pending for this entity.
        """
        if self._cancel_delayed_refresh is not None:
            self._cancel_delayed_refresh()
        self._cancel_delayed_refresh = async_call_later(
            self.hass, delay, self._async_delayed_refresh
        )

    async def _async_delayed_refresh(self, _now) -> None:
        self._cancel_delayed_refresh = None
        await self.coordinator.async_request_refresh()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any pending delayed refresh when the entity goes away."""
        if self._cancel_delayed_refresh is not None:
            self._cancel_delayed_refresh()
            self._cancel_delayed_refresh = None
