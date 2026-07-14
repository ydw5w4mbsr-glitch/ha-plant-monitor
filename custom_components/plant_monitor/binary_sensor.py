"""Binary sensor platform for the Plant Monitor integration."""

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
)

from .entity import PlantMonitorEntity, PlantMonitorPlantEntity
from .manager import PlantMonitorManager
from .models import PlantState

ATTR_CLEAR_AT = "clear_at"
ATTR_DRY_BELOW = "dry_below"
ATTR_DRY_PLANTS = "dry_plants"
ATTR_MOISTURE = "moisture"
ATTR_MOISTURE_SENSOR = "moisture_sensor"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[PlantMonitorManager],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Plant Monitor binary sensors."""
    manager = entry.runtime_data

    async_add_entities(
        [PlantMonitorWateringNeededBinarySensor(manager)]
    )

    for plant_state in manager.plant_states:
        async_add_entities(
            [
                PlantWateringNeededBinarySensor(
                    manager,
                    plant_state,
                )
            ],
            config_subentry_id=plant_state.config.subentry_id,
        )


class PlantMonitorWateringNeededBinarySensor(
    PlantMonitorEntity,
    BinarySensorEntity,
):
    """Indicate whether any monitored plant needs watering."""

    _attr_translation_key = "plant_monitor_watering_needed"

    def __init__(self, manager: PlantMonitorManager) -> None:
        """Initialize the central watering-needed binary sensor."""
        super().__init__(
            manager,
            "watering_needed",
        )

    @property
    def is_on(self) -> bool:
        """Return whether at least one plant needs watering."""
        return self.manager.watering_needed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            ATTR_DRY_PLANTS: self.manager.dry_plant_names,
        }


class PlantWateringNeededBinarySensor(
    PlantMonitorPlantEntity,
    BinarySensorEntity,
):
    """Indicate whether one monitored plant needs watering."""

    _attr_translation_key = "watering_needed"

    def __init__(
        self,
        manager: PlantMonitorManager,
        plant_state: PlantState,
    ) -> None:
        """Initialize a plant watering-needed binary sensor."""
        super().__init__(
            manager,
            plant_state,
            "watering_needed",
        )

    @property
    def is_on(self) -> bool:
        """Return whether this plant needs watering."""
        return self.plant_state.watering_needed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return plant configuration and moisture information."""
        return {
            ATTR_MOISTURE_SENSOR: (
                self.plant_state.config.moisture_sensor
            ),
            ATTR_MOISTURE: self.plant_state.moisture,
            ATTR_DRY_BELOW: self.plant_state.config.dry_below,
            ATTR_CLEAR_AT: self.plant_state.config.clear_at,
        }
