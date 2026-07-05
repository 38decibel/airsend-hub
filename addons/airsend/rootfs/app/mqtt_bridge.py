"""
Pont MQTT : publie la discovery HA pour chaque device connu, republie les
etats decodes (recus depuis callback_server via on_state), et route les
commandes MQTT entrantes vers AirSendClient.transfer().

Utilise paho-mqtt (API callback classique, pas la variante asyncio - on
l'entoure de call_soon_threadsafe pour rester compatible avec la boucle
asyncio du reste de l'app, paho tournant sur son propre thread reseau interne).
"""

from __future__ import annotations

import asyncio
import json
import logging

import paho.mqtt.client as mqtt

from airsend_client import AirSendClient, AirSendError, BoxConfig
from device_registry import Device, DeviceRegistry
from domains import get_domain_module
from domains.topics import (
    AVAILABILITY_OFFLINE,
    AVAILABILITY_ONLINE,
    AVAILABILITY_TOPIC,
    DeviceTopics,
    build_device_info,
)
from inclusion import InclusionState
from net_utils import mac_from_link_local
from protocol_catalog import ProtocolCatalog
from runtime_settings import RuntimeSettings

_LOGGER = logging.getLogger("airsend.mqtt_bridge")

# Entites systeme (mode inclusion, reglages), independantes du device_registry
# (pas des appareils AirSend, mais des modes/reglages de l'addon lui-meme).
# Rattachees au device de la PREMIERE box configuree (limitation actuelle :
# le mode inclusion et les reglages sont partages entre toutes les box s'il y
# en a plusieurs - a revisiter si besoin de reglages par-box).
_INCLUSION_COMMAND_TOPIC = "airsend/inclusion/set"
_INCLUSION_STATE_TOPIC = "airsend/inclusion/state"
_INCLUSION_DISCOVERY_TOPIC = "homeassistant/switch/airsend_inclusion_mode/config"
_INCLUSION_CANDIDATES_TOPIC = "airsend/inclusion/candidates"

_RELIABILITY_COMMAND_TOPIC = "airsend/settings/reliability_min/set"
_RELIABILITY_STATE_TOPIC = "airsend/settings/reliability_min/state"
_RELIABILITY_DISCOVERY_TOPIC = "homeassistant/number/airsend_reliability_min/config"


class MqttBridge:
    def __init__(
        self,
        registry: DeviceRegistry,
        client: AirSendClient,
        boxes_by_slug: dict[str, BoxConfig],
        inclusion: InclusionState,
        catalog: ProtocolCatalog,
        settings: RuntimeSettings,
        host: str,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        use_ssl: bool = False,
    ) -> None:
        self._registry = registry
        self._client = client
        self._boxes_by_slug = boxes_by_slug
        self._inclusion = inclusion
        self._catalog = catalog
        self._settings = settings
        self._loop = asyncio.get_event_loop()
        self._candidates_task: asyncio.Task | None = None

        self._mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="airsend-addon")
        if username:
            self._mqtt.username_pw_set(username, password)
        if use_ssl:
            self._mqtt.tls_set()
        self._mqtt.will_set(AVAILABILITY_TOPIC, AVAILABILITY_OFFLINE, retain=True)
        self._mqtt.on_connect = self._on_connect
        self._mqtt.on_message = self._on_message

        self._host = host
        self._port = port

    # ------------------------------------------------------------------ #
    # Connexion
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        self._mqtt.connect_async(self._host, self._port)
        self._mqtt.loop_start()
        self._candidates_task = asyncio.create_task(self._candidates_publisher_loop())

    async def stop(self) -> None:
        if self._candidates_task is not None:
            self._candidates_task.cancel()
        self._mqtt.publish(AVAILABILITY_TOPIC, AVAILABILITY_OFFLINE, retain=True)
        self._mqtt.loop_stop()
        self._mqtt.disconnect()

    async def _candidates_publisher_loop(self) -> None:
        """Republie la liste des candidats d'inclusion en continu pendant que
        le mode est actif. Implementation volontairement simple (polling),
        suffisante tant que la fenetre d'inclusion reste courte (quelques
        minutes) - a event-driver si besoin plus tard."""
        while True:
            if self._inclusion.active:
                candidates = [
                    {
                        "box": c.box,
                        "channel_id": c.channel_id,
                        "channel_source": c.channel_source,
                        "protocol_name": c.protocol_name,
                        "suggested_kind": c.suggested_kind,
                    }
                    for c in self._inclusion.list_candidates()
                ]
                self._mqtt.publish(_INCLUSION_CANDIDATES_TOPIC, json.dumps(candidates), retain=False)
            await asyncio.sleep(2.0)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        _LOGGER.info("MQTT connected (reason_code=%s)", reason_code)
        client.publish(AVAILABILITY_TOPIC, AVAILABILITY_ONLINE, retain=True)
        client.subscribe("airsend/+/set")
        client.subscribe("airsend/+/set_position")
        client.subscribe(_INCLUSION_COMMAND_TOPIC)
        client.subscribe(_RELIABILITY_COMMAND_TOPIC)
        # Republie la discovery + le dernier etat connu de tous les devices a
        # chaque (re)connexion : couvre le cas d'un broker/HA redemarre.
        for device in self._registry.all():
            self.publish_discovery(device)
        self._publish_inclusion_discovery()
        self._publish_inclusion_state()
        self._publish_reliability_discovery()
        self._publish_reliability_state()
        for box in self._boxes_by_slug.values():
            self.publish_box_diagnostics(box)

    # ------------------------------------------------------------------ #
    # Bloc `device` par box (nom reel + modele detecte + MAC)
    # ------------------------------------------------------------------ #

    def _box_model(self, box_slug: str) -> str | None:
        is_duo = self._catalog.is_duo_best_effort(box_slug)
        if is_duo is True:
            return "AirSend Duo"
        if is_duo is False:
            return "AirSend"
        return None  # catalogue pas encore recupere

    def _device_info_for_box(self, box_slug: str) -> dict:
        box = self._boxes_by_slug.get(box_slug)
        name = box.name if box else box_slug
        mac = mac_from_link_local(box.localip) if box else None
        return build_device_info(
            identifier=box_slug,
            name=name,
            model=self._box_model(box_slug),
            mac=mac,
        )

    def _primary_box_slug(self) -> str | None:
        """cf. limitation notee plus haut : le mode inclusion et les reglages
        sont rattaches a la premiere box configuree tant qu'on ne gere qu'un
        etat global (pas encore per-box)."""
        return next(iter(self._boxes_by_slug), None)

    # ------------------------------------------------------------------ #
    # Entite systeme : mode inclusion (bloc "Configuration")
    # ------------------------------------------------------------------ #

    def _publish_inclusion_discovery(self) -> None:
        box_slug = self._primary_box_slug()
        device_info = (
            self._device_info_for_box(box_slug)
            if box_slug
            else build_device_info("airsend_addon", "AirSend")
        )
        config = {
            "name": "Mode inclusion",
            "object_id": "mode_inclusion",
            "has_entity_name": True,
            "unique_id": "airsend_inclusion_mode",
            "entity_category": "config",
            "command_topic": _INCLUSION_COMMAND_TOPIC,
            "state_topic": _INCLUSION_STATE_TOPIC,
            "payload_on": "ON",
            "payload_off": "OFF",
            "state_on": "ON",
            "state_off": "OFF",
            "availability_topic": AVAILABILITY_TOPIC,
            "payload_available": AVAILABILITY_ONLINE,
            "payload_not_available": AVAILABILITY_OFFLINE,
            "device": device_info,
        }
        self._mqtt.publish(_INCLUSION_DISCOVERY_TOPIC, json.dumps(config), retain=True)

    def _publish_inclusion_state(self) -> None:
        self._mqtt.publish(
            _INCLUSION_STATE_TOPIC,
            "ON" if self._inclusion.active else "OFF",
            retain=True,
        )

    # ------------------------------------------------------------------ #
    # Entite systeme : seuil de fiabilite (bloc "Configuration")
    # ------------------------------------------------------------------ #

    def _publish_reliability_discovery(self) -> None:
        box_slug = self._primary_box_slug()
        device_info = (
            self._device_info_for_box(box_slug)
            if box_slug
            else build_device_info("airsend_addon", "AirSend")
        )
        config = {
            "name": "Fiabilite minimale",
            "object_id": "reliability_min",
            "has_entity_name": True,
            "unique_id": "airsend_reliability_min",
            "entity_category": "config",
            "command_topic": _RELIABILITY_COMMAND_TOPIC,
            "state_topic": _RELIABILITY_STATE_TOPIC,
            "min": 0,
            "max": RuntimeSettings.RELIABILITY_MAX - 1,
            "step": 1,
            "mode": "slider",
            "availability_topic": AVAILABILITY_TOPIC,
            "payload_available": AVAILABILITY_ONLINE,
            "payload_not_available": AVAILABILITY_OFFLINE,
            "device": device_info,
        }
        self._mqtt.publish(_RELIABILITY_DISCOVERY_TOPIC, json.dumps(config), retain=True)

    def _publish_reliability_state(self) -> None:
        self._mqtt.publish(_RELIABILITY_STATE_TOPIC, str(self._settings.reliability_min), retain=True)

    # ------------------------------------------------------------------ #
    # Diagnostics par box (IPv4) - bloc "Diagnostic"
    # ------------------------------------------------------------------ #

    def publish_box_diagnostics(self, box: BoxConfig) -> None:
        """Publie une entite sensor (categorie diagnostic) affichant l'IPv4
        de la box. La MAC, elle, est exposee nativement via `connections`
        dans le bloc `device` (cf. _device_info_for_box) plutot qu'en entite
        separee - c'est l'emplacement standard HA pour ce genre d'identifiant."""
        object_id = f"{box.slug}_ipv4"
        topics = DeviceTopics.for_device("sensor", object_id)
        config = {
            "name": "Adresse IPv4",
            "object_id": object_id,
            "has_entity_name": True,
            "unique_id": f"airsend_{object_id}",
            "entity_category": "diagnostic",
            "state_topic": topics.state,
            "availability_topic": AVAILABILITY_TOPIC,
            "payload_available": AVAILABILITY_ONLINE,
            "payload_not_available": AVAILABILITY_OFFLINE,
            "device": self._device_info_for_box(box.slug),
        }
        self._mqtt.publish(topics.discovery, json.dumps(config), retain=True)
        self._mqtt.publish(topics.state, box.ipv4, retain=True)

    # ------------------------------------------------------------------ #
    # Discovery (appareils RF)
    # ------------------------------------------------------------------ #

    def publish_discovery(self, device: Device) -> None:
        module = get_domain_module(device.domain)
        if module is None:
            _LOGGER.warning("Unknown domain '%s' for device %s, skipping discovery", device.domain, device.key)
            return
        topics = DeviceTopics.for_device(module.COMPONENT, device.key)
        device_info = self._device_info_for_box(device.box)
        config = module.discovery_config(device, topics, device_info)
        self._mqtt.publish(topics.discovery, json.dumps(config), retain=True)
        _LOGGER.info("Published discovery for %s (%s) on %s", device.key, device.domain, topics.discovery)

    def remove_discovery(self, device: Device) -> None:
        module = get_domain_module(device.domain)
        if module is None:
            return
        topics = DeviceTopics.for_device(module.COMPONENT, device.key)
        self._mqtt.publish(topics.discovery, "", retain=True)  # payload vide = suppression cote HA

    # ------------------------------------------------------------------ #
    # Etat sortant (RF -> MQTT)
    # ------------------------------------------------------------------ #

    async def publish_state(self, device_key: str, stype: str, svalue: object, channel: dict) -> None:
        device = self._registry.get(device_key)
        if device is None:
            _LOGGER.warning("publish_state called for unknown device_key=%s", device_key)
            return

        module = get_domain_module(device.domain)
        if module is None:
            return

        for topic, payload in module.encode_state(device, stype, svalue):
            self._mqtt.publish(topic, payload, retain=True)
            _LOGGER.debug("Published state %s = %s", topic, payload)

    # ------------------------------------------------------------------ #
    # Commande entrante (MQTT -> RF / reglages)
    # ------------------------------------------------------------------ #

    def _on_message(self, client, userdata, msg) -> None:
        # Callback paho = thread reseau interne, on repasse sur la boucle
        # asyncio pour pouvoir faire l'appel HTTP vers AirSendWebService.
        asyncio.run_coroutine_threadsafe(self._handle_command(msg.topic, msg.payload.decode()), self._loop)

    async def _handle_command(self, topic: str, payload: str) -> None:
        if topic == _INCLUSION_COMMAND_TOPIC:
            if payload.upper() == "ON":
                self._inclusion.start()
            else:
                self._inclusion.stop()
            self._publish_inclusion_state()
            return

        if topic == _RELIABILITY_COMMAND_TOPIC:
            try:
                value = int(float(payload))
            except ValueError:
                _LOGGER.warning("Invalid reliability_min payload: %r", payload)
                return
            value = max(0, min(RuntimeSettings.RELIABILITY_MAX - 1, value))
            self._settings.reliability_min = value
            self._publish_reliability_state()
            _LOGGER.info("reliability_min updated to %s", value)
            return

        # topic attendu: airsend/<device_key>/set ou /set_position
        parts = topic.split("/")
        if len(parts) < 3:
            return
        device_key = parts[1]
        device = self._registry.get(device_key)
        if device is None:
            _LOGGER.warning("Command on unknown device_key=%s (topic=%s)", device_key, topic)
            return

        module = get_domain_module(device.domain)
        if module is None:
            return

        thingnotes = module.decode_command(device, topic, payload)
        if thingnotes is None:
            _LOGGER.debug("Command payload %r on %s not understood by domain %s", payload, topic, device.domain)
            return

        box = self._boxes_by_slug.get(device.box)
        if box is None:
            _LOGGER.error("Command for device %s references unknown box '%s'", device.key, device.box)
            return

        channel = {"id": device.channel_id, "source": device.channel_source}
        try:
            await self._client.transfer(box, channel=channel, thingnotes=thingnotes, wait=True)
        except AirSendError as exc:
            _LOGGER.warning("Failed to send command for device %s: %s", device.key, exc)
            return

        # Etat optimiste : la plupart des recepteurs RF (rolling-code
        # notamment) ne renvoient aucune confirmation de position exploitable
        # via le canal de callback (cf. callback_server.py, evenements avec
        # uid ignores). Sans ca, l'entite resterait affichee dans son ancien
        # etat indefiniment apres une commande reussie. C'est une
        # approximation assumee, pas une lecture reelle de l'etat materiel.
        optimistic = getattr(module, "encode_optimistic_state", None)
        if optimistic is not None:
            for state_topic, state_payload in optimistic(device, topic, payload):
                self._mqtt.publish(state_topic, state_payload, retain=True)
                _LOGGER.debug("Published optimistic state %s = %s", state_topic, state_payload)
