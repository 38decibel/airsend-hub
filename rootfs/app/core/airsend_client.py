"""
HTTP client for AirSendWebService.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import uuid
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger("airsend.client")

# Special channel id used by AirSendWebService to read the box memory table.
_MEMORY_CHANNEL_ID = 1
# Each memory entry is 14 bytes (Big-Endian): uint16 id | uint64 source | uint32 counter.
_MEMORY_ENTRY_SIZE = 14
_MEMORY_ENTRY_BITS = _MEMORY_ENTRY_SIZE * 8
# memory==3 in the channel response means PUT was acknowledged.
_MEMORY_ACK_PUT = 3

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

    async def read_memory(self, box: BoxConfig) -> list[dict]:
        """Read the box internal RF memory table.

        Returns a list of dicts with keys ``id`` (channel id), ``source``
        (RF source address) and ``counter`` (current rolling-code counter).

        The box encodes the table as a Big-Endian binary blob carried inside a
        thingnotes INFO note (type DATA, value_binsize=1120 bits = 10 entries
        of 14 bytes each: uint16 id | uint64 source | uint32 counter).
        """
        uid = int(uuid.uuid4().int & 0xFFFF_FFFF)
        body: dict[str, Any] = {
            "wait": True,
            "channel": {"id": _MEMORY_CHANNEL_ID},
            "thingnotes": {
                "uid": uid,
                "notes": [{"method": 0, "type": 0, "value": 0}],
            },
        }
        async with self._transfer_lock:
            resp = await self._request("POST", "/airsend/transfer", box=box, json_body=body)

        notes = resp.get("thingnotes", {}).get("notes", [])
        for note in notes:
            raw = note.get("value")
            binsize = note.get("value_binsize", 0)
            if not isinstance(raw, str) or not raw.startswith("0x"):
                continue
            if binsize % _MEMORY_ENTRY_BITS != 0:
                _LOGGER.warning("Unexpected memory blob size: %d bits", binsize)
                continue
            blob = bytes.fromhex(raw[2:])
            entries = []
            for i in range(len(blob) // _MEMORY_ENTRY_SIZE):
                off = i * _MEMORY_ENTRY_SIZE
                ch_id  = struct.unpack_from(">H", blob, off)[0]
                source = struct.unpack_from(">Q", blob, off + 2)[0]
                counter = struct.unpack_from(">I", blob, off + 10)[0]
                entries.append({"id": ch_id, "source": source, "counter": counter})
            return entries

        return []

    async def write_memory_entry(
        self, box: BoxConfig, channel_id: int, source: int, counter: int
    ) -> bool:
        """Write (or update) one entry in the box internal RF memory.

        Sends a ``memory: PUT`` transfer for the given channel/source/counter
        triplet.  Returns True on ACK (response memory==3), False otherwise.
        """
        uid = int(uuid.uuid4().int & 0xFFFF_FFFF)
        body: dict[str, Any] = {
            "wait": True,
            "channel": {
                "id": channel_id,
                "source": source,
                "counter": counter,
            },
            "thingnotes": {
                "uid": uid,
                "state": {"memory": "PUT", "counter": counter},
                "notes": [],
            },
        }
        async with self._transfer_lock:
            resp = await self._request("POST", "/airsend/transfer", box=box, json_body=body)

        ack_memory = resp.get("channel", {}).get("memory")
        success = ack_memory == _MEMORY_ACK_PUT
        if success:
            _LOGGER.info(
                "Memory entry written: box=%s channel_id=%d source=%d counter=%d",
                box.slug, channel_id, source, counter,
            )
        else:
            _LOGGER.warning(
                "Memory write returned unexpected ack memory=%r for channel_id=%d source=%d",
                ack_memory, channel_id, source,
            )
        return success
