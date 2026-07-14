"""Runtime manager for the Plant Monitor integration."""

from collections import defaultdict
from collections.abc import Callable
import math
from typing import TypedDict

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .models import PlantConfig, PlantState, PlantStatus

_STORAGE_VERSION = 1
_STORAGE_SAVE_DELAY = 1.0


class PlantMonitorStorageData(TypedDict):
    """Persisted Plant Monitor runtime data."""

    watering_needed: dict[str, bool]


ManagerListener = Callable[[], None]


class PlantMonitorManager:
    """Manage monitored plants and their runtime state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        plants: list[PlantConfig],
    ) -> None:
        """Initialize the Plant Monitor manager."""
        self.hass = hass
        self.entry_id = entry_id

        self._plants: dict[str, PlantState] = {
            plant.subentry_id: PlantState(config=plant) for plant in plants
        }

        self._plants_by_sensor: defaultdict[str, list[PlantState]] = defaultdict(list)
        for plant_state in self._plants.values():
            self._plants_by_sensor[
                plant_state.config.moisture_sensor
            ].append(plant_state)

        self._listeners: set[ManagerListener] = set()
        self._unsub_state_change: CALLBACK_TYPE | None = None
        self._started = False

        self._store = Store[PlantMonitorStorageData](
            hass,
            _STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}",
        )

    @property
    def plant_states(self) -> tuple[PlantState, ...]:
        """Return all plant runtime states."""
        return tuple(self._plants.values())

    @property
    def watering_needed(self) -> bool:
        """Return whether at least one plant needs watering."""
        return any(plant.watering_needed for plant in self._plants.values())

    @property
    def dry_plant_count(self) -> int:
        """Return the number of plants that need watering."""
        return sum(
            plant.watering_needed for plant in self._plants.values()
        )

    @property
    def dry_plant_names(self) -> list[str]:
        """Return names of plants that need watering."""
        return [
            plant.config.name
            for plant in self._plants.values()
            if plant.watering_needed
        ]

    @property
    def unavailable_sensor_count(self) -> int:
        """Return the number of unavailable moisture sensors."""
        return sum(
            plant.status is PlantStatus.UNAVAILABLE
            for plant in self._plants.values()
        )

    @property
    def unavailable_sensor_ids(self) -> list[str]:
        """Return unavailable moisture sensor entity IDs."""
        return [
            plant.config.moisture_sensor
            for plant in self._plants.values()
            if plant.status is PlantStatus.UNAVAILABLE
        ]

    @property
    def invalid_sensor_count(self) -> int:
        """Return the number of invalid moisture sensor values."""
        return sum(
            plant.status is PlantStatus.INVALID
            for plant in self._plants.values()
        )

    @property
    def invalid_sensor_ids(self) -> list[str]:
        """Return moisture sensor entity IDs with invalid values."""
        return [
            plant.config.moisture_sensor
            for plant in self._plants.values()
            if plant.status is PlantStatus.INVALID
        ]

    def get_plant_state(self, subentry_id: str) -> PlantState:
        """Return the runtime state for one plant."""
        return self._plants[subentry_id]

    async def async_start(self) -> None:
        """Restore state and start monitoring moisture sensors."""
        if self._started:
            return

        stored_data = await self._store.async_load()
        restored_states = self._extract_restored_states(stored_data)

        for subentry_id, plant_state in self._plants.items():
            restored_watering_needed = restored_states.get(subentry_id)
            if isinstance(restored_watering_needed, bool):
                plant_state.watering_needed = restored_watering_needed

        if self._plants_by_sensor:
            self._unsub_state_change = async_track_state_change_event(
                self.hass,
                list(self._plants_by_sensor),
                self._async_handle_state_change,
            )

        for plant_state in self._plants.values():
            current_state = self.hass.states.get(
                plant_state.config.moisture_sensor
            )
            self._async_update_plant(
                plant_state,
                current_state,
                notify=False,
            )

        self._started = True
        self._async_schedule_save()
        self._async_notify_listeners()

    async def async_stop(self) -> None:
        """Stop monitoring and persist the current watering state."""
        if self._unsub_state_change is not None:
            self._unsub_state_change()
            self._unsub_state_change = None

        await self._store.async_save(self._storage_data())

        self._listeners.clear()
        self._started = False

    @callback
    def async_add_listener(
        self,
        listener: ManagerListener,
    ) -> CALLBACK_TYPE:
        """Register a listener for manager updates."""
        self._listeners.add(listener)

        @callback
        def remove_listener() -> None:
            """Remove the registered listener."""
            self._listeners.discard(listener)

        return remove_listener

    @callback
    def _async_handle_state_change(
        self,
        event: Event[EventStateChangedData],
    ) -> None:
        """Handle a moisture sensor state change."""
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]

        for plant_state in self._plants_by_sensor.get(entity_id, ()):
            self._async_update_plant(plant_state, new_state)

    @callback
    def _async_update_plant(
        self,
        plant_state: PlantState,
        source_state: State | None,
        *,
        notify: bool = True,
    ) -> None:
        """Update one plant from its source sensor state."""
        previous = (
            plant_state.status,
            plant_state.watering_needed,
            plant_state.moisture,
        )
        previous_watering_needed = plant_state.watering_needed

        if source_state is None or source_state.state in (
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
        ):
            plant_state.status = PlantStatus.UNAVAILABLE
            plant_state.moisture = None
        else:
            moisture = self._parse_moisture(source_state.state)

            if moisture is None:
                plant_state.status = PlantStatus.INVALID
                plant_state.moisture = None
            else:
                plant_state.moisture = moisture

                if moisture < plant_state.config.dry_below:
                    plant_state.watering_needed = True
                elif moisture >= plant_state.config.clear_at:
                    plant_state.watering_needed = False

                plant_state.status = (
                    PlantStatus.DRY
                    if plant_state.watering_needed
                    else PlantStatus.OK
                )

        current = (
            plant_state.status,
            plant_state.watering_needed,
            plant_state.moisture,
        )

        if current == previous:
            return

        if plant_state.watering_needed != previous_watering_needed:
            self._async_schedule_save()

        if notify:
            self._async_notify_listeners()

    @staticmethod
    def _parse_moisture(raw_state: str) -> float | None:
        """Convert a source state into a valid percentage."""
        try:
            moisture = float(raw_state)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(moisture):
            return None

        if not 0 <= moisture <= 100:
            return None

        return moisture

    @staticmethod
    def _extract_restored_states(
        stored_data: PlantMonitorStorageData | None,
    ) -> dict[str, bool]:
        """Extract valid persisted watering states."""
        if not isinstance(stored_data, dict):
            return {}

        watering_needed = stored_data.get("watering_needed")
        if not isinstance(watering_needed, dict):
            return {}

        return {
            subentry_id: value
            for subentry_id, value in watering_needed.items()
            if isinstance(subentry_id, str) and isinstance(value, bool)
        }

    @callback
    def _async_schedule_save(self) -> None:
        """Schedule persistence of the watering states."""
        self._store.async_delay_save(
            self._storage_data,
            _STORAGE_SAVE_DELAY,
        )

    @callback
    def _storage_data(self) -> PlantMonitorStorageData:
        """Return serializable runtime data."""
        return {
            "watering_needed": {
                subentry_id: plant_state.watering_needed
                for subentry_id, plant_state in self._plants.items()
            }
        }

    @callback
    def _async_notify_listeners(self) -> None:
        """Notify all registered entities about updated data."""
        for listener in tuple(self._listeners):
            listener()
