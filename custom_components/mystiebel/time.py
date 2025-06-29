"""Time platform for MyStiebel integration."""

from datetime import datetime, time, timedelta
import logging

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .sensor import MyStiebelBaseEntity

_LOGGER = logging.getLogger(__name__)


# Helper functions for encoding and decoding the time value
def _decode_time_pair(value: int) -> tuple[time | None, time | None]:
    """Decode the integer value into start and end time objects based on 15-minute intervals."""
    if value == 0:
        return None, None

    start_interval = (value >> 8) & 0xFF
    end_interval = value & 0xFF

    start_minutes = start_interval * 15
    end_minutes = end_interval * 15

    start_time = (datetime.min + timedelta(minutes=start_minutes)).time()
    end_time = (datetime.min + timedelta(minutes=end_minutes)).time()

    return start_time, end_time


def _encode_time_pair(start_time: time | None, end_time: time | None) -> int:
    """Encode start and end time objects into the integer format."""
    if not start_time or not end_time:
        return 0

    start_interval = (start_time.hour * 60 + start_time.minute) // 15
    end_interval = (end_time.hour * 60 + end_time.minute) // 15

    return (start_interval << 8) | end_interval


def _setup_time_entities(coordinator):
    """Set up time entities by iterating through all parameters."""
    params_to_check, fields_to_create = (
        coordinator.parameters,
        coordinator.active_fields,
    )
    entities = []
    for idx in fields_to_create:
        param = params_to_check.get(idx)
        if param and param.get("data_type") == "SwitchingTime":
            entities.append(MyStiebelTimeEntity(coordinator, idx, param, "start"))
            entities.append(MyStiebelTimeEntity(coordinator, idx, param, "end"))

    return entities


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up MyStiebel time entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = await hass.async_add_executor_job(_setup_time_entities, coordinator)
    async_add_entities(entities, True)


class MyStiebelTimeEntity(MyStiebelBaseEntity, TimeEntity):
    """Time entity for a MyStiebel time schedule."""

    def __init__(self, coordinator, register_index, param, time_type: str) -> None:
        """Initialize a MyStiebel time entity."""
        super().__init__(coordinator, param)
        self._register_index = register_index
        self._param = param
        self._time_type = time_type

        type_name = "Start Time" if time_type == "start" else "End Time"
        self._attr_unique_id = f"mystiebel_{register_index}_{time_type}"
        self._attr_name = f"{param.get('display_name')} {type_name}"
        self._attr_icon = "mdi:clock-start" if time_type == "start" else "mdi:clock-end"

        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_entity_registry_enabled_default = False

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> time | None:
        """Return the current time."""
        encoded_value = self.coordinator.data.get(self._register_index)
        if encoded_value is None:
            return None

        try:
            start_time, end_time = _decode_time_pair(int(float(encoded_value)))
            return start_time if self._time_type == "start" else end_time
        except (ValueError, TypeError):
            return None

    async def async_set_value(self, value: time) -> None:
        """Set a new time."""
        encoded_value = self.coordinator.data.get(self._register_index, 0)
        current_start, current_end = _decode_time_pair(int(float(encoded_value)))

        new_start = value if self._time_type == "start" else current_start
        new_end = value if self._time_type == "end" else current_end

        new_encoded_value = _encode_time_pair(new_start, new_end)
        await self.coordinator.async_set_value(self._register_index, new_encoded_value)
