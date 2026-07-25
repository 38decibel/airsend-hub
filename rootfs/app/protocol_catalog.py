"""
Local cache of the RF protocol catalog (GET /channels, cf. airsend_client),
per hub. Used to:
- retrieve a human-readable protocol name (e.g., "PFX") from a channel.id during
inclusion, for display/suggestion to the user. 
- determine as accurately as possible whether the hub is a single-band AirSend or an AirSend Duo.
"""

from __future__ import annotations

import logging
import time

from airsend_client import AirSendClient, AirSendError, BoxConfig

_LOGGER = logging.getLogger("airsend.protocol_catalog")

_CACHE_TTL_S = 3600.0

BAND_868_MHZ = 2


class ProtocolCatalog:
    def __init__(self, client: AirSendClient) -> None:
        self._client = client
        self._cache: dict[str, dict] = {}

    async def refresh(self, box: BoxConfig) -> list[dict]:
        try:
            channels = await self._client.list_channels(box)
        except AirSendError as exc:
            _LOGGER.warning("Failed to fetch channel catalog for box '%s': %s", box.name, exc)
            return self._cache.get(box.slug, {}).get("channels", [])

        self._cache[box.slug] = {"channels": channels, "fetched_at": time.time()}
        _LOGGER.info("Cached %d protocol(s) for box '%s'", len(channels), box.name)
        return channels

    def _get_cached(self, box_slug: str) -> list[dict]:
        entry = self._cache.get(box_slug)
        if entry is None:
            return []
        if time.time() - entry["fetched_at"] > _CACHE_TTL_S:
            _LOGGER.debug("Protocol cache for box '%s' is stale, refresh recommended", box_slug)
        return entry["channels"]

    def protocol_name_for(self, box_slug: str, channel_id: int) -> str | None:
        for entry in self._get_cached(box_slug):
            if entry.get("id") == channel_id:
                return entry.get("name")
        return None

    def entry_for(self, box_slug: str, channel_id: int) -> dict | None:
        for entry in self._get_cached(box_slug):
            if entry.get("id") == channel_id:
                return entry
        return None

    def is_duo_best_effort(self, box_slug: str) -> bool | None:
        channels = self._get_cached(box_slug)
        if not channels:
            return None
        return any(entry.get("band") == BAND_868_MHZ for entry in channels)

