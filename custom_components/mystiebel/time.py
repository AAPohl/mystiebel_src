"""Time platform for MyStiebel integration."""

import logging
from datetime import datetime, time, timedelta

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
    """Encode start and end time objects into the integer format.

    Note: Times are rounded to the nearest 15-minute interval.
    """
    if not start_time or not end_time:
        return 0

    # Round to nearest 15-minute interval instead of truncating
    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = end_time.hour * 60 + end_time.minute

    # Round to nearest 15 minutes
    start_interval = round(start_minutes / 15)
    end_interval = round(end_minutes / 15)

    # Log if rounding occurred
    if start_minutes % 15 != 0:
        rounded_start = (start_interval * 15) % (24 * 60)
        _LOGGER.info(
            "Start time %s rounded to %02d:%02d (nearest 15-minute interval)",
            start_time.strftime("%H:%M"),
            rounded_start // 60,
            rounded_start % 60,
        )

    if end_minutes % 15 != 0:
        rounded_end = (end_interval * 15) % (24 * 60)
        _LOGGER.info(
            "End time %s rounded to %02d:%02d (nearest 15-minute interval)",
            end_time.strftime("%H:%M"),
            rounded_end // 60,
            rounded_end % 60,
        )

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

    # Add the combined hygiene time entity if the parameters exist
    if (
        2477 in coordinator.active_fields and
        2483 in coordinator.active_fields
    ):
        entities.append(MyStiebelHygieneTimeEntity(coordinator))
        _LOGGER.debug("Added combined hygiene time entity")

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
        """Set a new time.

        Note: The value will be rounded to the nearest 15-minute interval.
        """
        encoded_value = self.coordinator.data.get(self._register_index, 0)
        current_start, current_end = _decode_time_pair(int(float(encoded_value)))

        new_start = value if self._time_type == "start" else current_start
        new_end = value if self._time_type == "end" else current_end

        # Warn user if time will be rounded
        minutes = value.hour * 60 + value.minute
        if minutes % 15 != 0:
            rounded_minutes = round(minutes / 15) * 15
            rounded_time = (
                datetime.min + timedelta(minutes=rounded_minutes % (24 * 60))
            ).time()
            _LOGGER.info(
                "Time %s will be rounded to %s for %s",
                value.strftime("%H:%M"),
                rounded_time.strftime("%H:%M"),
                self._attr_name,
            )

        new_encoded_value = _encode_time_pair(new_start, new_end)
        await self.coordinator.async_set_value(self._register_index, new_encoded_value)


class MyStiebelHygieneTimeEntity(CoordinatorEntity, TimeEntity):
    """Combined time entity for hygiene program start time."""

    def __init__(self, coordinator) -> None:
        """Initialize the hygiene time entity."""
        super().__init__(coordinator)
        self._hour_register = 2483  # Hours parameter
        self._minute_register = 2477  # Minutes parameter

        self._attr_unique_id = "mystiebel_hygiene_start_time"
        self._attr_name = "Weekly hygiene program start time"
        self._attr_icon = "mdi:clock-check"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_entity_registry_enabled_default = True  # Enable by default as it's useful

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.installation_id)},
            name=coordinator.device_name,
            manufacturer="Stiebel Eltron",
            model=coordinator.model,
        )

        if coordinator.sw_version:
            self._attr_device_info["sw_version"] = coordinator.sw_version

        if coordinator.mac_address:
            self._attr_device_info["connections"] = {
                (CONNECTION_NETWORK_MAC, coordinator.mac_address)
            }

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> time | None:
        """Get current time from both hour and minute parameters."""
        hours = self.coordinator.data.get(self._hour_register)
        minutes = self.coordinator.data.get(self._minute_register)

        if hours is None or minutes is None:
            return None

        try:
            # Convert to integers and create time object
            hour_val = int(float(hours))
            minute_val = int(float(minutes))

            # Validate ranges
            if 0 <= hour_val <= 23 and 0 <= minute_val <= 59:
                return time(hour=hour_val, minute=minute_val)
            else:
                _LOGGER.warning(
                    "Invalid time values: hours=%d, minutes=%d",
                    hour_val,
                    minute_val
                )
                return None
        except (ValueError, TypeError) as e:
            _LOGGER.error("Error parsing hygiene time values: %s", e)
            return None

    async def async_set_value(self, value: time) -> None:
        """Set both hour and minute parameters."""
        _LOGGER.info(
            "Setting hygiene program start time to %s",
            value.strftime("%H:%M")
        )

        # Update both parameters
        await self.coordinator.async_set_value(self._hour_register, value.hour)
        await self.coordinator.async_set_value(self._minute_register, value.minute)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self._hour_register in self.coordinator.data
            and self._minute_register in self.coordinator.data
        )
