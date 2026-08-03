"""
Internal HTTP server that receives events pushed by the AirSend WebService
following a `bind` with a callback (see bind_manager.py).
"""

from __future__ import annotations

import json
import logging
from typing import Callable

from aiohttp import web

from registry.device_registry import DeviceRegistry
from inclusion import InclusionState
from catalog.protocol_catalog import ProtocolCatalog
from runtime_settings import RuntimeSettings
from core.thing_notes import convert_notes_to_states

_LOGGER = logging.getLogger("airsend.callback_server")

StateSink = Callable[[str, str, object, dict], None]
RfInboxSink = Callable[[str, int, int, str | None, str | None, int | None], None]

# ThingEvent.type values (see AirSendWebService.yaml). GOT is a fully decoded
# frame (channel + thingnotes usable). UNKNOWN/UNSUPPORTED/INCOMPLETE are
# frames the box received but could not fully decode - only surfaced as
# inclusion inbox candidates when RuntimeSettings.capture_unknown_events is on.
_EVENT_TYPE_GOT = 3
_EVENT_TYPE_UNKNOWN = 256
_EVENT_TYPE_UNSUPPORTED = 262
_EVENT_TYPE_INCOMPLETE = 263
_UNDECODED_CAPTURABLE_TYPES = (_EVENT_TYPE_UNKNOWN, _EVENT_TYPE_UNSUPPORTED, _EVENT_TYPE_INCOMPLETE)


class CallbackServer:
    def __init__(
        self,
        registry: DeviceRegistry,
        inclusion: InclusionState,
        catalog: ProtocolCatalog,
        settings: RuntimeSettings,
        on_state: StateSink,
        on_rf_inbox: RfInboxSink,
        host: str = "127.0.0.1",
        port: int = 8126,
    ) -> None:
        self._registry = registry
        self._inclusion = inclusion
        self._catalog = catalog
        self._settings = settings
        self._on_state = on_state
        self._on_rf_inbox = on_rf_inbox
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

    def _resolve_decoded_flag(self, event_type: object) -> bool | None:
        """Returns True for a fully decoded (GOT) frame, False for a frame
        the box could not decode but that we still want to capture (only
        when capture_unknown_events is on), or None if the event should be
        ignored entirely."""
        if event_type == _EVENT_TYPE_GOT:
            return True
        if self._settings.capture_unknown_events and event_type in _UNDECODED_CAPTURABLE_TYPES:
            return False
        return None

    def _log_reliability_sample(self, box_slug: str, channel_id: int, channel_source: int, event: dict) -> None:
        catalog_entry = self._catalog.entry_for(box_slug, channel_id)
        _LOGGER.info(
            "reliability_sample value=%s protocol=%s band=%s box=%s channel=%s/%s",
            event.get("reliability"),
            catalog_entry.get("name") if catalog_entry else None,
            catalog_entry.get("band") if catalog_entry else None,
            box_slug, channel_id, channel_source,
        )

    def _record_candidate(
        self, box_slug: str, channel_id: int, channel_source: int, decoded: bool,
    ) -> None:
        protocol_name = self._catalog.protocol_name_for(box_slug, channel_id)
        self._inclusion.upsert_candidate(
            box=box_slug,
            channel_id=channel_id,
            channel_source=channel_source,
            protocol_name=protocol_name,
            decoded=decoded,
        )

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

        if "uid" in thingnotes and thingnotes.get("uid") is not None:
            _LOGGER.debug(
                "Command ack event (uid=%s) type=%s on box=%s channel=%s/%s",
                thingnotes.get("uid"), event_type, box_slug, channel_id, channel_source,
            )
            return

        _LOGGER.info("raw_event_body box=%s channel=%s/%s body=%s", box_slug, channel_id, channel_source, json.dumps(event))

        decoded = self._resolve_decoded_flag(event_type)
        if decoded is None:
            _LOGGER.debug(
                "Event ignored (type=%s, capture_unknown_events=%s) on box=%s channel=%s/%s",
                event_type, self._settings.capture_unknown_events, box_slug, channel_id, channel_source,
            )
            return

        if decoded:
            self._log_reliability_sample(box_slug, channel_id, channel_source, event)
            if not self._is_valid_reliability(event):
                _LOGGER.debug(
                    "Event dropped (reliability=%s out of range [%s, %s]) on box=%s channel=%s/%s",
                    event.get("reliability"),
                    RuntimeSettings.RELIABILITY_MIN,
                    RuntimeSettings.RELIABILITY_MAX,
                    box_slug, channel_id, channel_source,
                )
                return

        # Publish RF inbox MQTT event for every valid decoded frame,
        # regardless of whether it matches a configured device.
        if decoded:
            catalog_entry = self._catalog.entry_for(box_slug, channel_id)
            protocol_name = catalog_entry.get("name") if catalog_entry else None
            action: str | None = None
            reliability_val: int | None = event.get("reliability")
            for stype, svalue in convert_notes_to_states(notes):
                if stype == "STATE":
                    action = str(svalue)
                    break
            self._on_rf_inbox(
                box_slug, channel_id, channel_source,
                protocol_name, action, reliability_val,
            )

        device = self._registry.match(box_slug, channel_id, channel_source)
        if device is not None:
            if decoded:
                for stype, svalue in convert_notes_to_states(notes):
                    self._on_state(device.key, stype, svalue, channel)
            return

        # Unmatched frame: always recorded as an inclusion inbox candidate,
        # whether or not the wizard UI currently has a session open.
        self._record_candidate(box_slug, channel_id, channel_source, decoded)
