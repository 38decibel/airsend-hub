"""
HTTP client for AirSendWebService.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger("airsend.client")

class AirSendError(Exception):
    pass
    
class AirSendAuthError(AirSendError):
    pass

@dataclass
class BoxConfig:

    name: str
    localip: str
    ipv4: str
    password: str
    gw: bool = False

    @property
    def slug(self) -> str:
        return "".join(c if c.isalnum() else "_" for c in self.name.lower()) or "box"

    def locator(self) -> str:
        gw_flag = "1" if self.gw else "0"
        return f"sp://{self.password}@[{self.localip}]/?gw={gw_flag}&rhost={self.ipv4}"


class AirSendClient:

    def __init__(self, base_url: str = "http://127.0.0.1:33863") -> None:
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self._transfer_lock = asyncio.Lock()

    def start(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "AirSendClient":
        self.start()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()


    async def _request(
        self,
        method: str,
        path: str,
        box: BoxConfig | None = None,
        json_body: dict | None = None,
    ) -> Any:
        if self._session is None:
            raise AirSendError("AirSendClient.start() must be called before use")

        url = f"{self._base_url}{path}"
        headers = {}
        if box is not None:
            headers["Authorization"] = f"Bearer {box.locator()}"

        try:
            async with self._session.request(
                method, url, json=json_body, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 401:
                    raise AirSendAuthError(f"Invalid locator for {url}")
                if resp.status >= 500:
                    text = await resp.text()
                    raise AirSendError(f"AirSendWebService error {resp.status} on {url}: {text}")
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.text()
        except aiohttp.ClientError as exc:
            raise AirSendError(f"Connection error calling {url}: {exc}") from exc


    async def get_status(self) -> dict:
        return await self._request("GET", "/service/status")


    async def list_channels(self, box: BoxConfig) -> list[dict]:
        result = await self._request("GET", "/channels", box=box)
        if isinstance(result, list):
            return result
        raise AirSendError("Unexpected /channels response shape")


    async def bind(
        self,
        box: BoxConfig,
        callback_url: str,
        duration: float = 3600.0,
        channel: dict | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "duration": duration,
            "callback": callback_url,
        }
        if channel is not None:
            body["channel"] = channel
        return await self._request("POST", "/airsend/bind", box=box, json_body=body)

    async def unbind(self, box: BoxConfig) -> None:
        await self._request("GET", "/airsend/unbind", box=box)

    async def transfer(
        self,
        box: BoxConfig,
        channel: dict,
        thingnotes: dict,
        wait: bool = True,
        callback_url: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "wait": wait,
            "channel": channel,
            "thingnotes": thingnotes,
        }
        if callback_url is not None:
            body["callback"] = callback_url
        async with self._transfer_lock:
            return await self._request("POST", "/airsend/transfer", box=box, json_body=body)
