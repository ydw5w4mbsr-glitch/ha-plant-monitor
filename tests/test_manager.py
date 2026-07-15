"""Tests for the Plant Monitor runtime manager."""

from unittest.mock import MagicMock

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

from custom_components.plant_monitor.manager import PlantMonitorManager
from custom_components.plant_monitor.models import (
    PlantConfig,
    PlantState,
    PlantStatus,
)

SOURCE_ENTITY_ID = "sensor.test_soil_moisture"


def _plant_state(*, watering_needed: bool = False) -> PlantState:
    """Create a plant state for manager tests."""
    return PlantState(
        config=PlantConfig(
            subentry_id="plant-1",
            name="Test Plant",
            moisture_sensor=SOURCE_ENTITY_ID,
            dry_below=25.0,
            clear_at=35.0,
        ),
        watering_needed=watering_needed,
    )


def _manager() -> PlantMonitorManager:
    """Create a manager shell without starting Home Assistant listeners."""
    manager = object.__new__(PlantMonitorManager)
    manager._async_schedule_save = MagicMock()
    manager._async_notify_listeners = MagicMock()
    return manager


def _source_state(raw_state: str | None) -> State | None:
    """Create a source state, or represent a missing source entity."""
    if raw_state is None:
        return None
    return State(SOURCE_ENTITY_ID, raw_state)


@pytest.mark.parametrize(
    (
        "initial_watering_needed",
        "raw_state",
        "expected_watering_needed",
        "expected_status",
    ),
    [
        (False, "24.9", True, PlantStatus.DRY),
        (False, "25", False, PlantStatus.OK),
        (False, "30", False, PlantStatus.OK),
        (True, "30", True, PlantStatus.DRY),
        (True, "35", False, PlantStatus.OK),
        (True, "35.1", False, PlantStatus.OK),
    ],
)
def test_watering_hysteresis(
    initial_watering_needed: bool,
    raw_state: str,
    expected_watering_needed: bool,
    expected_status: PlantStatus,
) -> None:
    """Apply both threshold boundaries and the hysteresis band."""
    manager = _manager()
    plant_state = _plant_state(
        watering_needed=initial_watering_needed,
    )

    manager._async_update_plant(
        plant_state,
        _source_state(raw_state),
    )

    assert plant_state.moisture == float(raw_state)
    assert plant_state.watering_needed is expected_watering_needed
    assert plant_state.status is expected_status

    if expected_watering_needed is initial_watering_needed:
        manager._async_schedule_save.assert_not_called()
    else:
        manager._async_schedule_save.assert_called_once_with()

    manager._async_notify_listeners.assert_called_once_with()


@pytest.mark.parametrize(
    ("raw_state", "expected_status"),
    [
        (None, PlantStatus.UNAVAILABLE),
        (STATE_UNKNOWN, PlantStatus.UNAVAILABLE),
        (STATE_UNAVAILABLE, PlantStatus.UNAVAILABLE),
        ("not-a-number", PlantStatus.INVALID),
        ("nan", PlantStatus.INVALID),
        ("inf", PlantStatus.INVALID),
        ("-inf", PlantStatus.INVALID),
        ("-0.1", PlantStatus.INVALID),
        ("100.1", PlantStatus.INVALID),
    ],
)
@pytest.mark.parametrize("initial_watering_needed", [False, True])
def test_source_failure_preserves_watering_state(
    raw_state: str | None,
    expected_status: PlantStatus,
    initial_watering_needed: bool,
) -> None:
    """Do not clear or create a watering alert when the source fails."""
    manager = _manager()
    plant_state = _plant_state(
        watering_needed=initial_watering_needed,
    )

    manager._async_update_plant(
        plant_state,
        _source_state(raw_state),
    )

    assert plant_state.moisture is None
    assert plant_state.watering_needed is initial_watering_needed
    assert plant_state.status is expected_status
    manager._async_schedule_save.assert_not_called()


@pytest.mark.parametrize(
    ("raw_state", "expected"),
    [
        ("0", 0.0),
        ("31", 31.0),
        ("31.5", 31.5),
        ("100", 100.0),
    ],
)
def test_parse_valid_moisture(
    raw_state: str,
    expected: float,
) -> None:
    """Accept finite percentages including both valid boundaries."""
    assert PlantMonitorManager._parse_moisture(raw_state) == expected


@pytest.mark.parametrize(
    "raw_state",
    [
        "",
        "not-a-number",
        "nan",
        "inf",
        "-inf",
        "-0.1",
        "100.1",
    ],
)
def test_parse_invalid_moisture(raw_state: str) -> None:
    """Reject values outside the valid percentage range."""
    assert PlantMonitorManager._parse_moisture(raw_state) is None