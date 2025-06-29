"""WebSocket client for MyStiebel integration."""

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
    hass: HomeAssistant, session, coordinator, fields_to_monitor: list
):
    """Start de WebSocket-listener als achtergrondtaak."""

    async def _run():
        headers = {
            "Authorization": f"Bearer {coordinator.token}",
            "X-SC-ClientApp-Name": "MyStiebelApp",
            "X-SC-ClientApp-Version": "Android_2.3.0",
            "User-Agent": "MyStiebelApp/2.3.0 Dalvik/...",
        }
        try:
            async with session.ws_connect(WS_URL, headers=headers) as ws:
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

                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    try:
                        data = json.loads(msg.data)
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

                            coordinator.process_data_update(fields)
                            await ws.send_json(
                                SUBSCRIBE_MSG(
                                    coordinator.installation_id, fields_to_monitor
                                )
                            )
                        elif data.get("method") == "valuesChanged":
                            params = data.get("params", {})
                            coordinator.process_data_update([params])
                    except json.JSONDecodeError as e:
                        _LOGGER.error("⚠️ Error parsing message: %s", e)
        except Exception as e:
            _LOGGER.error("❌ WebSocket error: %s", e, exc_info=True)
        finally:
            if coordinator:
                coordinator.set_websocket(None)

    hass.async_create_task(_run())
