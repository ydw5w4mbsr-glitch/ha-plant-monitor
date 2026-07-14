"""Constants for the Plant Monitor integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "plant_monitor"

SUBENTRY_TYPE_PLANT: Final = "plant"

PLATFORMS: tuple[Platform, ...] = (
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
)

CONF_MOISTURE_SENSOR: Final = "moisture_sensor"
CONF_DRY_BELOW: Final = "dry_below"
CONF_CLEAR_AT: Final = "clear_at"

DEFAULT_DRY_BELOW: Final = 25.0
DEFAULT_CLEAR_AT: Final = 35.0

MIN_MOISTURE: Final = 0.0
MAX_MOISTURE: Final = 100.0
