
"""Sensor platform for the Plant Monitor integration."""

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
)

from .entity import PlantMonitorEntity, PlantMonitorPlantEntity
from .manager import PlantMonitorManager
from .models import PlantState, PlantStatus

ATTR_DRY_PLANTS = "dry_plants"
ATTR_INVALID_SENSOR_COUNT = "invalid_sensor_count"
ATTR_INVALID_SENSORS = "invalid_sensors"
ATTR_MOISTURE_SENSOR = "moisture_sensor"
ATTR_UNAVAILABLE_SENSORS = "unavailable_sensors"
ATTR_WATERING_NEEDED = "watering_needed"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[PlantMonitorManager],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Plant Monitor sensors."""
    manager = entry.runtime_data

    async_add_entities(
        [
            PlantMonitorDryPlantsSensor(manager),
            PlantMonitorUnavailableSensorsSensor(manager),
        ]
    )

    for plant_state in manager.plant_states:
        async_add_entities(
            [
                PlantSoilMoistureSensor(
                    manager,
                    plant_state,
                ),
                PlantStatusSensor(
                    manager,
                    plant_state,
                ),
                PlantDryBelowSensor(
                    manager,
                    plant_state,
                ),
                PlantClearAtSensor(
                    manager,
                    plant_state,
                ),
            ],
            config_subentry_id=plant_state.config.subentry_id,
        )


class PlantMonitorDryPlantsSensor(
    PlantMonitorEntity,
    SensorEntity,
):
    """Report the number of plants that need watering."""

    _attr_translation_key = "dry_plants"

    def __init__(self, manager: PlantMonitorManager) -> None:
        """Initialize the dry-plants sensor."""
        super().__init__(
            manager,
            "dry_plants",
        )

    @property
    def native_value(self) -> int:
        """Return the number of plants that need watering."""
        return self.manager.dry_plant_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return names of plants that need watering."""
        return {
            ATTR_DRY_PLANTS: self.manager.dry_plant_names,
        }


class PlantMonitorUnavailableSensorsSensor(
    PlantMonitorEntity,
    SensorEntity,
):
    """Report the number of unavailable moisture sensors."""

    _attr_translation_key = "unavailable_sensors"

    def __init__(self, manager: PlantMonitorManager) -> None:
        """Initialize the unavailable-sensors sensor."""
        super().__init__(
            manager,
            "unavailable_sensors",
        )

    @property
    def native_value(self) -> int:
        """Return the number of unavailable moisture sensors."""
        return self.manager.unavailable_sensor_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return unavailable and invalid source sensors."""
        return {
            ATTR_UNAVAILABLE_SENSORS: (
                self.manager.unavailable_sensor_ids
            ),
            ATTR_INVALID_SENSOR_COUNT: (
                self.manager.invalid_sensor_count
            ),
            ATTR_INVALID_SENSORS: self.manager.invalid_sensor_ids,
        }


class PlantSoilMoistureSensor(
    PlantMonitorPlantEntity,
    SensorEntity,
):
    """Report the current validated soil moisture of one plant."""

    _attr_device_class = SensorDeviceClass.MOISTURE
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "soil_moisture"

    def __init__(
        self,
        manager: PlantMonitorManager,
        plant_state: PlantState,
    ) -> None:
        """Initialize a plant soil-moisture sensor."""
        super().__init__(
            manager,
            plant_state,
            "soil_moisture",
        )

    @property
    def available(self) -> bool:
        """Return whether a valid current moisture value exists."""
        return self.plant_state.moisture is not None

    @property
    def native_value(self) -> float | None:
        """Return the validated current soil moisture."""
        return self.plant_state.moisture


class PlantStatusSensor(
    PlantMonitorPlantEntity,
    SensorEntity,
):
    """Report the current status of one monitored plant."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [status.value for status in PlantStatus]
    _attr_translation_key = "status"

    def __init__(
        self,
        manager: PlantMonitorManager,
        plant_state: PlantState,
    ) -> None:
        """Initialize a plant status sensor."""
        super().__init__(
            manager,
            plant_state,
            "status",
        )

    @property
    def native_value(self) -> str:
        """Return the current plant status."""
        return self.plant_state.status.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return source-sensor and watering-state information."""
        return {
            ATTR_MOISTURE_SENSOR: (
                self.plant_state.config.moisture_sensor
            ),
            ATTR_WATERING_NEEDED: (
                self.plant_state.watering_needed
            ),
        }


class PlantDryBelowSensor(
    PlantMonitorPlantEntity,
    SensorEntity,
):
    """Report the configured dry threshold of one plant."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_translation_key = "dry_below"

    def __init__(
        self,
        manager: PlantMonitorManager,
        plant_state: PlantState,
    ) -> None:
        """Initialize a plant dry-threshold sensor."""
        super().__init__(
            manager,
            plant_state,
            "dry_below",
        )

    @property
    def native_value(self) -> float:
        """Return the configured dry threshold."""
        return self.plant_state.config.dry_below


class PlantClearAtSensor(
    PlantMonitorPlantEntity,
    SensorEntity,
):
    """Report the configured alert-clear threshold of one plant."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_translation_key = "clear_at"

    def __init__(
        self,
        manager: PlantMonitorManager,
        plant_state: PlantState,
    ) -> None:
        """Initialize a plant alert-clear threshold sensor."""
        super().__init__(
            manager,
            plant_state,
            "clear_at",
        )

    @property
    def native_value(self) -> float:
        """Return the configured alert-clear threshold."""
        return self.plant_state.config.clear_at
