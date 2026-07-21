"""
Persistent registry of learned AirSend devices (listening mode, manual addition,
or one-off cloud import). Stored in /data/devices.json (standard persistent
volume for HA apps; survives restarts/updates)—NOT managed by
Supervisor/options; this is our own runtime source of truth, distinct from
user configuration (boxes).

Matching key for an incoming RF frame: (box_slug, channel.id, channel.source)
We prefix this with box_slug since multiple boxes can coexist within our app.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Any

_LOGGER = logging.getLogger("airsend.registry")

DEFAULT_PATH = "/data/devices.json"


@dataclass
class Device:
    key: str
    box: str
    channel_id: int
    channel_source: int
    protocol_name: str | None
    kind: str
    domain: str
    friendly_name: str
    options: dict[str, Any] = field(default_factory=dict)
    source_of_creation: str = "manual"

    def match_key(self) -> tuple[str, int, int]:
        return (self.box, self.channel_id, self.channel_source)


class DeviceRegistry:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self._path = path
        self._devices: dict[str, Device] = {}
        self._by_match: dict[tuple[str, int, int], Device] = {}
        self.load()


    def load(self) -> None:
        if not os.path.exists(self._path):
            _LOGGER.info("No existing device registry at %s, starting empty", self._path)
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError):
            _LOGGER.exception("Failed to load %s, starting empty to avoid crash-loop", self._path)
            return

        for key, payload in raw.items():
            try:
                device = Device(key=key, **payload)
            except TypeError as exc:
                _LOGGER.warning("Skipping malformed device entry %s: %s", key, exc)
                continue
            self._devices[key] = device
            self._by_match[device.match_key()] = device
        _LOGGER.info("Loaded %d device(s) from registry", len(self._devices))

    def save(self) -> None:
        """Atomic write (temporary file + rename) to avoid
        a corrupted registry in the event of a crash during writing."""
        payload = {}
        for key, device in self._devices.items():
            data = asdict(device)
            data.pop("key")
            payload[key] = data

        dir_name = os.path.dirname(self._path) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".devices_", suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise


    def match(self, box_slug: str, channel_id: int, channel_source: int) -> Device | None:
        return self._by_match.get((box_slug, channel_id, channel_source))

    def get(self, key: str) -> Device | None:
        return self._devices.get(key)

    def all(self) -> list[Device]:
        return list(self._devices.values())

    def add(self, device: Device) -> None:
        self._devices[device.key] = device
        self._by_match[device.match_key()] = device
        self.save()

    def remove(self, key: str) -> Device | None:
        device = self._devices.pop(key, None)
        if device is not None:
            self._by_match.pop(device.match_key(), None)
            self.save()
        return device

    def update(
        self,
        key: str,
        friendly_name: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> Device | None:
        """Limited to friendly_name/options (see Ingress UI): never affects 
        channel_id/channel_source/kind/domain, which remain managed via deletion 
        and re-inclusion to avoid any risk of desynchronization between the 
        registry and the already published MQTT discovery topics (where the 
        component depends on the domain)."""
        device = self._devices.get(key)
        if device is None:
            return None
        if friendly_name is not None:
            device.friendly_name = friendly_name
        if options is not None:
            device.options = options
        self.save()
        return device
