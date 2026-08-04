"""
Ingress web interface for adding devices, inspired by the workflow of the official cloud app.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import re
import time
import uuid
from pathlib import Path
from typing import Any

from aiohttp import web

from core.airsend_client import AirSendClient, AirSendError, BoxConfig
from registry.backup_export import build_backup, diff_backup_devices, parse_backup
from core.bind_manager import BindManager
from catalog.catalog_data import search_brands
from catalog.channel_aliases import expected_receive_channels
from registry.device_registry import Device, DeviceRegistry
from inclusion import Candidate, InclusionState
from mqtt_bridge import MqttBridge
from catalog.protocol_catalog import BAND_868_MHZ, ProtocolCatalog
from api.registration_api import RegistrationApi
from runtime_settings import RuntimeSettings
from registry.yaml_import import load_yaml_devices, parse_airsend_yaml

_LOGGER = logging.getLogger("airsend.inclusion_api")

_WEB_DIR = Path(__file__).parent.parent / "web"

_DEFAULT_LISTEN_DURATION_S = 20.0
_MAX_LISTEN_DURATION_S = 60.0
_SESSION_TTL_S = 600.0

_FRIENDLY_NAME_EMPTY = "empty friendly_name"

_HA_CONFIG_DIR = Path("/config")
_AIRSEND_YAML_FILENAME = "airsend.yaml"

KIND_TO_DOMAIN: dict[str, str] = {
    "1_bouton": "button",
    "on_off": "switch",
    "volet_roulant": "cover",
    "niveau": "cover",
}

# Purely cosmetic, user-facing grouping (icon/label in the UI). Stored in
# device.options["display_category"] and never consulted for domain/kind
# logic: several categories legitimately map to the same technical kind
# (e.g. automotive_keyfob and doorbell are both "1_bouton"/"event").
DISPLAY_CATEGORIES: frozenset[str] = frozenset({
    "other",
    "temp_humidity",
    "weather_station",
    "tpms",
    "energy_water_meter",
    "smoke_security_alarm",
    "gate_garage_remote",
    "automotive_keyfob",
    "remote_keyfob",
    "home_automation_blinds",
    "ceiling_fan",
    "kitchen_thermometer",
    "doorbell",
    "rolling_code",
    "restaurant_pager",
})

def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "device"


class ListenSession:

    __slots__ = (
        "id", "box_slug", "channel_id", "expected_channels",
        "started_at", "duration", "done", "error",
    )

    def __init__(self, box_slug: str, channel_id: int | None, duration: float) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.box_slug = box_slug
        self.channel_id = channel_id
        self.expected_channels = expected_receive_channels(channel_id) if channel_id is not None else set()
        self.started_at = time.time()
        self.duration = duration
        self.done = False
        self.error: str | None = None

    @property
    def remaining_s(self) -> float:
        return max(0.0, self.started_at + self.duration - time.time())

    @property
    def is_stale(self) -> bool:
        return self.done and (time.time() - self.started_at) > _SESSION_TTL_S


class InclusionApi:
    def __init__(
        self,
        boxes_by_slug: dict[str, BoxConfig],
        client: AirSendClient,
        bind_manager: BindManager,
        inclusion: InclusionState,
        registry: DeviceRegistry,
        catalog: ProtocolCatalog,
        mqtt_bridge: MqttBridge,
        settings: RuntimeSettings,
    ) -> None:
        self._boxes = boxes_by_slug
        self._client = client
        self._bind_manager = bind_manager
        self._inclusion = inclusion
        self._registry = registry
        self._catalog = catalog
        self._mqtt_bridge = mqtt_bridge
        self._settings = settings
        self._sessions: dict[str, ListenSession] = {}
        self._listening_boxes: set[str] = set()
        self._background_tasks: set[asyncio.Task] = set()

        self.app = web.Application()
        self.app.router.add_get("/api/boxes", self._handle_boxes)
        self.app.router.add_get("/api/devices", self._handle_list_devices)
        self.app.router.add_get("/api/brands", self._handle_search_brands)
        self.app.router.add_get("/api/channel/{channel_id}", self._handle_channel_info)
        self.app.router.add_post("/api/listen", self._handle_start_listen)
        self.app.router.add_get("/api/listen/{session_id}", self._handle_poll_listen)
        self.app.router.add_post("/api/devices", self._handle_confirm_device)
        self.app.router.add_post("/api/devices/manual", self._handle_manual_device)
        self.app.router.add_patch("/api/devices/{key}", self._handle_update_device)
        self.app.router.add_delete("/api/devices/{key}", self._handle_delete_device)
        self.app.router.add_post("/api/import/preview", self._handle_import_preview)
        self.app.router.add_post("/api/import/commit", self._handle_import_commit)
        self.app.router.add_get("/api/import/detect", self._handle_import_detect)
        self.app.router.add_get("/api/backup/export", self._handle_backup_export)
        self.app.router.add_post("/api/backup/import/preview", self._handle_backup_import_preview)
        self.app.router.add_post("/api/backup/import/commit", self._handle_backup_import_commit)
        self.app.router.add_get("/api/inbox", self._handle_list_inbox)
        self.app.router.add_post("/api/inbox/forget", self._handle_inbox_forget)
        self.app.router.add_post("/api/inbox/confirm", self._handle_inbox_confirm)
        self.app.router.add_get("/api/settings", self._handle_get_settings)
        self.app.router.add_patch("/api/settings", self._handle_patch_settings)
        self.app.router.add_get("/api/channels", self._handle_list_channels)
        self.app.router.add_get("/api/memory", self._handle_memory)
        self.app.router.add_get("/{tail:.*}", self._handle_static)


    async def _handle_static(self, request: web.Request) -> web.Response:
        tail = request.match_info["tail"] or "index.html"
        candidate = (_WEB_DIR / tail).resolve()
        try:
            candidate.relative_to(_WEB_DIR.resolve())
        except ValueError:
            raise web.HTTPForbidden()
        if not candidate.is_file():
            candidate = _WEB_DIR / "index.html"
        mime, _ = mimetypes.guess_type(candidate.name)
        mime = mime or "application/octet-stream"
        if mime.startswith("text/"):
            return web.Response(
                text=candidate.read_text(encoding="utf-8"),
                content_type=mime,
                charset="utf-8",
            )
        return web.FileResponse(candidate)


    async def _handle_boxes(self, request: web.Request) -> web.Response:
        return web.json_response(
            [{"slug": slug, "name": box.name} for slug, box in self._boxes.items()]
        )

    async def _handle_list_devices(self, request: web.Request) -> web.Response:
        return web.json_response(
            [
                {
                    "key": d.key,
                    "friendly_name": d.friendly_name,
                    "kind": d.kind,
                    "domain": d.domain,
                    "protocol_name": d.protocol_name,
                    "box": d.box,
                    "options": d.options,
                }
                for d in self._registry.all()
            ]
        )

    async def _handle_search_brands(self, request: web.Request) -> web.Response:
        query = request.query.get("q", "")
        return web.json_response(search_brands(query))

    async def _handle_channel_info(self, request: web.Request) -> web.Response:
        box_slug = request.query.get("box") or next(iter(self._boxes), None)
        try:
            channel_id = int(request.match_info["channel_id"])
        except ValueError:
            raise web.HTTPBadRequest(text="invalid channel_id")

        entry = self._catalog.entry_for(box_slug, channel_id) if box_slug else None
        if entry is None:
            return web.json_response({"known": False})
        return web.json_response(
            {
                "known": True,
                "name": entry.get("name"),
                "band": entry.get("band"),
                "counter": entry.get("counter"),
                "rolling_code_risk": bool(entry.get("counter")),
            }
        )


    def _candidate_row(self, c: Candidate) -> dict[str, Any]:
        entry = self._catalog.entry_for(c.box, c.channel_id)
        return {
            "box": c.box,
            "channel_id": c.channel_id,
            "channel_source": c.channel_source,
            "protocol_name": c.protocol_name,
            "decoded": c.decoded,
            "band": entry.get("band") if entry else None,
            "seen_count": c.seen_count,
            "first_seen": c.first_seen,
            "last_seen": c.last_seen,
            "last_action": c.last_action,
            "last_notes": c.last_notes,
        }

    async def _handle_list_inbox(self, request: web.Request) -> web.Response:
        rows = [self._candidate_row(c) for c in self._inclusion.list_candidates()]
        rows.sort(key=lambda r: r["last_seen"], reverse=True)
        return web.json_response(
            {"candidates": rows, "capture_unknown_events": self._settings.capture_unknown_events}
        )

    def _parse_candidate_ref(self, body: dict[str, Any]) -> tuple[str, int, int]:
        try:
            box_slug = str(body["box"])
            channel_id = int(body["channel_id"])
            channel_source = int(body["channel_source"])
        except (KeyError, ValueError, TypeError):
            raise web.HTTPBadRequest(text="missing or invalid box/channel_id/channel_source")
        return box_slug, channel_id, channel_source

    async def _handle_inbox_forget(self, request: web.Request) -> web.Response:
        body = await request.json()
        box_slug, channel_id, channel_source = self._parse_candidate_ref(body)
        forgotten = self._inclusion.forget_candidate(box_slug, channel_id, channel_source)
        return web.json_response({"forgotten": forgotten})

    async def _handle_inbox_confirm(self, request: web.Request) -> web.Response:
        body = await request.json()
        box_slug, channel_id, channel_source = self._parse_candidate_ref(body)

        try:
            kind = str(body["kind"])
            friendly_name = str(body["friendly_name"]).strip()
        except (KeyError, TypeError):
            raise web.HTTPBadRequest(text="missing or invalid fields")
        if not friendly_name:
            raise web.HTTPBadRequest(text=_FRIENDLY_NAME_EMPTY)

        candidate = next(
            (
                c for c in self._inclusion.list_candidates()
                if c.match_key == (box_slug, channel_id, channel_source)
            ),
            None,
        )
        if candidate is None:
            raise web.HTTPNotFound(text="candidate not found (already included or forgotten?)")

        device = self._create_device(
            box_slug=box_slug,
            channel_id=channel_id,
            channel_source=channel_source,
            protocol_name=candidate.protocol_name,
            kind=kind,
            friendly_name=friendly_name,
            options=body.get("options") or {},
            source_of_creation="rf_inbox",
        )
        self._inclusion.pop_candidate(box_slug, channel_id, channel_source)
        return web.json_response({"key": device.key})

    async def _handle_get_settings(self, request: web.Request) -> web.Response:
        return web.json_response({
            "capture_unknown_events": self._settings.capture_unknown_events,
            "bind_channel_id": self._settings.bind_channel_id,
        })

    async def _handle_patch_settings(self, request: web.Request) -> web.Response:
        body = await request.json()
        changed_channel = False

        if "capture_unknown_events" in body:
            value = body["capture_unknown_events"]
            if not isinstance(value, bool):
                raise web.HTTPBadRequest(text="'capture_unknown_events' must be a boolean")
            self._mqtt_bridge.set_capture_unknown_events(value)

        if "bind_channel_id" in body:
            raw = body["bind_channel_id"]
            if raw is not None and not isinstance(raw, int):
                raise web.HTTPBadRequest(text="'bind_channel_id' must be an integer or null")
            self._settings.bind_channel_id = raw
            changed_channel = True

        if not body.keys() & {"capture_unknown_events", "bind_channel_id"}:
            raise web.HTTPBadRequest(text="no recognised field in request body")

        if changed_channel:
            asyncio.ensure_future(self._bind_manager.restart_all())

        return web.json_response({
            "capture_unknown_events": self._settings.capture_unknown_events,
            "bind_channel_id": self._settings.bind_channel_id,
        })

    async def _handle_list_channels(self, request: web.Request) -> web.Response:
        """Proxy /channels from AirSendWebService for the first configured box.

        Returns the raw channel list as-is, or 503 when no box is configured.
        """
        box_slug = next(iter(self._boxes), None)
        if box_slug is None:
            return web.json_response({"error": "no box configured"}, status=503)
        box = self._boxes[box_slug]
        try:
            channels = await self._client.list_channels(box)
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"error": str(exc)}, status=502)
        return web.json_response(channels)

    async def _handle_memory(self, request: web.Request) -> web.Response:
        """Return the box internal RF memory table, enriched with device info.

        Each entry contains: id (channel_id), source, counter, protocol_name,
        and optionally device_key / device_name when a matching device exists
        in devices.json.
        """
        box_slug = request.query.get("box") or next(iter(self._boxes), None)
        if box_slug is None:
            return web.json_response({"error": "no box configured"}, status=503)
        box = self._boxes.get(box_slug)
        if box is None:
            return web.json_response({"error": f"unknown box {box_slug!r}"}, status=404)

        try:
            entries = await self._client.read_memory(box)
        except AirSendError as exc:
            return web.json_response({"error": str(exc)}, status=502)

        # Build a lookup (channel_id, source) → device for quick matching
        device_lookup: dict[tuple[int, int], Device] = {
            (d.channel_id, d.channel_source): d
            for d in self._registry.all()
        }

        result = []
        for entry in entries:
            ch_id  = entry["id"]
            source = entry["source"]
            ch_entry = self._catalog.entry_for(box_slug, ch_id)
            protocol_name = ch_entry.get("name") if ch_entry else None
            device = device_lookup.get((ch_id, source))
            row: dict[str, Any] = {
                "channel_id":    ch_id,
                "source":        source,
                "counter":       entry["counter"],
                "protocol_name": protocol_name,
                "device_key":    device.key if device else None,
                "device_name":   device.friendly_name if device else None,
            }
            result.append(row)

        return web.json_response(result)

    def _prune_stale_sessions(self) -> None:
        for sid in [sid for sid, s in self._sessions.items() if s.is_stale]:
            self._sessions.pop(sid, None)

    def _is_433(self, box_slug: str, channel_id: int) -> bool:
        entry = self._catalog.entry_for(box_slug, channel_id)
        return entry is None or entry.get("band") != BAND_868_MHZ

    def _session_accepts_channel(self, session: "ListenSession", channel_id: int) -> bool:
        if session.channel_id is None:
            return self._is_433(session.box_slug, channel_id)
        return channel_id in session.expected_channels

    async def _handle_start_listen(self, request: web.Request) -> web.Response:
        self._prune_stale_sessions()
        body = await request.json()
        box_slug = body.get("box")
        channel_id = body.get("channel_id")
        try:
            duration = min(float(body.get("duration", _DEFAULT_LISTEN_DURATION_S)), _MAX_LISTEN_DURATION_S)
        except (TypeError, ValueError):
            duration = _DEFAULT_LISTEN_DURATION_S

        box = self._boxes.get(box_slug)
        if box is None:
            raise web.HTTPBadRequest(text="invalid box")
        if channel_id is not None and not isinstance(channel_id, int):
            raise web.HTTPBadRequest(text="invalid channel_id")

        if box_slug in self._listening_boxes:
            raise web.HTTPConflict(text="a listening session is already in progress on this box.")

        handle = self._bind_manager.get_handle(box_slug)
        if handle is None:
            raise web.HTTPBadRequest(text="box unknown to the bind_manager")

        session = ListenSession(box_slug, channel_id, duration)
        self._sessions[session.id] = session
        self._listening_boxes.add(box_slug)

        was_active = self._inclusion.active
        self._inclusion.active = True

        async def _run() -> None:
            try:
                await handle.start_targeted_listen(channel_id, duration)
            except AirSendError as exc:
                session.error = str(exc)
                _LOGGER.warning(
                    "Targeted listen failed for box=%s channel=%s: %s", box_slug, channel_id, exc
                )
            finally:
                if not was_active:
                    self._inclusion.active = False
                session.done = True
                self._listening_boxes.discard(box_slug)

        listen_task = asyncio.create_task(_run())
        self._background_tasks.add(listen_task)
        listen_task.add_done_callback(self._background_tasks.discard)
        return web.json_response({"session_id": session.id, "duration": duration})

    async def _handle_poll_listen(self, request: web.Request) -> web.Response:
        session = self._sessions.get(request.match_info["session_id"])
        if session is None:
            raise web.HTTPNotFound()

        candidates = [
            {
                "box": c.box,
                "channel_id": c.channel_id,
                "channel_source": c.channel_source,
                "protocol_name": c.protocol_name,
            }
            for c in self._inclusion.list_candidates()
            if c.box == session.box_slug
            and self._session_accepts_channel(session, c.channel_id)
            and c.last_seen >= session.started_at
        ]

        if session.error:
            status = "error"
        elif session.done:
            status = "done"
        else:
            status = "listening"

        return web.json_response(
            {
                "status": status,
                "error": session.error,
                "remaining_s": round(session.remaining_s, 1),
                "candidates": candidates,
            }
        )


    def _create_device(
        self,
        box_slug: str,
        channel_id: int,
        channel_source: int,
        protocol_name: str | None,
        kind: str,
        friendly_name: str,
        options: dict[str, Any],
        source_of_creation: str,
        key: str | None = None,
    ) -> Device:
        """If `key` is omitted, one is minted from friendly_name (existing
        inclusion/YAML-import behavior). If provided (backup restore), it is
        used verbatim so the MQTT unique_id/entity_id match the originals."""
        domain = KIND_TO_DOMAIN.get(kind)
        if domain is None:
            raise web.HTTPBadRequest(text=f"unknown kind: {kind}")

        display_category = (options or {}).get("display_category")
        if display_category is not None and display_category not in DISPLAY_CATEGORIES:
            raise web.HTTPBadRequest(text=f"unknown display_category: {display_category}")

        if key is None:
            base_key = _slugify(friendly_name)
            key = base_key
            suffix = 2
            while self._registry.get(key) is not None:
                key = f"{base_key}_{suffix}"
                suffix += 1

        device = Device(
            key=key,
            box=box_slug,
            channel_id=channel_id,
            channel_source=channel_source,
            protocol_name=protocol_name,
            kind=kind,
            domain=domain,
            friendly_name=friendly_name,
            options=options or {},
            source_of_creation=source_of_creation,
        )
        self._registry.add(device)
        self._mqtt_bridge.publish_discovery(device)
        _LOGGER.info(
            "New device created via ingress UI: %s (kind=%s domain=%s source=%s)",
            key, kind, domain, source_of_creation,
        )
        return device

    async def _write_memory_if_needed(
        self, box_slug: str, channel_id: int, channel_source: int
    ) -> None:
        """Register the device in the box internal memory if the protocol is
        send-only (getDecoder==0, i.e. rolling-code).

        For decodable protocols the box learns the source automatically when it
        receives an RF frame; for send-only ones (PFX, PTC, …) we must
        explicitly PUT the entry so the motor can verify the counter.

        Failures are logged as warnings and never propagated — a failed memory
        write must not prevent the device from being saved to devices.json.
        """
        entry = self._catalog.entry_for(box_slug, channel_id)
        if entry is None or entry.get("getDecoder") != 0:
            return

        box = self._boxes.get(box_slug)
        if box is None:
            _LOGGER.warning("_write_memory_if_needed: unknown box '%s'", box_slug)
            return

        try:
            success = await self._client.write_memory_entry(
                box, channel_id, channel_source, counter=0
            )
            if not success:
                _LOGGER.warning(
                    "Box memory write not acknowledged for channel_id=%d source=%d",
                    channel_id, channel_source,
                )
        except AirSendError as exc:
            _LOGGER.warning(
                "Could not write box memory for channel_id=%d source=%d: %s",
                channel_id, channel_source, exc,
            )

    async def _handle_confirm_device(self, request: web.Request) -> web.Response:
        body = await request.json()
        session = self._sessions.get(body.get("session_id"))
        if session is None:
            raise web.HTTPNotFound(text="unknown or expired listening session")

        try:
            channel_source = int(body["channel_source"])
            kind = str(body["kind"])
            friendly_name = str(body["friendly_name"]).strip()
        except (KeyError, ValueError, TypeError):
            raise web.HTTPBadRequest(text="missing or invalid fields")

        if not friendly_name:
            raise web.HTTPBadRequest(text=_FRIENDLY_NAME_EMPTY)

        candidate = next(
            (
                c for c in self._inclusion.list_candidates()
                if c.box == session.box_slug
                and c.channel_source == channel_source
                and self._session_accepts_channel(session, c.channel_id)
            ),
            None,
        )
        if candidate is None:
            raise web.HTTPNotFound(text="candidate not found (session expired?)")

        device = self._create_device(
            box_slug=session.box_slug,
            channel_id=candidate.channel_id,
            channel_source=channel_source,
            protocol_name=candidate.protocol_name,
            kind=kind,
            friendly_name=friendly_name,
            options=body.get("options") or {},
            source_of_creation="rf_listen",
        )
        await self._write_memory_if_needed(session.box_slug, candidate.channel_id, channel_source)
        self._inclusion.pop_candidate(session.box_slug, candidate.channel_id, channel_source)
        self._sessions.pop(session.id, None)
        return web.json_response({"key": device.key})

    async def _handle_manual_device(self, request: web.Request) -> web.Response:
        body = await request.json()
        try:
            box_slug = body["box"]
            channel_id = int(body["channel_id"])
            channel_source = int(body["channel_source"])
            kind = str(body["kind"])
            friendly_name = str(body["friendly_name"]).strip()
        except (KeyError, ValueError, TypeError):
            raise web.HTTPBadRequest(text="missing or invalid fields")

        if box_slug not in self._boxes:
            raise web.HTTPBadRequest(text="unknown box")
        if not friendly_name:
            raise web.HTTPBadRequest(text=_FRIENDLY_NAME_EMPTY)

        device = self._create_device(
            box_slug=box_slug,
            channel_id=channel_id,
            channel_source=channel_source,
            protocol_name=self._catalog.protocol_name_for(box_slug, channel_id),
            kind=kind,
            friendly_name=friendly_name,
            options=body.get("options") or {},
            source_of_creation="manual",
        )
        await self._write_memory_if_needed(box_slug, channel_id, channel_source)
        return web.json_response({"key": device.key})

    async def _handle_update_device(self, request: web.Request) -> web.Response:
        key = request.match_info["key"]
        device = self._registry.get(key)
        if device is None:
            raise web.HTTPNotFound(text="unknown device")

        body = await request.json()

        friendly_name = body.get("friendly_name")
        if friendly_name is not None:
            friendly_name = str(friendly_name).strip()
            if not friendly_name:
                raise web.HTTPBadRequest(text=_FRIENDLY_NAME_EMPTY)

        options = body.get("options")
        if options is not None and not isinstance(options, dict):
            raise web.HTTPBadRequest(text="invalid options")

        updated = self._registry.update(key, friendly_name=friendly_name, options=options)
        self._mqtt_bridge.publish_discovery(updated)
        _LOGGER.info(
            "Device %s updated via ingress UI (friendly_name=%s options=%s)",
            key, friendly_name, options,
        )
        return web.json_response(
            {"key": updated.key, "friendly_name": updated.friendly_name, "options": updated.options}
        )

    async def _remove_memory_if_needed(self, device: "Device") -> None:
        """Remove the device entry from the box internal memory if the protocol
        is send-only (getDecoder==0, i.e. rolling-code).

        Must read the live memory table first to get the current counter value,
        which the box requires in the REMOVE request.

        Failures are logged as warnings and never propagated — a failed memory
        removal must not prevent the device from being deleted from devices.json.
        """
        entry = self._catalog.entry_for(device.box, device.channel_id)
        if entry is None or entry.get("getDecoder") != 0:
            return

        box = self._boxes.get(device.box)
        if box is None:
            _LOGGER.warning("_remove_memory_if_needed: unknown box '%s'", device.box)
            return

        try:
            memory = await self._client.read_memory(box)
        except AirSendError as exc:
            _LOGGER.warning(
                "Could not read box memory before removing channel_id=%d source=%d: %s",
                device.channel_id, device.channel_source, exc,
            )
            return

        mem_entry = next(
            (e for e in memory if e["id"] == device.channel_id and e["source"] == device.channel_source),
            None,
        )
        if mem_entry is None:
            _LOGGER.info(
                "Device %s not found in box memory (already removed or never written), skipping REMOVE",
                device.key,
            )
            return

        try:
            success = await self._client.remove_memory_entry(
                box, device.channel_id, device.channel_source, mem_entry["counter"]
            )
            if not success:
                _LOGGER.warning(
                    "Box memory REMOVE not acknowledged for channel_id=%d source=%d",
                    device.channel_id, device.channel_source,
                )
        except AirSendError as exc:
            _LOGGER.warning(
                "Could not remove box memory entry for channel_id=%d source=%d: %s",
                device.channel_id, device.channel_source, exc,
            )

    async def _handle_delete_device(self, request: web.Request) -> web.Response:
        key = request.match_info["key"]
        device = self._registry.get(key)
        if device is None:
            raise web.HTTPNotFound(text="unknown device")

        await self._remove_memory_if_needed(device)
        self._mqtt_bridge.remove_discovery(device)
        self._registry.remove(key)
        _LOGGER.info("Device %s removed via ingress UI", key)
        return web.json_response({"key": key, "deleted": True})


    async def _handle_import_detect(self, request: web.Request) -> web.Response:
        candidate = _HA_CONFIG_DIR / _AIRSEND_YAML_FILENAME
        try:
            yaml_text = await asyncio.to_thread(candidate.read_text, encoding="utf-8")
        except FileNotFoundError:
            return web.json_response({"found": False})
        except OSError as exc:
            _LOGGER.warning("Could not read %s: %s", candidate, exc)
            return web.json_response({"found": False})

        return web.json_response({
            "found": True,
            "path": str(candidate),
            "yaml_text": yaml_text,
        })

    async def _handle_import_preview(self, request: web.Request) -> web.Response:
        body = await request.json()
        yaml_text = body.get("yaml_text", "")
        if not yaml_text.strip():
            raise web.HTTPBadRequest(text="empty yaml_text")

        box_slug = body.get("box") or next(iter(self._boxes), None)
        if box_slug not in self._boxes:
            raise web.HTTPBadRequest(text="unknown box")

        try:
            yaml_devices = load_yaml_devices(yaml_text)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))

        existing_devices = {
            d.key: {
                "channel_id": d.channel_id,
                "channel_source": d.channel_source,
                "domain": d.domain,
                "kind": d.kind,
                "options": d.options,
            }
            for d in self._registry.all()
        }

        def protocol_name_for(channel_id: int) -> str | None:
            return self._catalog.protocol_name_for(box_slug, channel_id)

        rows = parse_airsend_yaml(
            yaml_devices,
            protocol_name_for,
            existing_devices,
            box_slug,
            KIND_TO_DOMAIN,
        )
        return web.json_response({"rows": rows, "available_kinds": list(KIND_TO_DOMAIN.keys())})

    def _validate_import_row(self, row: dict[str, Any]) -> str | None:
        action = row.get("action", "skip")
        if action in ("skip", "keep_existing"):
            return None

        row_key = row.get("key", "?")
        if action not in ("import", "overwrite"):
            return f"{row_key}: unknown action '{action}'"

        kind = row.get("kind")
        friendly_name = str(row.get("friendly_name", "")).strip()
        if not kind or not friendly_name:
            return f"{row_key}: kind/friendly_name missing"
        if kind not in KIND_TO_DOMAIN:
            return f"{row_key}: unknown kind '{kind}'"
        return None

    def _process_import_row(self, row: dict[str, Any]) -> tuple[str, str | None]:
        action = row.get("action", "skip")
        row_key = row.get("key", "?")

        if action in ("skip", "keep_existing"):
            return "skipped", None

        validation_error = self._validate_import_row(row)
        if validation_error is not None:
            return "error", validation_error

        kind = row.get("kind")
        friendly_name = str(row.get("friendly_name", "")).strip()
        removed_existing = self._maybe_remove_existing(row, row_key, action)

        try:
            self._create_device(
                box_slug=row.get("box"),
                channel_id=row["channel_id"],
                channel_source=row["channel_source"],
                protocol_name=row.get("protocol_name"),
                kind=kind,
                friendly_name=friendly_name,
                options=row.get("options") or {},
                source_of_creation="yaml_import",
            )
        except web.HTTPBadRequest as exc:
            return "error", f"{row_key}: {exc.text}"

        return "overwritten" if removed_existing else "added", None

    def _maybe_remove_existing(self, row: dict[str, Any], row_key: str, action: str) -> bool:
        if action != "overwrite":
            return False
        existing_key = row.get("conflict_with") or row_key
        existing = self._registry.get(existing_key)
        if existing is None:
            return False
        self._mqtt_bridge.remove_discovery(existing)
        self._registry.remove(existing_key)
        return True

    async def _handle_import_commit(self, request: web.Request) -> web.Response:
        body = await request.json()
        rows = body.get("rows")
        if not isinstance(rows, list):
            raise web.HTTPBadRequest(text="'rows' must be a list")

        validation_errors: list[str] = []
        for row in rows:
            error = self._validate_import_row(row)
            if error is not None:
                validation_errors.append(error)

        if validation_errors:
            return web.json_response(
                {"added": 0, "overwritten": 0, "skipped": 0, "errors": validation_errors}
            )

        added = overwritten = skipped = 0
        errors: list[str] = []

        for row in rows:
            outcome, error = self._process_import_row(row)
            if error is not None:
                errors.append(error)
            elif outcome == "added":
                added += 1
            elif outcome == "overwritten":
                overwritten += 1
            else:
                skipped += 1

        return web.json_response(
            {"added": added, "overwritten": overwritten, "skipped": skipped, "errors": errors}
        )

    async def _handle_backup_export(self, request: web.Request) -> web.Response:
        backup = build_backup(self._registry.all())
        filename = f"airsend-hub-backup-{backup['exported_at']}.json"
        return web.Response(
            text=json.dumps(backup, indent=2, ensure_ascii=False),
            content_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    async def _handle_backup_import_preview(self, request: web.Request) -> web.Response:
        body = await request.json()
        raw = body.get("backup")
        if not isinstance(raw, dict):
            raise web.HTTPBadRequest(text="missing or invalid 'backup'")

        try:
            backup_devices = parse_backup(raw)
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))

        existing_devices = {
            d.key: {
                "box": d.box,
                "channel_id": d.channel_id,
                "channel_source": d.channel_source,
                "protocol_name": d.protocol_name,
                "kind": d.kind,
                "domain": d.domain,
                "friendly_name": d.friendly_name,
                "options": d.options,
                "source_of_creation": d.source_of_creation,
            }
            for d in self._registry.all()
        }

        rows = diff_backup_devices(
            backup_devices, existing_devices, set(self._boxes.keys()), set(KIND_TO_DOMAIN.keys())
        )
        return web.json_response({"rows": rows, "known_boxes": list(self._boxes.keys())})

    def _process_backup_row(self, row: dict[str, Any]) -> tuple[str, str | None]:
        action = row.get("action", "skip")
        key = row.get("key", "?")

        if action == "skip":
            return "skipped", None
        if action not in ("import", "overwrite"):
            return "error", f"{key}: unknown action '{action}'"

        kind = row.get("kind")
        if kind not in KIND_TO_DOMAIN:
            return "error", f"{key}: unknown kind '{kind}'"
        box_slug = row.get("box")
        if box_slug not in self._boxes:
            return "error", f"{key}: unknown box '{box_slug}'"
        friendly_name = str(row.get("friendly_name", "")).strip()
        if not friendly_name:
            return "error", f"{key}: {_FRIENDLY_NAME_EMPTY}"

        existing = self._registry.get(key)
        if existing is not None and action != "overwrite":
            return "error", f"{key}: already exists (choose 'overwrite' or 'skip')"

        removed_existing = existing is not None
        if removed_existing:
            self._mqtt_bridge.remove_discovery(existing)
            self._registry.remove(key)

        try:
            self._create_device(
                box_slug=box_slug,
                channel_id=row["channel_id"],
                channel_source=row["channel_source"],
                protocol_name=row.get("protocol_name"),
                kind=kind,
                friendly_name=friendly_name,
                options=row.get("options") or {},
                source_of_creation=row.get("source_of_creation") or "backup_import",
                key=key,
            )
        except web.HTTPBadRequest as exc:
            return "error", f"{key}: {exc.text}"

        return "overwritten" if removed_existing else "imported", None

    async def _handle_backup_import_commit(self, request: web.Request) -> web.Response:
        body = await request.json()
        rows = body.get("rows")
        if not isinstance(rows, list):
            raise web.HTTPBadRequest(text="'rows' must be a list")

        imported = overwritten = skipped = 0
        errors: list[str] = []

        for row in rows:
            outcome, error = self._process_backup_row(row)
            if error is not None:
                errors.append(error)
            elif outcome == "imported":
                imported += 1
            elif outcome == "overwritten":
                overwritten += 1
            else:
                skipped += 1

        return web.json_response(
            {"imported": imported, "overwritten": overwritten, "skipped": skipped, "errors": errors}
        )


def create_ingress_app(
    boxes_by_slug: dict[str, BoxConfig],
    client: AirSendClient,
    bind_manager: BindManager,
    inclusion: InclusionState,
    registry: DeviceRegistry,
    catalog: ProtocolCatalog,
    mqtt_bridge: MqttBridge,
    settings: RuntimeSettings,
) -> web.Application:
    api = InclusionApi(
        boxes_by_slug=boxes_by_slug,
        client=client,
        bind_manager=bind_manager,
        inclusion=inclusion,
        registry=registry,
        catalog=catalog,
        mqtt_bridge=mqtt_bridge,
        settings=settings,
    )
    registration = RegistrationApi(
        boxes_by_slug=boxes_by_slug,
        client=client,
        registry=registry,
    )
    registration.attach_to(api.app)
    return api.app
