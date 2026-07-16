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
from net_utils import mac_from_link_local
from protocol_catalog import ProtocolCatalog
from runtime_settings import RuntimeSettings

_LOGGER = logging.getLogger("airsend.mqtt_bridge")

_RELIABILITY_COMMAND_TOPIC = "airsend/settings/reliability_min/set"

_BIND_DURATION_COMMAND_TOPIC = "airsend/settings/bind_duration/set"
_BIND_DURATION_STATE_TOPIC = "airsend/settings/bind_duration/state"
_BIND_DURATION_DISCOVERY_TOPIC = "homeassistant/number/bind_duration_airsend/config"

# Legacy : le switch "Mode inclusion" (switch.mode_inclusion) a existe
# jusqu'a la restructuration "1 device HA par element RF + inclusion
# exclusivement via l'UI Ingress" - retire car il n'exposait plus de flow
# utilisable seul (la confirmation d'un candidat en device est desormais
# verrouillee a une session d'ecoute Ingress, cf. inclusion_api.py). Le
# mecanisme interne (InclusionState.active, candidats) reste utilise par
# inclusion_api.py + callback_server.py, seule l'exposition MQTT disparait.
# On garde ces anciens topics ici UNIQUEMENT pour les vider au demarrage
# (retrait propre chez les utilisateurs deja installes), comme pour
# _LEGACY_RELIABILITY_DISCOVERY_TOPICS ci-dessous.
_LEGACY_INCLUSION_DISCOVERY_TOPICS = (
    "homeassistant/switch/inclusion_mode_airsend/config",
    "homeassistant/switch/airsend_inclusion_mode/config",  # forme encore plus ancienne
)
_LEGACY_INCLUSION_STATE_TOPIC = "airsend/inclusion/state"

# Legacy : l'entite "fiabilite minimale" (number.reliability_min) a existe
# jusqu'a la v0.1.11 puis a ete retiree (cf. callback_server.py - la borne
# basse est desormais fixe a 6, alignee sur jeeAirSend.php/Jeedom, non
# ajustable). On garde les anciens topics de discovery ici UNIQUEMENT pour
# publier une chaine vide dessus au demarrage (retrait propre de l'entite
# chez les utilisateurs deja installes) - cf. _cleanup_legacy_discovery_topics().
# _RELIABILITY_COMMAND_TOPIC est conserve tel quel (non renomme) uniquement
# pour reconnaitre et ignorer proprement d'anciens messages retenus sur ce
# topic (cf. _on_message) - pas une entite active.
_LEGACY_RELIABILITY_DISCOVERY_TOPICS = (
    "homeassistant/number/reliability_min_airsend/config",
    "homeassistant/number/airsend_reliability_min/config",
)

# Utilisees par _diagnostic_sensor_topics_and_config (cf. publish_box_diagnostics).
_SENSOR_COMPONENT = "sensor"
_DIAGNOSTIC_CATEGORY = "diagnostic"


class MqttBridge:
    def __init__(
        self,
        registry: DeviceRegistry,
        client: AirSendClient,
        boxes_by_slug: dict[str, BoxConfig],
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
        self._catalog = catalog
        self._settings = settings
        self._loop = asyncio.get_event_loop()
        self._health_task: asyncio.Task | None = None

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
        self._health_task = asyncio.create_task(self._health_poll_loop())

    def stop(self) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
        self._mqtt.publish(AVAILABILITY_TOPIC, AVAILABILITY_OFFLINE, retain=True)
        self._mqtt.loop_stop()
        self._mqtt.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        _LOGGER.info("MQTT connected (reason_code=%s)", reason_code)
        client.publish(AVAILABILITY_TOPIC, AVAILABILITY_ONLINE, retain=True)
        client.subscribe("airsend/+/set")
        client.subscribe("airsend/+/set_position")
        client.subscribe(_RELIABILITY_COMMAND_TOPIC)  # entite retiree, cf. constante
        client.subscribe(_BIND_DURATION_COMMAND_TOPIC)
        self._cleanup_legacy_discovery_topics()
        # Republie la discovery + le dernier etat connu de tous les devices a
        # chaque (re)connexion : couvre le cas d'un broker/HA redemarre.
        for device in self._registry.all():
            self.publish_discovery(device)
        self._publish_bind_duration_discovery()
        self._publish_bind_duration_state()
        for box in self._boxes_by_slug.values():
            self.publish_box_diagnostics(box)

    def _cleanup_legacy_discovery_topics(self) -> None:
        """
        Migration ponctuelle : efface les topics de discovery de l'ANCIEN
        schema (avant l'inversion "airsend_X" -> "X_airsend"), ainsi que les
        entites completement retirees (switch "Mode inclusion", fiabilite
        minimale). Publier un payload vide et retenu sur un topic de
        discovery MQTT est la methode standard pour supprimer une entite
        decouverte cote HA - on l'utilise ici pour eviter d'avoir a supprimer
        les anciennes entites a la main a chaque fois qu'on change le schema.
        Sans danger a rejouer : publier un payload vide sur un topic deja
        vide ne fait rien.
        """
        for device in self._registry.all():
            module = get_domain_module(device.domain)
            if module is None:
                continue
            legacy_topic = f"homeassistant/{module.COMPONENT}/airsend_{device.key}/config"
            self._mqtt.publish(legacy_topic, "", retain=True)

        for legacy_topic in _LEGACY_INCLUSION_DISCOVERY_TOPICS:
            self._mqtt.publish(legacy_topic, "", retain=True)
        self._mqtt.publish(_LEGACY_INCLUSION_STATE_TOPIC, "", retain=True)
        for legacy_topic in _LEGACY_RELIABILITY_DISCOVERY_TOPICS:
            self._mqtt.publish(legacy_topic, "", retain=True)
        self._mqtt.publish("airsend/settings/reliability_min/state", "", retain=True)
        for box in self._boxes_by_slug.values():
            legacy_ipv4_topic = f"homeassistant/sensor/airsend_{box.slug}_ipv4/config"
            self._mqtt.publish(legacy_ipv4_topic, "", retain=True)

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

    def _device_info_for_element(self, device: Device) -> dict:
        """Device HA dedie a un element RF (1 par device.key), rattache au
        device box via `via_device` - cf. discussion "1 device par element"
        remplacant l'ancien schema ou tous les elements partageaient le
        device box, ce qui empechait de nommer/zoner chaque volet/switch
        individuellement (le nom affiche heritait du prefixe du device box,
        et l'assignation de zone se faisait entite par entite)."""
        return build_device_info(
            identifier=device.key,
            name=device.friendly_name,
            via_device=device.box,
        )

    def _primary_box_slug(self) -> str | None:
        """L'entite reglage "Duree du bind" est rattachee a la premiere box
        configuree tant qu'on ne gere qu'un etat global (pas encore per-box)."""
        return next(iter(self._boxes_by_slug), None)

    # ------------------------------------------------------------------ #
    # Entite systeme : reglages (bloc "Configuration")
    # ------------------------------------------------------------------ #

    def _publish_bind_duration_discovery(self) -> None:
        box_slug = self._primary_box_slug()
        device_info = (
            self._device_info_for_box(box_slug)
            if box_slug
            else build_device_info("airsend_addon", "AirSend")
        )
        config = {
            "name": "Duree du bind",
            "default_entity_id": "number.bind_duration",
            "has_entity_name": True,
            "unique_id": "bind_duration_airsend",
            "entity_category": "config",
            "command_topic": _BIND_DURATION_COMMAND_TOPIC,
            "state_topic": _BIND_DURATION_STATE_TOPIC,
            "unit_of_measurement": "s",
            "min": 60,
            "max": 86400,
            "step": 60,
            "mode": "box",
            "availability_topic": AVAILABILITY_TOPIC,
            "payload_available": AVAILABILITY_ONLINE,
            "payload_not_available": AVAILABILITY_OFFLINE,
            "device": device_info,
        }
        self._mqtt.publish(_BIND_DURATION_DISCOVERY_TOPIC, json.dumps(config), retain=True)

    def _publish_bind_duration_state(self) -> None:
        self._mqtt.publish(_BIND_DURATION_STATE_TOPIC, str(int(self._settings.bind_duration_s)), retain=True)

    # ------------------------------------------------------------------ #
    # Diagnostics par box (IPv4) - bloc "Diagnostic"
    # ------------------------------------------------------------------ #

    def _diagnostic_sensor_topics_and_config(
        self, box: BoxConfig, suffix: str, name: str, extra: dict | None = None
    ) -> tuple[DeviceTopics, dict]:
        """Construit (topics, config discovery) pour une entite sensor
        diagnostic de box (IPv4/statut/version partagent tous la meme forme,
        cf. publish_box_diagnostics) - evite de repeter les 8 memes cles
        (dont les literaux "sensor"/"diagnostic") trois fois."""
        object_id = f"{box.slug}_{suffix}"
        topics = DeviceTopics.for_device(_SENSOR_COMPONENT, object_id)
        config = {
            "name": name,
            "default_entity_id": f"{_SENSOR_COMPONENT}.{object_id}",
            "has_entity_name": True,
            "unique_id": f"{object_id}_airsend",
            "entity_category": _DIAGNOSTIC_CATEGORY,
            "state_topic": topics.state,
            "availability_topic": AVAILABILITY_TOPIC,
            "payload_available": AVAILABILITY_ONLINE,
            "payload_not_available": AVAILABILITY_OFFLINE,
            "device": self._device_info_for_box(box.slug),
        }
        if extra:
            config.update(extra)
        return topics, config

    def publish_box_diagnostics(self, box: BoxConfig) -> None:
        """Publie les entites sensor (categorie diagnostic) : IPv4, statut et
        version du service AirSendWebService. La MAC, elle, est exposee
        nativement via `connections` dans le bloc `device` (cf.
        _device_info_for_box) plutot qu'en entite separee - c'est
        l'emplacement standard HA pour ce genre d'identifiant.

        NOTE : /service/status interroge le binaire AirSendWebService
        lui-meme (le moteur RF local partage), pas une box precise - si
        plusieurs box sont configurees, ce statut/version sera identique
        pour toutes (c'est le meme service qui les sert toutes, cf.
        airsend_client.py). Rattache quand meme au diagnostic de chaque box
        pour rester visible sans introduire un device "addon" a part."""
        ipv4_topics, ipv4_config = self._diagnostic_sensor_topics_and_config(box, "ipv4", "Adresse IPv4")
        self._mqtt.publish(ipv4_topics.discovery, json.dumps(ipv4_config), retain=True)
        self._mqtt.publish(ipv4_topics.state, box.ipv4, retain=True)

        status_topics, status_config = self._diagnostic_sensor_topics_and_config(
            box, "service_status", "Statut du service"
        )
        self._mqtt.publish(status_topics.discovery, json.dumps(status_config), retain=True)

        version_topics, version_config = self._diagnostic_sensor_topics_and_config(
            box, "service_version", "Version du service"
        )
        self._mqtt.publish(version_topics.discovery, json.dumps(version_config), retain=True)

    async def _refresh_box_service_health(self) -> None:
        """Interroge GET /service/status une seule fois (service partage,
        cf. note plus haut) et republie le resultat sur les entites
        diagnostic de chaque box configuree."""
        try:
            result = await self._client.get_status()
            is_ok = isinstance(result, dict)
            version = result.get("version") if is_ok else None
        except AirSendError as exc:
            _LOGGER.debug("service/status check failed: %s", exc)
            is_ok = False
            version = None

        for box in self._boxes_by_slug.values():
            status_topics = DeviceTopics.for_device("sensor", f"{box.slug}_service_status")
            version_topics = DeviceTopics.for_device("sensor", f"{box.slug}_service_version")
            self._mqtt.publish(status_topics.state, "actif" if is_ok else "inactif", retain=True)
            if version is not None:
                self._mqtt.publish(version_topics.state, str(version), retain=True)

    async def _health_poll_loop(self, interval_s: float = 60.0) -> None:
        while True:
            await self._refresh_box_service_health()
            await asyncio.sleep(interval_s)

    # ------------------------------------------------------------------ #
    # Discovery (appareils RF)
    # ------------------------------------------------------------------ #

    def publish_discovery(self, device: Device) -> None:
        module = get_domain_module(device.domain)
        if module is None:
            _LOGGER.warning("Unknown domain '%s' for device %s, skipping discovery", device.domain, device.key)
            return
        topics = DeviceTopics.for_device(module.COMPONENT, device.key)
        device_info = self._device_info_for_element(device)
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

    def publish_state(self, device_key: str, stype: str, svalue: object, channel: dict) -> None:
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

    def _handle_bind_duration_command(self, payload: str) -> None:
        try:
            value = max(60.0, min(86400.0, float(payload)))
        except ValueError:
            _LOGGER.warning("Invalid bind_duration payload: %r", payload)
            return
        self._settings.bind_duration_s = value
        self._publish_bind_duration_state()
        _LOGGER.info(
            "bind_duration_s updated to %s (effectif au prochain renouvellement de bind)",
            value,
        )

    async def _handle_device_command(self, topic: str, payload: str) -> None:
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

    async def _handle_command(self, topic: str, payload: str) -> None:
        if topic == _RELIABILITY_COMMAND_TOPIC:
            # Entite retiree (cf. constante ci-dessus) : un message peut
            # encore arriver une seule fois si HA avait un payload retenu
            # sur ce topic avant la mise a jour. On l'ignore sciemment.
            _LOGGER.debug("Ignoring stale message on removed reliability_min topic")
        elif topic == _BIND_DURATION_COMMAND_TOPIC:
            self._handle_bind_duration_command(payload)
        else:
            await self._handle_device_command(topic, payload)
