"""Config flow for the MyStiebel integration."""

import logging
import uuid

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN
from .mystiebel_auth import MyStiebelAuth

_LOGGER = logging.getLogger(__name__)


class MyStiebelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MyStiebel."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.user_credentials, self.installations = {}, {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return MyStiebelOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step of the config flow for user credentials."""
        errors = {}
        if user_input is not None:
            self.user_credentials = user_input
            self.user_credentials["client_id"] = str(uuid.uuid4())
            try:
                session = aiohttp_client.async_get_clientsession(self.hass)
                auth = MyStiebelAuth(
                    session,
                    self.user_credentials["username"],
                    self.user_credentials["password"],
                    self.user_credentials["client_id"],
                )
                await auth.authenticate()
                installations_data = await auth.get_installations()
                for inst in installations_data.get("items", []):
                    device_name = f"{inst.get('profile', {}).get('name', 'Unknown')} in {inst.get('location', {}).get('city', 'Unknown')}"
                    self.installations[device_name] = inst
                if not self.installations:
                    return self.async_abort(reason="no_devices_found")
                return await self.async_step_device()
            except Exception:
                _LOGGER.exception("Authentication failed")
                errors["base"] = "auth_error"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("username"): str, vol.Required("password"): str}
            ),
            errors=errors,
        )

    async def async_step_device(self, user_input=None):
        """Handle the step to select a device from the fetched list."""
        if user_input is not None:
            selected_device_name = user_input["device"]
            selected_device = self.installations[selected_device_name]
            unique_id = str(selected_device["id"])
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=selected_device_name,
                data={
                    "username": self.user_credentials["username"],
                    "password": self.user_credentials["password"],
                    "client_id": self.user_credentials["client_id"],
                    "installation_id": selected_device["id"],
                },
            )
        device_names = list(self.installations.keys())
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Required("device"): vol.In(device_names)}),
            description_placeholders={"devices": ", ".join(device_names)},
        )


class MyStiebelOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for MyStiebel."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = self.config_entry.options
        data_schema = vol.Schema(
            {
                vol.Optional(
                    "bath_volume", default=options.get("bath_volume", 180)
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional(
                    "shower_output", default=options.get("shower_output", 12)
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
