"""Constants for the Tap Electric RFID Auth integration."""

from typing import Final

DOMAIN: Final = "tap_electric_rfid_auth"

# The Tap Electric API is a single fixed endpoint, not user-configurable.
API_BASE_URL: Final = "https://api.tapelectric.app"

CONF_API_KEY: Final = "api_key"
CONF_CHARGER_ID: Final = "charger_id"
CONF_RFID: Final = "rfid"

# A charger discovered via /api/v1/chargers becomes a config subentry of this type.
SUBENTRY_TYPE_CHARGER: Final = "charger"

# Background polling interval. Actions (authorize/stop) trigger their own
# immediate (+ delayed, see button.py) refresh, so this is just for picking
# up changes made elsewhere (e.g. a session started via a physical RFID
# card) - hourly is plenty and keeps load on the Tap Electric API low.
DEFAULT_SCAN_INTERVAL: Final = 3600  # seconds

# While any charger has an active session, poll faster instead - so sensors
# like session duration/energy stay reasonably fresh while charging.
ACTIVE_SESSION_SCAN_INTERVAL: Final = 600  # seconds (10 minutes)

DEFAULT_TIMEOUT: Final = 10  # seconds
