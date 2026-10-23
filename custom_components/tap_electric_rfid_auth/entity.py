"""Base entity for the Tap Electric RFID Auth integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ACTION_POLL_INTERVAL, ACTION_POLL_TIMEOUT, DOMAIN
from .coordinator import TapElectricDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigSubentry

_LOGGER = logging.getLogger(__name__)


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
        self._poll_task: asyncio.Task | None = None

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

    @property
    def action_pending(self) -> bool:
        """Whether an action was sent and we're still waiting for it to show up."""
        return self._poll_task is not None

    async def _async_poll_after_action(self, done: Callable[[], bool], action: str) -> None:
        """Refresh now, then keep polling in the background until `done()` holds.

        Used after actions (authorize/stop) whose effect on Tap Electric's
        side may take a while to show up (see ACTION_POLL_* in const.py), so
        the UI doesn't have to wait for the next regular poll.
        """
        self._poll_task = self.coordinator.config_entry.async_create_background_task(
            self.hass,
            self._async_poll_until(done, action),
            f"{self.entity_id} wait for {action}",
        )
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def _async_poll_until(self, done: Callable[[], bool], action: str) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + ACTION_POLL_TIMEOUT
        try:
            while loop.time() < deadline:
                await asyncio.sleep(ACTION_POLL_INTERVAL)
                # Not async_request_refresh: that's debounced, and every one
                # of these polls should actually happen.
                await self.coordinator.async_refresh()
                if done():
                    break
            else:
                _LOGGER.warning(
                    "%s on charger %s didn't show up within %s s; "
                    "the regular update will still pick it up later",
                    action,
                    self.charger_id,
                    ACTION_POLL_TIMEOUT,
                )
        finally:
            self._poll_task = None
        # Skipped when cancelled (entity removed/unloaded) - nothing to update then.
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Stop polling for a pending action when the entity goes away."""
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None
