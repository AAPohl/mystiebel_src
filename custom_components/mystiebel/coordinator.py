"""Data update coordinator for the MyStiebel integration."""

import logging
from asyncio import Event

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class MyStiebelCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
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
    ):
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.session, self.token, self.installation_id = session, token, installation_id
        self.client_id, self.device_name = client_id, device_name
        self.model, self.sw_version, self.mac_address = model, sw_version, mac_address
        self.bath_volume = bath_volume
        self.shower_output = shower_output
        self.entities, self.data = {}, {}
        self.parameters, self.alarms, self.active_fields = {}, {}, []
        self.ready_event, self.ws = Event(), None

    async def _async_update_data(self):
        return self.data

    def process_data_update(self, data_updates: list[dict]):
        for update in data_updates:
            register, value = update.get("registerIndex"), update.get("displayValue")
            if register is not None:
                self.data[register] = value
        self.async_set_updated_data(self.data)

    def set_websocket(self, ws):
        self.ws = ws

    def set_token(self, token: str):
        """Update the authentication token."""
        self.token = token

    async def async_set_value(self, register_index, value):
        if self.ws and not self.ws.closed:
            from .websocket_client import SET_VALUE_MSG

            message = SET_VALUE_MSG(
                self.installation_id, self.client_id, register_index, value
            )
            _LOGGER.debug("➡️ Sending setValues message: %s", message)
            await self.ws.send_json(message)
            self.process_data_update(
                [{"registerIndex": register_index, "displayValue": value}]
            )
            return True
        _LOGGER.error("❌ WebSocket not available or closed. Cannot set value")
        return False
