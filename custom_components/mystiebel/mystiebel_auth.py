"""Authentication handler for MyStiebel integration."""

import logging

import aiohttp

BASE_URL = "https://auth.mystiebel.com"
SERVICE_URL = "https://serviceapi.mystiebel.com"

_LOGGER = logging.getLogger(__name__)


class MyStiebelAuth:
    """Authentication handler for the MyStiebel integration.

    Handles authentication and installation retrieval using the MyStiebel API.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        client_id: str,
    ) -> None:
        """Initialize the authentication handler with session and credentials."""
        self._session = session
        self._username = username
        self._password = password
        self._client_id = client_id
        self.token: str | None = None

    async def authenticate(self) -> None:
        """Authenticate with the MyStiebel API and acquire a JWT token."""
        headers = {
            "X-SC-ClientApp-Name": "MyStiebelApp",
            "X-SC-ClientApp-Version": "Android_2.3.0",
            "User-Agent": "MyStiebelApp/2.3.0 Dalvik/2.1.0",
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Encoding": "gzip",
        }
        payload = {
            "userName": self._username,
            "password": self._password,
            "clientId": self._client_id,
            "rememberMe": True,
        }

        async with self._session.post(
            f"{BASE_URL}/api/v1/Jwt/login", json=payload, headers=headers
        ) as response:
            response.raise_for_status()
            data = await response.json()
            self.token = data.get("token")
            if not self.token:
                raise ValueError("Authentication succeeded but no token was received")

    async def get_installations(self) -> dict:
        """Retrieve installations associated with the authenticated user."""
        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-SC-ClientApp-Name": "MyStiebelApp",
            "X-SC-ClientApp-Version": "Android_2.3.0",
            "User-Agent": "MyStiebelApp/2.3.0 Dalvik/2.1.0",
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Encoding": "gzip",
        }
        payload = {"includeWithPendingUserAccesses": True}
        async with self._session.post(
            f"{SERVICE_URL}/api/v1/InstallationsInfo/own", json=payload, headers=headers
        ) as response:
            response.raise_for_status()
            return await response.json()
