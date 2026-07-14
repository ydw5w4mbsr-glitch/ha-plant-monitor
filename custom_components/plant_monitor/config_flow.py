"""Config flow for the Plant Monitor integration."""

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
)

from .const import (
    CONF_CLEAR_AT,
    CONF_DRY_BELOW,
    CONF_MOISTURE_SENSOR,
    DEFAULT_CLEAR_AT,
    DEFAULT_DRY_BELOW,
    DOMAIN,
    MAX_MOISTURE,
    MIN_MOISTURE,
    SUBENTRY_TYPE_PLANT,
)


class PlantMonitorConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle the main Plant Monitor config flow."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Create the central Plant Monitor config entry."""
        if self._async_current_entries():
            return self.async_abort(
                reason="single_instance_allowed",
            )

        if user_input is not None:
            return self.async_create_entry(
                title="Plant Monitor",
                data={},
            )

        return self.async_show_form(step_id="user")

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls,
        config_entry: ConfigEntry,
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return supported config subentry types."""
        return {
            SUBENTRY_TYPE_PLANT: PlantConfigSubentryFlow,
        }


class PlantConfigSubentryFlow(ConfigSubentryFlow):
    """Handle adding and editing monitored plants."""

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> SubentryFlowResult:
        """Add a monitored plant."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = self._validate_input(user_input)

            if not errors:
                title = str(user_input[CONF_NAME]).strip()
                data = _subentry_data(user_input)

                return self.async_create_entry(
                    title=title,
                    data=data,
                    unique_id=data[CONF_MOISTURE_SENSOR],
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_plant_schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> SubentryFlowResult:
        """Edit an existing monitored plant."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()

        defaults: dict[str, Any] = {
            CONF_NAME: subentry.title,
            **subentry.data,
        }
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = self._validate_input(
                user_input,
                excluded_subentry_id=subentry.subentry_id,
            )

            if not errors:
                title = str(user_input[CONF_NAME]).strip()
                data = _subentry_data(user_input)

                return self.async_update_reload_and_abort(
                    entry,
                    subentry,
                    title=title,
                    data=data,
                    unique_id=data[CONF_MOISTURE_SENSOR],
                    reload_even_if_entry_is_unchanged=False,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_plant_schema(
                user_input if user_input is not None else defaults
            ),
            errors=errors,
        )

    def _validate_input(
        self,
        user_input: Mapping[str, Any],
        *,
        excluded_subentry_id: str | None = None,
    ) -> dict[str, str]:
        """Validate plant configuration."""
        errors: dict[str, str] = {}

        name = str(user_input[CONF_NAME]).strip()
        moisture_sensor = str(
            user_input[CONF_MOISTURE_SENSOR]
        )
        dry_below = float(user_input[CONF_DRY_BELOW])
        clear_at = float(user_input[CONF_CLEAR_AT])

        if not name:
            errors[CONF_NAME] = "name_required"

        if dry_below >= clear_at:
            errors["base"] = "invalid_thresholds"

        entry = self._get_entry()

        sensor_already_used = any(
            subentry.subentry_type == SUBENTRY_TYPE_PLANT
            and subentry.subentry_id != excluded_subentry_id
            and subentry.data.get(CONF_MOISTURE_SENSOR)
            == moisture_sensor
            for subentry in entry.subentries.values()
        )

        if sensor_already_used:
            errors[CONF_MOISTURE_SENSOR] = (
                "sensor_already_used"
            )

        return errors


def _subentry_data(
    user_input: Mapping[str, Any],
) -> dict[str, Any]:
    """Return normalized config subentry data."""
    return {
        CONF_MOISTURE_SENSOR: str(
            user_input[CONF_MOISTURE_SENSOR]
        ),
        CONF_DRY_BELOW: float(
            user_input[CONF_DRY_BELOW]
        ),
        CONF_CLEAR_AT: float(
            user_input[CONF_CLEAR_AT]
        ),
    }


def _plant_schema(
    defaults: Mapping[str, Any] | None = None,
) -> vol.Schema:
    """Return the plant configuration form schema."""
    values = defaults or {}

    schema: dict[Any, Any] = {
        vol.Required(
            CONF_NAME,
            default=values.get(CONF_NAME, ""),
        ): str,
        vol.Required(
            CONF_DRY_BELOW,
            default=values.get(
                CONF_DRY_BELOW,
                DEFAULT_DRY_BELOW,
            ),
        ): vol.All(
            vol.Coerce(float),
            vol.Range(
                min=MIN_MOISTURE,
                max=MAX_MOISTURE,
            ),
        ),
        vol.Required(
            CONF_CLEAR_AT,
            default=values.get(
                CONF_CLEAR_AT,
                DEFAULT_CLEAR_AT,
            ),
        ): vol.All(
            vol.Coerce(float),
            vol.Range(
                min=MIN_MOISTURE,
                max=MAX_MOISTURE,
            ),
        ),
    }

    moisture_sensor = values.get(CONF_MOISTURE_SENSOR)

    if moisture_sensor:
        sensor_field = vol.Required(
            CONF_MOISTURE_SENSOR,
            default=moisture_sensor,
        )
    else:
        sensor_field = vol.Required(
            CONF_MOISTURE_SENSOR,
        )

    schema[sensor_field] = EntitySelector(
        EntitySelectorConfig(
            domain=Platform.SENSOR,
        )
    )

    return vol.Schema(schema)
