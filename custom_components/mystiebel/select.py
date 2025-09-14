"""Select platform for MyStiebel integration."""

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, ESSENTIAL_CONTROLS, EXCLUDED_INDIVIDUAL_SENSORS
from .sensor import MyStiebelBaseEntity

_LOGGER = logging.getLogger(__name__)


def _setup_select_entities(coordinator):
    params_to_check, fields_to_create = (
        coordinator.parameters,
        coordinator.active_fields,
    )
    selects = []
    for idx in fields_to_create:
        # Skip excluded sensors (e.g., those combined into other entities)
        if idx in EXCLUDED_INDIVIDUAL_SENSORS:
            continue

        param = params_to_check.get(idx)
        if (
            param
            and "read_write" in param.get("access", [])
            and bool(param.get("choices"))
            and param.get("choicelist_id") != "State_on_off"
            and idx != 2480
        ):
            selects.append(MyStiebelSelect(coordinator, idx, param))
    return selects


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    selects = await hass.async_add_executor_job(_setup_select_entities, coordinator)
    async_add_entities(selects, True)


class MyStiebelSelect(MyStiebelBaseEntity, SelectEntity):
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, register_index, param) -> None:
        super().__init__(coordinator, param)
        self._register_index = register_index
        self._param = param
        self._attr_unique_id = f"mystiebel_{register_index}_select"
        self._attr_name = param.get("display_name")
        self._attr_icon = "mdi:form-dropdown"
        self._attr_options = list(param.get("choices", {}).values())
        self._value_to_key_map = {v: k for k, v in param.get("choices", {}).items()}
        self._attr_entity_category = EntityCategory.CONFIG
        if register_index in ESSENTIAL_CONTROLS:
            self._attr_entity_registry_enabled_default = True

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def current_option(self) -> str | None:
        value_key = self.coordinator.data.get(self._register_index)
        if value_key is None:
            return None
        try:
            lookup_key = str(int(float(value_key)))
            return self._param.get("choices", {}).get(lookup_key)
        except (ValueError, TypeError, KeyError):
            return None

    async def async_select_option(self, option: str) -> None:
        key_to_set = self._value_to_key_map.get(option)
        if key_to_set is not None:
            await self.coordinator.async_set_value(
                self._register_index, int(key_to_set)
            )
