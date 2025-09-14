"""Switch platform for MyStiebel integration."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, ESSENTIAL_CONTROLS, EXCLUDED_INDIVIDUAL_SENSORS
from .sensor import MyStiebelBaseEntity

_LOGGER = logging.getLogger(__name__)


def _setup_switch_entities(coordinator):
    params_to_check, fields_to_create = (
        coordinator.parameters,
        coordinator.active_fields,
    )
    switches = []
    for idx in fields_to_create:
        # Skip excluded sensors (e.g., those combined into other entities)
        if idx in EXCLUDED_INDIVIDUAL_SENSORS:
            continue

        param = params_to_check.get(idx)
        if (
            param
            and "read_write" in param.get("access", [])
            and param.get("choicelist_id") == "State_on_off"
        ):
            switches.append(MyStiebelSwitch(coordinator, idx, param))
    return switches


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    switches = await hass.async_add_executor_job(_setup_switch_entities, coordinator)
    async_add_entities(switches, True)


class MyStiebelSwitch(MyStiebelBaseEntity, SwitchEntity):
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, register_index, param) -> None:
        super().__init__(coordinator, param)
        self._register_index = register_index
        self._attr_unique_id = f"mystiebel_{register_index}_switch"
        self._attr_name = param.get("display_name")
        self._attr_icon = "mdi:toggle-switch"
        self._attr_entity_category = EntityCategory.CONFIG
        if register_index in ESSENTIAL_CONTROLS:
            self._attr_entity_registry_enabled_default = True

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self):
        try:
            return float(self.coordinator.data.get(self._register_index)) == 1.0
        except (ValueError, TypeError, AttributeError):
            return False

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_value(self._register_index, 1)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_value(self._register_index, 0)
