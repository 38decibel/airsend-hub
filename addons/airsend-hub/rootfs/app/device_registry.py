"""
Registre persistant des appareils AirSend appris (mode ecoute, ajout manuel
ou import cloud ponctuel). Stocke dans /data/devices.json (volume persistant
standard des addons HA, survit aux redemarrages/mises a jour) - PAS gere par
Supervisor/options, c'est notre propre source de verite runtime, distincte de
la config utilisateur (boxes).

Cle de matching pour une trame RF entrante : (box_slug, channel.id, channel.source)
cf. hassapi.class.php::toBasicChannel() qui ne retient que (id, source) - on
prefixe par box_slug puisque plusieurs box peuvent coexister dans notre addon.
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
    key: str  # identifiant stable interne (slug genere a la creation)
    box: str  # slug de la box (BoxConfig.slug)
    channel_id: int
    channel_source: int
    protocol_name: str | None
    kind: str  # "1_bouton" | "on_off" | "volet_roulant" | "niveau"
    domain: str  # "button" | "switch" | "cover" | "sensor" | "binary_sensor" | "event"
    friendly_name: str
    options: dict[str, Any] = field(default_factory=dict)
    source_of_creation: str = "manual"  # "rf_listen" | "manual" | "cloud_import"

    def match_key(self) -> tuple[str, int, int]:
        return (self.box, self.channel_id, self.channel_source)


class DeviceRegistry:
    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self._path = path
        self._devices: dict[str, Device] = {}
        self._by_match: dict[tuple[str, int, int], Device] = {}
        self.load()

    # ------------------------------------------------------------------ #
    # Persistance
    # ------------------------------------------------------------------ #

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
        """Ecriture atomique (fichier temp + rename) pour eviter un registre
        corrompu en cas de crash pendant l'ecriture."""
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

    # ------------------------------------------------------------------ #
    # API
    # ------------------------------------------------------------------ #

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
        """Edition limitee a friendly_name/options (cf. UI Ingress) : ne touche
        jamais a channel_id/channel_source/kind/domain, qui restent geres via
        suppression + reinclusion pour eviter tout risque de desynchronisation
        entre le registre et les topics MQTT discovery deja publies (dont le
        composant depend du domain)."""
        device = self._devices.get(key)
        if device is None:
            return None
        if friendly_name is not None:
            device.friendly_name = friendly_name
        if options is not None:
            device.options = options
        self.save()
        return device
