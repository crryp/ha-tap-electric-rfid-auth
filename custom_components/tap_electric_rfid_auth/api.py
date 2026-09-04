"""REST API client for the Tap Electric platform (api.tapelectric.app).

Confirmed endpoints (as of 2026-09):
- GET  /api/v1/chargers                                  -> chargers on the account
- GET  /api/v1/charger-sessions                           -> (recent) charging sessions
- GET  /api/v1/charger-sessions/{id}/session-meter-data   -> meter readings for one session
- POST /api/v1/chargers/{id}/ocpp                         -> generic OCPP command proxy, body:
        {"action": "<OCPP action>", "ocppVersion": "ocpp1.6", "data": "<json-encoded OCPP payload>"}
  Confirmed actions via that proxy:
  - "RemoteStartTransaction" with data {"idTag": "<hex rfid>"} (async_authorize_session)
  - "RemoteStopTransaction" with data {"transactionId": <int>} (async_stop_session).
    IMPORTANT: this transactionId is the real numeric OCPP transaction id -
    it is NOT the charger-session's own "id" (e.g. "cs_28de..."). That id
    is a Tap Electric-internal identifier and sending it as transactionId
    is silently accepted (HTTP 200) but does nothing. The real transactionId
    only shows up per reading in session-meter-data, so async_stop_session
    looks it up there first. Verified end-to-end against a real charger.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .const import API_BASE_URL, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class TapElectricApiError(Exception):
    """General API error."""


class TapElectricAuthError(TapElectricApiError):
    """Raised on authentication failure (HTTP 401/403)."""


class TapElectricApiClient:
    """Client to talk to the Tap Electric REST API."""

    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession,
        base_url: str = API_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the API client."""
        self._api_key = api_key
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    # -- read endpoints -----------------------------------------------------

    async def async_get_chargers(self) -> list[dict[str, Any]]:
        """GET the chargers on this account."""
        return await self._request("GET", "/api/v1/chargers")

    async def async_get_charger_sessions(self) -> list[dict[str, Any]]:
        """GET (recent) charging sessions across all chargers."""
        return await self._request("GET", "/api/v1/charger-sessions")

    async def async_get_session_meter_data(self, session_id: str) -> list[dict[str, Any]]:
        """GET meter readings for one session.

        This is the only place the real OCPP transactionId shows up.
        """
        return await self._request(
            "GET", f"/api/v1/charger-sessions/{session_id}/session-meter-data"
        )

    async def async_test_connection(self) -> bool:
        """Verify we can reach and authenticate against the API."""
        await self.async_get_chargers()
        return True

    # -- session control ------------------------------------------------------

    async def async_send_ocpp_command(
        self, charger_id: str, action: str, data: dict[str, Any]
    ) -> Any:
        """Send a raw OCPP command to a charger via the /ocpp proxy endpoint.

        `data` is the OCPP action's own payload (e.g. {"idTag": "..."}) - it
        gets JSON-encoded into a string, matching what the API expects.
        """
        payload = {
            "action": action,
            "ocppVersion": "ocpp1.6",
            "data": json.dumps(data),
        }
        return await self._request(
            "POST", f"/api/v1/chargers/{charger_id}/ocpp", json=payload
        )

    async def async_authorize_session(self, charger_id: str, id_tag: str) -> Any:
        """Authorize (and start) a charging session on a charger via its RFID idTag."""
        return await self.async_send_ocpp_command(
            charger_id, "RemoteStartTransaction", {"idTag": id_tag}
        )

    async def async_stop_session(
        self, charger_id: str, session_id: str, transaction_id: int | None = None
    ) -> Any:
        """Remotely stop a charging session.

        `session_id` is the charger-session's own "id" (from
        async_get_charger_sessions). If the caller doesn't already know the
        real OCPP `transaction_id` (e.g. the coordinator resolved it on the
        last poll, see coordinator.py), it's looked up here via
        session-meter-data - that's the only place it's exposed.
        """
        if transaction_id is None:
            meter_data = await self.async_get_session_meter_data(session_id)
            if not meter_data or not meter_data[0].get("transactionId"):
                raise TapElectricApiError(
                    f"No OCPP transactionId found in meter data for session {session_id}"
                )
            try:
                transaction_id = int(meter_data[0]["transactionId"])
            except (TypeError, ValueError) as err:
                raise TapElectricApiError(
                    f"Unexpected transactionId in meter data for session {session_id}: "
                    f"{meter_data[0]['transactionId']!r}"
                ) from err

        return await self.async_send_ocpp_command(
            charger_id, "RemoteStopTransaction", {"transactionId": transaction_id}
        )

    # -- internals ------------------------------------------------------------

    async def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers = {"X-Api-Key": self._api_key}

        try:
            async with asyncio.timeout(self._timeout):
                response = await self._session.request(
                    method, url, headers=headers, json=json
                )
                if response.status in (401, 403):
                    raise TapElectricAuthError(
                        f"Authentication failed for {url}: {response.status}"
                    )
                response.raise_for_status()
                if response.content_type == "application/json":
                    return await response.json()
                return await response.text()
        except TapElectricAuthError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            raise TapElectricApiError(f"Error communicating with {url}: {err}") from err
