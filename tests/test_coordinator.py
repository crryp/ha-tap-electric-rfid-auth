"""Tests for the coordinator's session/connector matching logic.

These exercise the exact bug class the multi-connector handling was written
to avoid: picking a still-active session even when a *newer* session on
another connector of the same charger has already finished.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tap_electric_rfid_auth.const import DOMAIN
from custom_components.tap_electric_rfid_auth.coordinator import (
    TapElectricDataUpdateCoordinator,
)

CHARGER_ID = "chg1"
CHARGERS = [{"id": CHARGER_ID, "name": "Test charger"}]


def _make_client(sessions, meter_data_by_session=None):
    """Build a fake API client returning fixed chargers/sessions/meter-data."""
    meter_data_by_session = meter_data_by_session or {}
    client = AsyncMock()
    client.async_get_chargers.return_value = CHARGERS
    client.async_get_charger_sessions.return_value = sessions
    client.async_get_session_meter_data.side_effect = (
        lambda session_id: meter_data_by_session.get(session_id, [])
    )
    return client


def _make_coordinator(hass, client):
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": "test"})
    entry.add_to_hass(hass)
    return TapElectricDataUpdateCoordinator(hass, entry, client)


async def test_active_session_found_despite_newer_finished_session(hass) -> None:
    """A still-active session on one connector must be found even though a
    *newer* session on another connector of the same charger already ended.
    """
    sessions = [
        # Connector 2: started later, already finished.
        {
            "id": "s_new_finished",
            "charger": {"id": CHARGER_ID, "connectorId": "2"},
            "wh": 10,
            "startedAt": "2026-01-01T10:00:00Z",
            "endedAt": "2026-01-01T10:05:00Z",
        },
        # Connector 1: started earlier, still active.
        {
            "id": "s_old_active",
            "charger": {"id": CHARGER_ID, "connectorId": "1"},
            "wh": 5,
            "startedAt": "2026-01-01T09:00:00Z",
            "endedAt": None,
        },
    ]
    client = _make_client(
        sessions, meter_data_by_session={"s_old_active": [{"transactionId": "42"}]}
    )
    coordinator = _make_coordinator(hass, client)

    data = await coordinator._async_update_data()  # noqa: SLF001

    charger_sessions = data["sessions"][CHARGER_ID]
    # Sorted newest-started first...
    assert charger_sessions[0]["id"] == "s_new_finished"
    # ...but the *active* one is still found regardless of sort order.
    active = next(s for s in charger_sessions if s.get("endedAt") is None)
    assert active["id"] == "s_old_active"
    assert active["ocpp_transaction_id"] == 42


async def test_ended_sessions_never_trigger_meter_data_lookup(hass) -> None:
    """Only active sessions should ever need a session-meter-data lookup."""
    sessions = [
        {
            "id": "s_finished",
            "charger": {"id": CHARGER_ID, "connectorId": "1"},
            "wh": 10,
            "startedAt": "2026-01-01T10:00:00Z",
            "endedAt": "2026-01-01T10:05:00Z",
        }
    ]
    client = _make_client(sessions)
    coordinator = _make_coordinator(hass, client)

    await coordinator._async_update_data()  # noqa: SLF001

    client.async_get_session_meter_data.assert_not_called()


async def test_transaction_id_resolved_once_and_cached(hass) -> None:
    """The OCPP transaction id should only be looked up once per session,
    even across repeated updates while it's still active."""
    sessions = [
        {
            "id": "s_active",
            "charger": {"id": CHARGER_ID, "connectorId": "1"},
            "wh": 1,
            "startedAt": "2026-01-01T09:00:00Z",
            "endedAt": None,
        }
    ]
    client = _make_client(
        sessions, meter_data_by_session={"s_active": [{"transactionId": "99"}]}
    )
    coordinator = _make_coordinator(hass, client)

    await coordinator._async_update_data()  # noqa: SLF001
    data = await coordinator._async_update_data()  # noqa: SLF001

    assert data["sessions"][CHARGER_ID][0]["ocpp_transaction_id"] == 99
    assert client.async_get_session_meter_data.call_count == 1
