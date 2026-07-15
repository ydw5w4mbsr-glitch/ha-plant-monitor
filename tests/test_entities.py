"""Tests for Plant Monitor entities."""

from types import SimpleNamespace
from typing import cast

import pytest
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.entity import EntityCategory

from custom_components.plant_monitor.binary_sensor import (
    PlantWateringNeededBinarySensor,
)
from custom_components.plant_monitor.const import DOMAIN
from custom_components.plant_monitor.entity import (
    PlantMonitorPlantEntity,
)
from custom_components.plant_monitor.manager import PlantMonitorManager
from custom_components.plant_monitor.models import (
    PlantConfig,
    PlantState,
    PlantStatus,
)
from custom_components.plant_monitor.sensor import (
    PlantClearAtSensor,
    PlantDryBelowSensor,
    PlantSoilMoistureSensor,
    PlantStatusSensor,
)

ENTRY_ID = "entry-1"
SUBENTRY_ID = "plant-1"
SOURCE_ENTITY_ID = "sensor.test_soil_moisture"


def _manager() -> PlantMonitorManager:
    """Create the minimal manager required by entity constructors."""
    return cast(
        PlantMonitorManager,
        SimpleNamespace(entry_id=ENTRY_ID),
    )


def _plant_state(
    *,
    status: PlantStatus = PlantStatus.OK,
    watering_needed: bool = False,
    moisture: float | None = 31.0,
) -> PlantState:
    """Create a plant runtime state for entity tests."""
    return PlantState(
        config=PlantConfig(
            subentry_id=SUBENTRY_ID,
            name="Test Plant",
            moisture_sensor=SOURCE_ENTITY_ID,
            dry_below=25.0,
            clear_at=35.0,
        ),
        status=status,
        watering_needed=watering_needed,
        moisture=moisture,
    )


def _plant_entities(
    manager: PlantMonitorManager,
    plant_state: PlantState,
) -> list[PlantMonitorPlantEntity]:
    """Create all entities belonging to one logical plant."""
    return [
        PlantSoilMoistureSensor(manager, plant_state),
        PlantStatusSensor(manager, plant_state),
        PlantWateringNeededBinarySensor(manager, plant_state),
        PlantDryBelowSensor(manager, plant_state),
        PlantClearAtSensor(manager, plant_state),
    ]


def test_per_plant_entity_unique_ids() -> None:
    """Use stable entry, subentry and entity keys in unique IDs."""
    manager = _manager()
    plant_state = _plant_state()

    entities = _plant_entities(manager, plant_state)

    assert [entity.unique_id for entity in entities] == [
        f"{ENTRY_ID}_{SUBENTRY_ID}_soil_moisture",
        f"{ENTRY_ID}_{SUBENTRY_ID}_status",
        f"{ENTRY_ID}_{SUBENTRY_ID}_watering_needed",
        f"{ENTRY_ID}_{SUBENTRY_ID}_dry_below",
        f"{ENTRY_ID}_{SUBENTRY_ID}_clear_at",
    ]


def test_per_plant_entities_share_logical_device() -> None:
    """Attach all per-plant entities to the same logical plant device."""
    manager = _manager()
    plant_state = _plant_state()

    entities = _plant_entities(manager, plant_state)

    for entity in entities:
        device_info = entity.device_info

        assert device_info is not None
        assert device_info["identifiers"] == {
            (
                DOMAIN,
                f"{ENTRY_ID}_{SUBENTRY_ID}",
            )
        }
        assert device_info["name"] == "Test Plant"
        assert device_info["manufacturer"] == "Plant Monitor"
        assert device_info["model"] == "Monitored plant"


def test_soil_moisture_sensor() -> None:
    """Expose the validated moisture value with sensor metadata."""
    entity = PlantSoilMoistureSensor(
        _manager(),
        _plant_state(moisture=31.5),
    )

    assert entity.native_value == 31.5
    assert entity.available is True
    assert entity.native_unit_of_measurement == PERCENTAGE
    assert entity.device_class == SensorDeviceClass.MOISTURE
    assert entity.state_class == SensorStateClass.MEASUREMENT


@pytest.mark.parametrize(
    "status",
    [
        PlantStatus.UNAVAILABLE,
        PlantStatus.INVALID,
    ],
)
def test_soil_moisture_sensor_unavailable_without_valid_value(
    status: PlantStatus,
) -> None:
    """Make projected moisture unavailable without a valid value."""
    entity = PlantSoilMoistureSensor(
        _manager(),
        _plant_state(
            status=status,
            moisture=None,
        ),
    )

    assert entity.native_value is None
    assert entity.available is False


@pytest.mark.parametrize(
    ("status", "watering_needed"),
    [
        (PlantStatus.OK, False),
        (PlantStatus.DRY, True),
        (PlantStatus.UNAVAILABLE, True),
        (PlantStatus.INVALID, False),
    ],
)
def test_status_sensor(
    status: PlantStatus,
    watering_needed: bool,
) -> None:
    """Expose public status and only non-redundant attributes."""
    entity = PlantStatusSensor(
        _manager(),
        _plant_state(
            status=status,
            watering_needed=watering_needed,
            moisture=None,
        ),
    )

    assert entity.native_value == status.value
    assert entity.extra_state_attributes == {
        "moisture_sensor": SOURCE_ENTITY_ID,
        "watering_needed": watering_needed,
    }


@pytest.mark.parametrize(
    "watering_needed",
    [False, True],
)
def test_watering_needed_binary_sensor(
    watering_needed: bool,
) -> None:
    """Expose the retained watering decision."""
    entity = PlantWateringNeededBinarySensor(
        _manager(),
        _plant_state(
            watering_needed=watering_needed,
        ),
    )

    assert entity.is_on is watering_needed
    assert entity.extra_state_attributes == {
        "moisture_sensor": SOURCE_ENTITY_ID,
    }


def test_threshold_sensors() -> None:
    """Expose configured thresholds as diagnostic percentages."""
    manager = _manager()
    plant_state = _plant_state()

    dry_below = PlantDryBelowSensor(manager, plant_state)
    clear_at = PlantClearAtSensor(manager, plant_state)

    assert dry_below.native_value == 25.0
    assert dry_below.native_unit_of_measurement == PERCENTAGE
    assert dry_below.entity_category == EntityCategory.DIAGNOSTIC

    assert clear_at.native_value == 35.0
    assert clear_at.native_unit_of_measurement == PERCENTAGE
    assert clear_at.entity_category == EntityCategory.DIAGNOSTIC


@pytest.mark.parametrize(
    ("status", "watering_needed"),
    [
        (PlantStatus.UNAVAILABLE, True),
        (PlantStatus.INVALID, True),
    ],
)
def test_source_failure_remains_visible(
    status: PlantStatus,
    watering_needed: bool,
) -> None:
    """Keep status and retained watering decision visible on failure."""
    manager = _manager()
    plant_state = _plant_state(
        status=status,
        watering_needed=watering_needed,
        moisture=None,
    )

    moisture = PlantSoilMoistureSensor(manager, plant_state)
    status_entity = PlantStatusSensor(manager, plant_state)
    watering = PlantWateringNeededBinarySensor(
        manager,
        plant_state,
    )

    assert moisture.available is False
    assert status_entity.native_value == status.value
    assert watering.is_on is watering_needed