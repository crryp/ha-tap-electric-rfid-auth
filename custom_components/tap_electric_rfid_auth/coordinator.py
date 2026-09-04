"""DataUpdateCoordinator for the Tap Electric RFID Auth integration."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TapElectricApiClient, TapElectricApiError
from .const import ACTIVE_SESSION_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .util import parse_iso

if TYPE_CHECKING:
    from .data import TapElectricConfigEntry

_LOGGER = logging.getLogger(__name__)


class TapElectricData(TypedDict):
    """Shape of `coordinator.data`."""

    chargers: dict[str, dict[str, Any]]
    # charger_id -> that charger's sessions, newest startedAt first. Kept as a
    # list (not just the single newest one) so a still-active session isn't
    # missed on a multi-connector charger where a *newer* session on another
    # connector may have already finished.
    sessions: dict[str, list[dict[str, Any]]]


class TapElectricDataUpdateCoordinator(DataUpdateCoordinator[TapElectricData]):
    """Coordinator that polls chargers + sessions for a Tap Electric account."""

    config_entry: TapElectricConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TapElectricConfigEntry,
        client: TapElectricApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        # session_id -> resolved OCPP transactionId. A session's transactionId
        # never changes once assigned, so once resolved we never need to hit
        # session-meter-data again for that session (only unresolved *active*
        # sessions get looked up - see below).
        self._transaction_id_cache: dict[str, int] = {}

    async def _async_update_data(self) -> TapElectricData:
        try:
            chargers = await self.client.async_get_chargers()
            sessions = await self.client.async_get_charger_sessions()
        except TapElectricApiError as err:
            raise UpdateFailed(f"Error fetching Tap Electric data: {err}") from err

        chargers_by_id = {charger["id"]: charger for charger in chargers}

        sessions_by_charger: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for session in sessions:
            charger_id = (session.get("charger") or {}).get("id")
            if not charger_id:
                continue
            sessions_by_charger[charger_id].append(session)

        for charger_sessions in sessions_by_charger.values():
            charger_sessions.sort(
                key=lambda s: parse_iso(s.get("startedAt")) or datetime.min, reverse=True
            )

        # For sessions still in progress, resolve the real OCPP transactionId
        # up front (needed to stop them - see api.py's async_stop_session for
        # why it's not the session's own "id"), so the stop button doesn't
        # need a fresh lookup. Cached per session_id so this only ever hits
        # the API once per session, not on every poll.
        for charger_sessions in sessions_by_charger.values():
            for session in charger_sessions:
                if session.get("endedAt") is not None:
                    continue
                session_id = session["id"]
                cached = self._transaction_id_cache.get(session_id)
                if cached is not None:
                    session["ocpp_transaction_id"] = cached
                    continue
                try:
                    meter_data = await self.client.async_get_session_meter_data(session_id)
                    if meter_data and meter_data[0].get("transactionId"):
                        transaction_id = int(meter_data[0]["transactionId"])
                        session["ocpp_transaction_id"] = transaction_id
                        self._transaction_id_cache[session_id] = transaction_id
                except (TapElectricApiError, TypeError, ValueError) as err:
                    _LOGGER.debug(
                        "Could not resolve OCPP transactionId for session %s: %s",
                        session_id,
                        err,
                    )

        # Poll faster while something is actually charging, back off to the
        # slow interval again once nothing is active.
        has_active_session = any(
            session.get("endedAt") is None
            for charger_sessions in sessions_by_charger.values()
            for session in charger_sessions
        )
        self.update_interval = timedelta(
            seconds=ACTIVE_SESSION_SCAN_INTERVAL
            if has_active_session
            else DEFAULT_SCAN_INTERVAL
        )

        return {"chargers": chargers_by_id, "sessions": dict(sessions_by_charger)}
