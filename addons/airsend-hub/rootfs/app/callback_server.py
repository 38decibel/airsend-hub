"""
Internal HTTP server that receives events pushed by the AirSend WebService
following a `bind` with a callback (see bind_manager.py).
"""

from __future__ import annotations

import json
import logging
from typing import Callable

from aiohttp import web

from device_registry import DeviceRegistry
from inclusion import InclusionState
from protocol_catalog import ProtocolCatalog
from runtime_settings import RuntimeSettings
from thing_notes import convert_notes_to_states

_LOGGER = logging.getLogger("airsend.callback_server")

StateSink = Callable[[str, str, object, dict], None]


class CallbackServer:
    def __init__(
        self,
        registry: DeviceRegistry,
        inclusion: InclusionState,
        catalog: ProtocolCatalog,
        settings: RuntimeSettings,
        on_state: StateSink,
        host: str = "127.0.0.1",
        port: int = 8126,
    ) -> None:
        self._registry = registry
        self._inclusion = inclusion
        self._catalog = catalog
        self._settings = settings
        self._on_state = on_state
        self._host = host
        self._port = port
        self._app = web.Application()
        self._app.router.add_post("/cb/{box_slug}", self._handle_callback)
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        _LOGGER.info("Callback server listening on %s:%s", self._host, self._port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _handle_callback(self, request: web.Request) -> web.Response:
        box_slug = request.match_info["box_slug"]
        try:
            payload = await request.json()
        except Exception as exc:
            _LOGGER.warning("Malformed callback payload from box %s: %s", box_slug, exc)
            return web.Response(status=200)

        events = payload.get("events")
        if not isinstance(events, list):
            _LOGGER.debug("Callback payload without 'events' array from box %s: %r", box_slug, payload)
            return web.Response(status=200)

        for event in events:
            try:
                await self._handle_event(box_slug, event)
            except Exception:
                _LOGGER.exception("Error processing event from box %s: %r", box_slug, event)

        return web.Response(status=200)

    def _is_valid_reliability(self, event: dict) -> bool:

        if "reliability" not in event:
            return True
        reliability = event.get("reliability")
        if not isinstance(reliability, (int, float)):
            return False
        return RuntimeSettings.RELIABILITY_MIN < reliability < RuntimeSettings.RELIABILITY_MAX

    async def _handle_event(self, box_slug: str, event: dict) -> None:
        channel = event.get("channel") or {}
        thingnotes = event.get("thingnotes") or {}
        notes = thingnotes.get("notes") or []
        event_type = event.get("type")

        channel_id = channel.get("id")
        channel_source = channel.get("source")
        if channel_id is None or channel_source is None:
            _LOGGER.debug("Event without channel id/source, ignored: %r", event)
            return

        has_uid = "uid" in thingnotes and thingnotes.get("uid") is not None

        if has_uid:
            _LOGGER.debug(
                "Command ack event (uid=%s) type=%s on box=%s channel=%s/%s",
                thingnotes.get("uid"), event_type, box_slug, channel_id, channel_source,
            )
            return

        _LOGGER.info("raw_event_body box=%s channel=%s/%s body=%s", box_slug, channel_id, channel_source, json.dumps(event))

        if event_type != 3:
            _LOGGER.debug(
                "Interrupt event ignored (type=%s != GOT) on box=%s channel=%s/%s",
                event_type, box_slug, channel_id, channel_source,
            )
            return

        reliability = event.get("reliability")

        catalog_entry = self._catalog.entry_for(box_slug, channel_id)
        _LOGGER.info(
            "reliability_sample value=%s protocol=%s band=%s box=%s channel=%s/%s",
            reliability,
            catalog_entry.get("name") if catalog_entry else None,
            catalog_entry.get("band") if catalog_entry else None,
            box_slug, channel_id, channel_source,
        )

        if not self._is_valid_reliability(event):
            _LOGGER.debug(
                "Interrupt event dropped (reliability=%s out of range [%s, %s]) on box=%s channel=%s/%s",
                reliability,
                RuntimeSettings.RELIABILITY_MIN,
                RuntimeSettings.RELIABILITY_MAX,
                box_slug, channel_id, channel_source,
            )
            return

        device = self._registry.match(box_slug, channel_id, channel_source)

        if device is not None:
            states = convert_notes_to_states(notes)
            for stype, svalue in states:
                self._on_state(device.key, stype, svalue, channel)
            return

        if not self._inclusion.active:
            _LOGGER.debug(
                "Unknown device, inclusion mode OFF, ignored: box=%s channel=%s/%s",
                box_slug, channel_id, channel_source,
            )
            return

        protocol_name = self._catalog.protocol_name_for(box_slug, channel_id)
        self._inclusion.upsert_candidate(
            box=box_slug,
            channel_id=channel_id,
            channel_source=channel_source,
            protocol_name=protocol_name,
        )
