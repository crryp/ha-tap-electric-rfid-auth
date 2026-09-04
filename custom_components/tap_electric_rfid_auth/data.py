"""Runtime data types for the Tap Electric RFID Auth integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .api import TapElectricApiClient
    from .coordinator import TapElectricDataUpdateCoordinator


@dataclass
class TapElectricRuntimeData:
    """Data stored on the config entry's `runtime_data`."""

    client: TapElectricApiClient
    coordinator: TapElectricDataUpdateCoordinator


type TapElectricConfigEntry = ConfigEntry[TapElectricRuntimeData]
