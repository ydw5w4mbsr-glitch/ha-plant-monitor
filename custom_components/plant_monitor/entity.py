"""Base entities for the Plant Monitor integration."""

from typing import override

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .manager import PlantMonitorManager
from .models import PlantState


class PlantMonitorEntity(Entity):
    """Base entity for Plant Monitor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        manager: PlantMonitorManager,
        unique_id_suffix: str,
    ) -> None:
        """Initialize a Plant Monitor entity."""
        self.manager = manager
        self._attr_unique_id = (
            f"{manager.entry_id}_{unique_id_suffix}"
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Register for manager updates."""
        await super().async_added_to_hass()

        self.async_on_remove(
            self.manager.async_add_listener(
                self.async_write_ha_state
            )
        )


class PlantMonitorPlantEntity(PlantMonitorEntity):
    """Base entity belonging to one monitored plant."""

    def __init__(
        self,
        manager: PlantMonitorManager,
        plant_state: PlantState,
        entity_key: str,
    ) -> None:
        """Initialize a plant entity."""
        self.plant_state = plant_state

        super().__init__(
            manager,
            (
                f"{plant_state.config.subentry_id}_"
                f"{entity_key}"
            ),
        )

        self._attr_device_info = DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    (
                        f"{manager.entry_id}_"
                        f"{plant_state.config.subentry_id}"
                    ),
                )
            },
            name=plant_state.config.name,
            manufacturer="Plant Monitor",
            model="Monitored plant",
        )
