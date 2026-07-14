"""The Plant Monitor integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CLEAR_AT,
    CONF_DRY_BELOW,
    CONF_MOISTURE_SENSOR,
    PLATFORMS,
    SUBENTRY_TYPE_PLANT,
)
from .manager import PlantMonitorManager
from .models import PlantConfig

PlantMonitorConfigEntry = ConfigEntry[PlantMonitorManager]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PlantMonitorConfigEntry,
) -> bool:
    """Set up Plant Monitor from a config entry."""
    plants = [
        PlantConfig(
            subentry_id=subentry.subentry_id,
            name=subentry.title,
            moisture_sensor=str(
                subentry.data[CONF_MOISTURE_SENSOR]
            ),
            dry_below=float(
                subentry.data[CONF_DRY_BELOW]
            ),
            clear_at=float(
                subentry.data[CONF_CLEAR_AT]
            ),
        )
        for subentry in entry.get_subentries_of_type(
            SUBENTRY_TYPE_PLANT
        )
    ]

    manager = PlantMonitorManager(
        hass,
        entry.entry_id,
        plants,
    )
    entry.runtime_data = manager

    entry.async_on_unload(
        entry.add_update_listener(_async_reload_entry)
    )

    await manager.async_start()

    try:
        await hass.config_entries.async_forward_entry_setups(
            entry,
            PLATFORMS,
        )
    except Exception:
        await manager.async_stop()
        raise

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: PlantMonitorConfigEntry,
) -> bool:
    """Unload a Plant Monitor config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )

    if unload_ok:
        await entry.runtime_data.async_stop()

    return unload_ok


async def _async_reload_entry(
    hass: HomeAssistant,
    entry: PlantMonitorConfigEntry,
) -> None:
    """Reload Plant Monitor after configuration changes."""
    await hass.config_entries.async_reload(entry.entry_id)
