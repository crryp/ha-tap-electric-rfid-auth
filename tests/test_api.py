"""Tests for the API client's request timeouts.

OCPP commands go through Tap Electric's /ocpp proxy, which only answers once
the charger has replied - that can take well over the regular timeout right
after a car is plugged in, so those calls get a longer timeout.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.tap_electric_rfid_auth.api import (
    TapElectricApiClient,
    TapElectricApiError,
)

RESPONSE_DELAY = 0.2  # seconds


def _slow_client(timeout: float, ocpp_timeout: float) -> TapElectricApiClient:
    """Build a client whose HTTP responses all take RESPONSE_DELAY to arrive."""
    response = MagicMock(status=200, content_type="text/plain")

    async def _text() -> str:
        return ""

    response.text = _text

    async def _request(*args, **kwargs):
        await asyncio.sleep(RESPONSE_DELAY)
        return response

    session = MagicMock()
    session.request = _request
    return TapElectricApiClient(
        "key", session, timeout=timeout, ocpp_timeout=ocpp_timeout
    )


async def test_ocpp_command_uses_longer_timeout() -> None:
    """A slow /ocpp answer succeeds where a regular call with the same delay times out."""
    client = _slow_client(timeout=RESPONSE_DELAY / 4, ocpp_timeout=RESPONSE_DELAY * 5)

    await client.async_authorize_session("chg1", "AB")

    with pytest.raises(TapElectricApiError, match="Timeout"):
        await client.async_get_chargers()


async def test_ocpp_command_times_out_eventually() -> None:
    """The /ocpp call still gives up once its own timeout passes."""
    client = _slow_client(timeout=RESPONSE_DELAY * 5, ocpp_timeout=RESPONSE_DELAY / 4)

    with pytest.raises(TapElectricApiError, match="Timeout"):
        await client.async_authorize_session("chg1", "AB")
