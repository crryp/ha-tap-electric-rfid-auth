"""Button platform for the Tap Electric RFID Auth integration.

Two buttons per charger: authorize a session (using the RFID tag configured
on that charger's subentry) and remotely stop the currently active session.
Both are wired up to real, verified Tap Electric OCPP calls - see api.py.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import TapElectricApiClient, TapElectricApiError
from .const import CONF_RFID, SUBENTRY_TYPE_CHARGER
from .data import TapElectricConfigEntry
from .entity import TapElectricChargerEntity

_LOGGER = logging.getLogger(__name__)

# Tap Electric's backend needs a moment (an OCPP round-trip to the charger)
# to reflect an authorize/stop call in /api/v1/charger-sessions. Poll again
# after this delay rather than waiting for the next regular (1h) update.
POLL_AFTER_AUTHORIZE = 15
POLL_AFTER_STOP = 15


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TapElectricConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tap Electric buttons, one pair per charger subentry."""
    coordinator = entry.runtime_data.coordinator
    client = entry.runtime_data.client

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_CHARGER:
            continue
        async_add_entities(
            [
                TapElectricAuthorizeButton(coordinator, client, subentry),
                TapElectricStopButton(coordinator, client, subentry),
            ],
            config_subentry_id=subentry.subentry_id,
        )


class TapElectricAuthorizeButton(TapElectricChargerEntity, ButtonEntity):
    """Authorize a charging session using this charger's configured RFID tag."""

    _attr_translation_key = "authorize_session"

    def __init__(self, coordinator, client: TapElectricApiClient, subentry) -> None:  # noqa: ANN001
        super().__init__(coordinator, subentry)
        self._client = client
        self._attr_unique_id = f"{self.charger_id}_authorize_session"

    @property
    def available(self) -> bool:
        """Disable the button in the UI while a session is already running.

        Mirror image of the stop button: you can't authorize a new session
        on a charger that already has one active.
        """
        return super().available and self.active_session is None

    async def async_press(self) -> None:
        """Trigger an authorize call for this charger."""
        if self.active_session is not None:
            raise HomeAssistantError(
                "Er loopt al een sessie op deze charger; stop die eerst."
            )
        rfid = self.subentry.data.get(CONF_RFID)
        if not rfid:
            raise HomeAssistantError(
                "Stel eerst een RFID-tag in voor deze charger "
                "(bewerk het apparaat via de integratie-instellingen)."
            )
        try:
            await self._client.async_authorize_session(self.charger_id, rfid)
        except TapElectricApiError as err:
            raise HomeAssistantError(f"Autoriseren van sessie mislukt: {err}") from err

        await self.coordinator.async_request_refresh()
        self._schedule_delayed_refresh(POLL_AFTER_AUTHORIZE)


class TapElectricStopButton(TapElectricChargerEntity, ButtonEntity):
    """Remotely stop the currently active session on this charger."""

    _attr_translation_key = "stop_session"

    def __init__(self, coordinator, client: TapElectricApiClient, subentry) -> None:  # noqa: ANN001
        super().__init__(coordinator, subentry)
        self._client = client
        self._attr_unique_id = f"{self.charger_id}_stop_session"

    @property
    def available(self) -> bool:
        """Disable the button in the UI while there is no active session."""
        return super().available and self.active_session is not None

    async def async_press(self) -> None:
        """Trigger a remote-stop call for this charger's active session."""
        session = self.active_session
        if not session:
            raise HomeAssistantError("Geen actieve sessie gevonden om te stoppen.")
        try:
            await self._client.async_stop_session(
                self.charger_id,
                session["id"],
                transaction_id=session.get("ocpp_transaction_id"),
            )
        except TapElectricApiError as err:
            raise HomeAssistantError(f"Stoppen van sessie mislukt: {err}") from err

        await self.coordinator.async_request_refresh()
        self._schedule_delayed_refresh(POLL_AFTER_STOP)
