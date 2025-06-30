"""WebSocket client for MyStiebel integration."""

import asyncio
import json
import logging
import random

import aiohttp
from homeassistant.core import HomeAssistant

from .const import WS_URL

_LOGGER = logging.getLogger(__name__)


def GET_VALUES_MSG(installation_id, fields):
    return {
        "jsonrpc": "2.0",
        "id": random.randint(1_000_000, 9_999_999),
        "method": "getValues",
        "params": {"installationId": installation_id, "fields": fields},
    }


def SUBSCRIBE_MSG(installation_id, fields):
    return {
        "jsonrpc": "2.0",
        "id": random.randint(1_000_000, 9_999_999),
        "method": "Subscribe",
        "params": {"installationId": installation_id, "registerIndexes": fields},
    }


def SET_VALUE_MSG(installation_id, client_id, register_index, value):
    try:
        numeric_value = int(float(value))
    except (ValueError, TypeError):
        numeric_value = 0
    return {
        "jsonrpc": "2.0",
        "id": random.randint(1_000_000_000, 9_999_999_999),
        "method": "setValues",
        "params": {
            "installationId": installation_id,
            "UUID": client_id,
            "listenWithValuesChanged": True,
            "fields": [
                {"registerIndex": register_index, "displayValue": numeric_value}
            ],
        },
    }


def setup_websocket_listener(
    hass: HomeAssistant, session, coordinator, auth, fields_to_monitor: list
):
    """Set up the WebSocket listener as a background task."""

    async def handle_ws_message(ws, msg, coordinator, fields_to_monitor):
        if msg.type != aiohttp.WSMsgType.TEXT:
            return
        try:
            data = json.loads(msg.data)
            _LOGGER.debug("[websocket] Received: %s", data)
            result = data.get("result")
            if data.get("id") == 1 and result is True:
                await ws.send_json(
                    GET_VALUES_MSG(
                        coordinator.installation_id, fields_to_monitor
                    )
                )
            elif (
                data.get("id")
                and isinstance(result, dict)
                and "fields" in result
            ):
                fields = result.get("fields")
                _LOGGER.debug(
                    f"📦 Initial data received with {len(fields)} values"
                )
                coordinator.process_data_update(fields)
                await ws.send_json(
                    SUBSCRIBE_MSG(
                        coordinator.installation_id, fields_to_monitor
                    )
                )
            elif data.get("method") == "valuesChanged":
                params = data.get("params", {})
                _LOGGER.debug("📡 UPDATE: %s", params)
                coordinator.process_data_update([params])
        except json.JSONDecodeError as e:
            _LOGGER.warning("⚠️ Error parsing message: %s", e)

    async def _run():
        """Run the WebSocket client in a resilient loop."""
        reconnect_delay = 5  # Start with a 5-second delay

        while True:
            try:
                # Re-authenticate to get a fresh token before each connection attempt
                _LOGGER.debug("Attempting to authenticate for WebSocket connection")
                await auth.authenticate()
                coordinator.set_token(auth.token)
                _LOGGER.debug("Authentication successful, proceeding to connect")

                headers = {
                    "Authorization": f"Bearer {coordinator.token}",
                    "X-SC-ClientApp-Name": "MyStiebelApp",
                    "X-SC-ClientApp-Version": "Android_2.3.0",
                    "User-Agent": "MyStiebelApp/2.3.0 Dalvik/...",
                }

                async with session.ws_connect(
                    WS_URL, headers=headers, heartbeat=30
                ) as ws:
                    _LOGGER.debug("✅ WebSocket connected successfully")
                    reconnect_delay = 5  # Reset delay after a successful connection
                    coordinator.set_websocket(ws)

                    await ws.send_json(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "Login",
                            "params": {
                                "clientId": coordinator.installation_id,
                                "jwt": coordinator.token,
                            },
                        }
                    )
                    _LOGGER.debug("➡️ Login message sent.")

                    async for msg in ws:
                        await handle_ws_message(ws, msg, coordinator, fields_to_monitor)

            except Exception as e:
                _LOGGER.error(
                    "❌ WebSocket error: %s Attempting to reconnect in %d seconds",
                    e,
                    reconnect_delay,
                    exc_info=True,
                )
            finally:
                if coordinator:
                    coordinator.set_websocket(None)
                await asyncio.sleep(reconnect_delay)
                # Exponential backoff
                reconnect_delay = min(
                    reconnect_delay * 2, 300
                )  # Max delay of 5 minutes

    hass.async_create_task(_run())
