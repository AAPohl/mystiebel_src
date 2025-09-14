"""Diagnostics support for MyStiebel integration."""

from __future__ import annotations

import logging
import re
from collections import deque
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class LogCapture(logging.Handler):
    """Capture log records for diagnostics."""

    def __init__(self, max_records: int = 50):
        """Initialize the log capture handler."""
        super().__init__()
        self.records: deque[logging.LogRecord] = deque(maxlen=max_records)

    def emit(self, record: logging.LogRecord) -> None:
        """Store the log record."""
        self.records.append(record)

    def get_logs(self) -> list[dict[str, Any]]:
        """Get formatted log records."""
        logs = []
        for record in self.records:
            if record.levelno >= logging.WARNING:  # Only include warnings and errors
                logs.append({
                    "timestamp": record.created,
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                })
        return logs


# Create a global log capture instance
LOG_CAPTURE = LogCapture(max_records=100)

# Add the handler to all MyStiebel loggers
# Set a filter level to only capture warnings and errors
LOG_CAPTURE.setLevel(logging.WARNING)

for logger_name in [
    "custom_components.mystiebel",
    "custom_components.mystiebel.websocket_client",
    "custom_components.mystiebel.coordinator",
    "custom_components.mystiebel.mystiebel_auth",
]:
    logger = logging.getLogger(logger_name)
    # Check if handler already added to avoid duplicates
    if LOG_CAPTURE not in logger.handlers:
        logger.addHandler(LOG_CAPTURE)

TO_REDACT = {
    "username",
    "password",
    "client_id",
    "token",
    "credential_id",
    "installation_id",  # Will partially redact
    "mac_address",  # Will partially redact
}


def _partial_redact(value: Any, visible_chars: int = 4) -> str:
    """Partially redact a value, showing only first few characters."""
    if value is None:
        return "**REDACTED**"

    # Convert to string if not already
    value_str = str(value)

    if len(value_str) <= visible_chars:
        return "**REDACTED**"
    return f"{value_str[:visible_chars]}...REDACTED"


def _get_entity_statistics(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, Any]:
    """Get entity statistics for the config entry."""
    entity_registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)

    entity_counts = {}
    enabled_counts = {}
    for entity in entities:
        platform = entity.domain
        entity_counts[platform] = entity_counts.get(platform, 0) + 1
        if not entity.disabled:
            enabled_counts[platform] = enabled_counts.get(platform, 0) + 1

    return {
        "total_entities": len(entities),
        "entities_by_platform": entity_counts,
        "enabled_by_platform": enabled_counts,
    }


def _get_parameters_info(coordinator) -> dict[str, Any]:
    """Extract parameter information from coordinator."""
    parameters_info = {}
    if hasattr(coordinator, "parameters") and coordinator.parameters:
        for param_id, param_data in coordinator.parameters.items():
            if isinstance(param_data, dict):
                parameters_info[str(param_id)] = {
                    "name": param_data.get("name", "Unknown"),
                    "data_type": param_data.get("data_type"),
                    "unit": param_data.get("unit"),
                    "visible": param_data.get("visible", False),
                    "enabled": param_data.get("enabled", False),
                    "writable": param_data.get("writable", False),
                }
    return parameters_info


def _get_current_values(coordinator) -> dict[str, Any]:
    """Extract current values from coordinator."""
    current_values = {}
    if hasattr(coordinator, "data") and coordinator.data:
        for data_id, value in coordinator.data.items():
            # Only include non-sensitive numeric/state values
            if isinstance(value, (int, float, bool)):
                current_values[str(data_id)] = value
            elif isinstance(value, str) and len(value) < 50:  # Short strings only
                current_values[str(data_id)] = value
    return current_values


def _get_alarms_info(coordinator) -> dict[str, Any]:
    """Extract alarm information from coordinator."""
    alarms_info = {}
    if hasattr(coordinator, "alarms") and coordinator.alarms:
        for alarm_id, alarm_data in coordinator.alarms.items():
            if isinstance(alarm_data, dict):
                alarms_info[str(alarm_id)] = {
                    "name": alarm_data.get("name", "Unknown"),
                    "active": alarm_data.get("active", False),
                    "timestamp": str(alarm_data.get("timestamp")) if alarm_data.get("timestamp") else None,
                }
    return alarms_info


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Get entity statistics
    entity_statistics = _get_entity_statistics(hass, config_entry)

    # Get device registry info
    device_registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)

    # Prepare configuration data (with sensitive data redacted)
    config_data = dict(config_entry.data)
    # Partially redact installation_id if present
    if "installation_id" in config_data:
        config_data["installation_id"] = _partial_redact(config_data["installation_id"])

    # Prepare device info
    device_info = {
        "name": coordinator.device_name,
        "model": coordinator.model,
        "sw_version": coordinator.sw_version,
        "mac_address": _partial_redact(coordinator.mac_address) if coordinator.mac_address else None,
    }

    # Get diagnostics components
    parameters_info = _get_parameters_info(coordinator)
    current_values = _get_current_values(coordinator)
    alarms_info = _get_alarms_info(coordinator)

    # WebSocket connection status
    ws_status = {
        "connected": coordinator.ws is not None if hasattr(coordinator, "ws") else False,
        "ready": coordinator.ready_event.is_set() if hasattr(coordinator, "ready_event") else False,
        "last_update": str(coordinator.last_update) if hasattr(coordinator, "last_update") else None,
    }

    # Options from config entry
    options = {
        "bath_volume": config_entry.options.get("bath_volume", 180),
        "shower_output": config_entry.options.get("shower_output", 12),
    }

    # Get recent error logs
    recent_logs = LOG_CAPTURE.get_logs()

    # Redact sensitive information from log messages
    redacted_logs = []
    for log in recent_logs:
        log_copy = log.copy()
        # Redact sensitive patterns in messages
        message = log_copy["message"]

        # Redact specific sensitive patterns
        # Redact tokens (usually long alphanumeric strings)
        message = re.sub(r'token["\s:=]+["\'`]?[\w\-\.]+["\'`]?', 'token=**REDACTED**', message, flags=re.IGNORECASE)
        # Redact passwords
        message = re.sub(r'password["\s:=]+["\'`]?[^"\'\s]+["\'`]?', 'password=**REDACTED**', message, flags=re.IGNORECASE)
        # Redact client IDs
        message = re.sub(r'client_id["\s:=]+["\'`]?[^"\'\s]+["\'`]?', 'client_id=**REDACTED**', message, flags=re.IGNORECASE)
        # Redact installation IDs (keep first 4 chars)
        message = re.sub(r'installation[_\s]?id["\s:=]+["\'`]?(\d{4})\d+["\'`]?', r'installation_id=\1...REDACTED', message, flags=re.IGNORECASE)

        log_copy["message"] = message
        redacted_logs.append(log_copy)

    # Compile diagnostics data
    diagnostics_data = {
        "config_entry": async_redact_data(config_data, TO_REDACT),
        "device_info": device_info,
        "options": options,
        "websocket_status": ws_status,
        "entity_statistics": entity_statistics,
        "registered_devices": len(devices),
        "parameters_count": len(parameters_info),
        "parameters_sample": dict(list(parameters_info.items())[:10]),  # First 10 parameters as sample
        "current_values_count": len(current_values),
        "current_values_sample": dict(list(current_values.items())[:20]),  # First 20 values as sample
        "active_alarms_count": sum(1 for a in alarms_info.values() if a.get("active")),
        "alarms": alarms_info if alarms_info else "No alarms",
        "coordinator_state": {
            "has_data": bool(coordinator.data),
            "has_parameters": bool(coordinator.parameters),
            "active_fields_count": len(coordinator.active_fields) if hasattr(coordinator, "active_fields") else 0,
        },
        "recent_errors_and_warnings": redacted_logs[-20:] if redacted_logs else "No recent warnings or errors",
        "error_count": len(redacted_logs),
    }

    return diagnostics_data
