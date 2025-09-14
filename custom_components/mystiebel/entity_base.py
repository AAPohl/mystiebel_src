"""Base entity classes for MyStiebel integration."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ESSENTIAL_CONTROLS,
    ESSENTIAL_SENSORS,
    EXCLUDED_INDIVIDUAL_SENSORS,
    NUMERIC_CONTROL_TYPES,
)

_LOGGER = logging.getLogger(__name__)


class MyStiebelEntity(CoordinatorEntity):
    """Base entity class for MyStiebel integration."""

    def __init__(
        self,
        coordinator,
        register_index: int,
        param: dict[str, Any],
        entity_suffix: str = "",
    ) -> None:
        """Initialize the MyStiebel entity."""
        super().__init__(coordinator)
        self._register_index = register_index
        self._param = param
        self._entity_suffix = entity_suffix

        # Set common attributes
        self._attr_unique_id = f"mystiebel_{register_index}{entity_suffix}"
        self._attr_name = param.get("display_name", f"Parameter {register_index}")
        self._attr_device_info = self._create_device_info()

        # Set entity category based on parameter group
        group = param.get("group", "")
        if "ADVANCED" in group or "SERVICE" in group:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif "CONFIG" in group or "SETTINGS" in group:
            self._attr_entity_category = EntityCategory.CONFIG

        # Determine if entity should be enabled by default
        self._attr_entity_registry_enabled_default = self._should_enable_by_default()

    def _create_device_info(self) -> DeviceInfo:
        """Create device info for the entity."""
        device_info = DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.installation_id)},
            name=self.coordinator.device_name,
            manufacturer="Stiebel Eltron",
            model=self.coordinator.model,
        )

        if self.coordinator.sw_version:
            device_info["sw_version"] = self.coordinator.sw_version

        if self.coordinator.mac_address:
            device_info["connections"] = {
                (CONNECTION_NETWORK_MAC, self.coordinator.mac_address)
            }

        return device_info

    def _should_enable_by_default(self) -> bool:
        """Determine if entity should be enabled by default."""
        # Check if it's an essential sensor or control
        if self._register_index in ESSENTIAL_SENSORS:
            return True
        if self._register_index in ESSENTIAL_CONTROLS:
            return True
        # Excluded individual sensors are disabled
        if self._register_index in EXCLUDED_INDIVIDUAL_SENSORS:
            return False
        # All other entities are disabled by default
        return False

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self._register_index in self.coordinator.data
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


def setup_entities_from_parameters(
    hass: HomeAssistant,
    coordinator,
    entity_class,
    filter_func=None,
    additional_entities=None,
) -> list:
    """Set up entities from parameters with optional filtering.

    Args:
        hass: Home Assistant instance
        coordinator: Data coordinator
        entity_class: The entity class to instantiate
        filter_func: Optional function to filter parameters
        additional_entities: Optional list of additional entities to add

    Returns:
        List of entity instances
    """
    entities = []
    params_to_check = coordinator.parameters
    fields_to_create = coordinator.active_fields

    for idx in fields_to_create:
        # Skip excluded sensors
        if idx in EXCLUDED_INDIVIDUAL_SENSORS:
            continue

        param = params_to_check.get(idx)
        if not param:
            continue

        # Apply filter function if provided
        if filter_func and not filter_func(idx, param):
            continue

        # Create the entity
        entities.append(entity_class(coordinator, idx, param))

    # Add any additional entities
    if additional_entities:
        entities.extend(additional_entities)

    return entities


def is_control_entity(param: dict[str, Any]) -> bool:
    """Check if a parameter should be a control entity."""
    is_writable = "read_write" in param.get("access", [])
    if not is_writable:
        return False

    # Check for control entity types
    is_time_control = param.get("data_type") == "SwitchingTime"
    has_choices = bool(param.get("choices"))
    is_numeric_with_range = (
        param.get("data_type") in NUMERIC_CONTROL_TYPES
        and param.get("min") is not None
    )

    return is_time_control or has_choices or is_numeric_with_range


def is_binary_sensor(param: dict[str, Any]) -> bool:
    """Check if a parameter should be a binary sensor."""
    return param.get("choicelist_id") == "State_on_off"
