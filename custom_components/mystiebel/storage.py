"""Secure storage handler for MyStiebel credentials."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_credentials"


class CredentialStore:
    """Handle secure storage of MyStiebel credentials."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the credential store."""
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {}

    async def async_load(self) -> dict[str, Any]:
        """Load credentials from encrypted storage."""
        try:
            data = await self._store.async_load()
            if data:
                self._data = data
                _LOGGER.debug("Loaded credentials from secure storage")
            return self._data
        except Exception as err:
            _LOGGER.error("Failed to load credentials: %s", err)
            return {}

    async def async_save(
        self,
        entry_id: str,
        username: str,
        password: str,
        client_id: str,
        token: str | None = None,
    ) -> None:
        """Save credentials to encrypted storage."""
        self._data[entry_id] = {
            "username": username,
            "password": password,
            "client_id": client_id,
            "token": token,
            "last_updated": dt_util.now().isoformat(),
        }
        await self._store.async_save(self._data)
        _LOGGER.debug("Saved credentials to secure storage for entry %s", entry_id)

    async def async_get(self, entry_id: str) -> dict[str, Any] | None:
        """Get credentials for a specific entry."""
        return self._data.get(entry_id)

    async def async_remove(self, entry_id: str) -> None:
        """Remove credentials for a specific entry."""
        if entry_id in self._data:
            del self._data[entry_id]
            await self._store.async_save(self._data)
            _LOGGER.debug("Removed credentials for entry %s", entry_id)

    async def async_update_token(self, entry_id: str, token: str) -> None:
        """Update only the token for a specific entry."""
        if entry_id in self._data:
            self._data[entry_id]["token"] = token
            self._data[entry_id]["last_updated"] = dt_util.now().isoformat()
            await self._store.async_save(self._data)
            _LOGGER.debug("Updated token for entry %s", entry_id)
