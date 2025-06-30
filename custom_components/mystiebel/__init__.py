"""Integration for MyStiebel devices."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN
from .coordinator import MyStiebelCoordinator
from .mystiebel_auth import MyStiebelAuth
from .parameters import load_parameters
from .websocket_client import setup_websocket_listener

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["number", "select", "sensor", "switch", "time"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MyStiebel from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    session = aiohttp_client.async_get_clientsession(hass)

    username, password, client_id = (
        entry.data["username"],
        entry.data["password"],
        entry.data["client_id"],
    )
    installation_id = str(entry.data["installation_id"])

    auth = MyStiebelAuth(session, username, password, client_id)
    await auth.authenticate()
    token = auth.token

    installations = await auth.get_installations()
    device_data = next(
        (item for item in installations["items"] if str(item["id"]) == installation_id),
        None,
    )
    if not device_data:
        _LOGGER.error("Could not find installation with ID {installation_id}")
        return False

    device_name = f"{device_data.get('profile', {}).get('name', 'Unknown')} in {device_data.get('location', {}).get('city', 'Unknown')}"
    model = device_data.get("profile", {}).get("name", "Unknown")
    sw_version = device_data.get("firmware", {}).get("firmwareVersion")
    mac_address = device_data.get("macAddress")

    options = entry.options
    bath_volume = options.get("bath_volume", 180)
    shower_output = options.get("shower_output", 12)

    coordinator = MyStiebelCoordinator(
        hass,
        session,
        token,
        installation_id,
        client_id,
        device_name,
        model,
        sw_version,
        mac_address,
        bath_volume,
        shower_output,
    )
    hass.data[DOMAIN][entry.entry_id] = coordinator

    language = hass.config.language
    loaded_data = await hass.async_add_executor_job(load_parameters, language)

    coordinator.parameters = loaded_data.get("parameters", {})
    coordinator.alarms = loaded_data.get("alarms", {})
    coordinator.active_fields = list(coordinator.parameters.keys())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    setup_websocket_listener(hass, session, coordinator, coordinator.active_fields)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
