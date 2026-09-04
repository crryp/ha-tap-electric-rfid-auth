"""Config flow for the Tap Electric RFID Auth integration.

Two flows live here:
- TapElectricConfigFlow: the top-level "add integration" / "reconfigure"
  flow that only asks for an API key. On success it seeds one config
  subentry per charger currently on the account.
- ChargerSubentryFlowHandler: manages the per-charger subentries (= HA
  devices). "user" lets you manually link a charger that isn't linked yet
  (e.g. one added to the account after initial setup); "reconfigure" lets
  you change the RFID tag for an already-linked charger.

NOTE: config subentries are a newer part of Home Assistant's integration
API. This is a best-effort implementation - verify the exact method/param
names against the Home Assistant version running in the dev container.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TapElectricApiClient, TapElectricApiError, TapElectricAuthError
from .const import CONF_API_KEY, CONF_CHARGER_ID, CONF_RFID, DOMAIN, SUBENTRY_TYPE_CHARGER

_LOGGER = logging.getLogger(__name__)

STEP_API_KEY_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


async def _async_validate_api_key(hass: Any, api_key: str) -> tuple[dict[str, str], list[dict]]:
    """Validate an API key, returning (errors, chargers)."""
    client = TapElectricApiClient(api_key, async_get_clientsession(hass))
    try:
        chargers = await client.async_get_chargers()
    except TapElectricAuthError:
        return {"base": "invalid_auth"}, []
    except TapElectricApiError:
        return {"base": "cannot_connect"}, []
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected exception validating Tap Electric API key")
        return {"base": "unknown"}, []
    return {}, chargers


class TapElectricConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tap Electric RFID Auth."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the API key, then seed one subentry per discovered charger."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors, chargers = await _async_validate_api_key(
                self.hass, user_input[CONF_API_KEY]
            )
            if not errors:
                subentries = [
                    {
                        "subentry_type": SUBENTRY_TYPE_CHARGER,
                        "title": charger.get("name") or charger["id"],
                        "unique_id": charger["id"],
                        "data": {CONF_RFID: ""},
                    }
                    for charger in chargers
                ]
                return self.async_create_entry(
                    title="Tap Electric",
                    data=user_input,
                    subentries=subentries,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_API_KEY_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow updating the API key on an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            errors, _chargers = await _async_validate_api_key(
                self.hass, user_input[CONF_API_KEY]
            )
            if not errors:
                return self.async_update_reload_and_abort(entry, data=user_input)

        return self.async_show_form(
            step_id="reconfigure", data_schema=STEP_API_KEY_SCHEMA, errors=errors
        )

    @classmethod
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Declare the subentry types this integration supports."""
        return {SUBENTRY_TYPE_CHARGER: ChargerSubentryFlowHandler}


class ChargerSubentryFlowHandler(ConfigSubentryFlow):
    """Add a not-yet-linked charger, or edit an existing charger's RFID tag."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        """Manually link a charger that doesn't have a subentry yet."""
        entry = self._get_entry()
        client = entry.runtime_data.client

        try:
            chargers = await client.async_get_chargers()
        except TapElectricApiError:
            return self.async_abort(reason="cannot_connect")

        existing_ids = {sub.unique_id for sub in entry.subentries.values()}
        available = {
            charger["id"]: charger.get("name") or charger["id"]
            for charger in chargers
            if charger["id"] not in existing_ids
        }

        if not available:
            return self.async_abort(reason="no_chargers_available")

        if user_input is not None:
            charger_id = user_input[CONF_CHARGER_ID]
            return self.async_create_entry(
                title=available[charger_id],
                data={CONF_RFID: user_input.get(CONF_RFID, "")},
                unique_id=charger_id,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_CHARGER_ID): vol.In(available),
                vol.Optional(CONF_RFID, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Edit the RFID tag stored on an existing charger subentry."""
        subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, data={CONF_RFID: user_input[CONF_RFID]}
            )

        schema = vol.Schema(
            {vol.Optional(CONF_RFID, default=subentry.data.get(CONF_RFID, "")): str}
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema)
