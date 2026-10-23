"""Tests for the buttons' wait-for-effect polling.

After an authorize/stop, the change only shows up in Tap Electric once the
charger reports back - which can take minutes. The button keeps polling
until it appears, and refuses a second press meanwhile.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tap_electric_rfid_auth import entity as entity_module
from custom_components.tap_electric_rfid_auth.button import (
    TapElectricAuthorizeButton,
    TapElectricStopButton,
)
from custom_components.tap_electric_rfid_auth.const import DOMAIN
from custom_components.tap_electric_rfid_auth.coordinator import (
    TapElectricDataUpdateCoordinator,
)

CHARGER_ID = "chg1"
ACTIVE_SESSION = {
    "id": "s_active",
    "charger": {"id": CHARGER_ID, "connectorId": "1"},
    "startedAt": "2026-01-01T09:00:00Z",
    "endedAt": None,
}


def _make_button(hass, button_cls=TapElectricAuthorizeButton, sessions=None):
    """Build a button on a coordinator with the given sessions (none by default)."""
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": "test"})
    entry.add_to_hass(hass)
    client = AsyncMock()
    coordinator = TapElectricDataUpdateCoordinator(hass, entry, client)
    coordinator.data = {
        "chargers": {CHARGER_ID: {"id": CHARGER_ID}},
        "sessions": {CHARGER_ID: sessions} if sessions else {},
    }
    coordinator.async_request_refresh = AsyncMock()

    subentry = SimpleNamespace(unique_id=CHARGER_ID, title="Test charger", data={"rfid": "AB"})
    button = button_cls(coordinator, client, subentry)
    button.hass = hass
    button.entity_id = "button.test_charger"
    button.async_write_ha_state = MagicMock()
    return button, coordinator, client


async def test_polls_until_session_appears(hass) -> None:
    """Keep refreshing after an authorize until the session shows up, then stop."""
    button, coordinator, client = _make_button(hass)
    calls = 0

    async def refresh() -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            coordinator.data["sessions"] = {CHARGER_ID: [ACTIVE_SESSION]}

    coordinator.async_refresh = AsyncMock(side_effect=refresh)

    with patch.object(entity_module, "ACTION_POLL_INTERVAL", 0):
        await button.async_press()
        assert button.action_pending
        assert not button.available
        await button._poll_task  # noqa: SLF001

    client.async_authorize_session.assert_awaited_once_with(CHARGER_ID, "AB")
    assert coordinator.async_refresh.await_count == 3
    assert not button.action_pending


async def test_gives_up_after_timeout(hass) -> None:
    """Without a session appearing, polling stops at the timeout and the button frees up."""
    button, coordinator, _client = _make_button(hass)
    coordinator.async_refresh = AsyncMock()

    with (
        patch.object(entity_module, "ACTION_POLL_INTERVAL", 0),
        patch.object(entity_module, "ACTION_POLL_TIMEOUT", 0.05),
    ):
        await button.async_press()
        await button._poll_task  # noqa: SLF001

    assert coordinator.async_refresh.await_count >= 1
    assert not button.action_pending
    assert button.available


async def test_second_authorize_refused_while_pending(hass) -> None:
    """A second press while still waiting for the first session must not re-authorize."""
    button, _coordinator, client = _make_button(hass)

    await button.async_press()
    with pytest.raises(HomeAssistantError):
        await button.async_press()

    client.async_authorize_session.assert_awaited_once()
    await button.async_will_remove_from_hass()
    assert not button.action_pending


async def test_stop_polls_until_session_ended(hass) -> None:
    """After a stop, keep refreshing until the session has ended, refusing a second stop."""
    button, coordinator, client = _make_button(
        hass, TapElectricStopButton, sessions=[{**ACTIVE_SESSION, "ocpp_transaction_id": 42}]
    )
    calls = 0

    async def refresh() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            coordinator.data["sessions"] = {
                CHARGER_ID: [{**ACTIVE_SESSION, "endedAt": "2026-01-01T10:00:00Z"}]
            }

    coordinator.async_refresh = AsyncMock(side_effect=refresh)

    with patch.object(entity_module, "ACTION_POLL_INTERVAL", 0):
        await button.async_press()
        assert not button.available
        with pytest.raises(HomeAssistantError):
            await button.async_press()
        await button._poll_task  # noqa: SLF001

    client.async_stop_session.assert_awaited_once_with(
        CHARGER_ID, "s_active", transaction_id=42
    )
    assert coordinator.async_refresh.await_count == 2
    assert not button.action_pending
