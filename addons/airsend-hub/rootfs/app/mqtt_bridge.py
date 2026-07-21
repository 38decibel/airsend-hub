"""
MQTT Bridge: publishes HA discovery data for each known device, 
republishes decoded states (received from `callback_server` via `on_state`), 
and routes incoming MQTT commands to `AirSendClient.transfer()`.

Uses `paho-mqtt` (standard callback API, not the `asyncio` variant—wrapped
in `call_soon_threadsafe` to maintain compatibility with the rest of the app's
`asyncio` loop, as `paho` runs on its own internal network thread).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

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

_LEGACY_INCLUSION_DISCOVERY_TOPICS = (
    "homeassistant/switch/inclusion_mode_airsend/config",
    "homeassistant/switch/airsend_inclusion_mode/config",
)
_LEGACY_INCLUSION_STATE_TOPIC = "airsend/inclusion/state"

_LEGACY_RELIABILITY_DISCOVERY_TOPICS = (
    "homeassistant/number/reliability_min_airsend/config",
    "homeassistant/number/airsend_reliability_min/config",
)

_SENSOR_COMPONENT = "sensor"
_DIAGNOSTIC_CATEGORY = "diagnostic"

_COVER_STOP_REACHED_RATIO = 0.5


@dataclass
class _CoverMotion:

    task: asyncio.Task
    motion_state: str
    started_at: float
    travel_time_s: float


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
        self._cover_tasks: dict[str, _CoverMotion] = {}

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


    async def start(self) -> None:
        self._mqtt.connect_async(self._host, self._port)
        self._mqtt.loop_start()
        self._health_task = asyncio.create_task(self._health_poll_loop())

    def stop(self) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
        for motion in self._cover_tasks.values():
            motion.task.cancel()
        self._mqtt.publish(AVAILABILITY_TOPIC, AVAILABILITY_OFFLINE, retain=True)
        self._mqtt.loop_stop()
        self._mqtt.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        _LOGGER.info("MQTT connected (reason_code=%s)", reason_code)
        client.publish(AVAILABILITY_TOPIC, AVAILABILITY_ONLINE, retain=True)
        client.subscribe("airsend/+/set")
        client.subscribe("airsend/+/set_position")
        client.subscribe(_RELIABILITY_COMMAND_TOPIC)
        client.subscribe(_BIND_DURATION_COMMAND_TOPIC)
        self._cleanup_legacy_discovery_topics()
        for device in self._registry.all():
            self.publish_discovery(device)
        self._publish_bind_duration_discovery()
        self._publish_bind_duration_state()
        for box in self._boxes_by_slug.values():
            self.publish_box_diagnostics(box)

    def _cleanup_legacy_discovery_topics(self) -> None:

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


    def _box_model(self, box_slug: str) -> str | None:
        is_duo = self._catalog.is_duo_best_effort(box_slug)
        if is_duo is True:
            return "AirSend Duo"
        if is_duo is False:
            return "AirSend"
        return None

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

        return build_device_info(
            identifier=device.key,
            name=device.friendly_name,
            via_device=device.box,
        )

    def _primary_box_slug(self) -> str | None:

        return next(iter(self._boxes_by_slug), None)


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


    def _diagnostic_sensor_topics_and_config(
        self, box: BoxConfig, suffix: str, name: str, extra: dict | None = None
    ) -> tuple[DeviceTopics, dict]:
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
        self._mqtt.publish(topics.discovery, "", retain=True)


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


    def _on_message(self, client, userdata, msg) -> None:
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
            "bind_duration_s updated to %s (effective upon the next bind renewal)",
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

        optimistic = getattr(module, "encode_optimistic_state", None)
        if optimistic is not None:
            for state_topic, state_payload in optimistic(device, topic, payload):
                self._mqtt.publish(state_topic, state_payload, retain=True)
                _LOGGER.debug("Published optimistic state %s = %s", state_topic, state_payload)

        motion_fn = getattr(module, "motion_command", None)
        if motion_fn is not None:
            self._apply_cover_motion(device, module, motion_fn(device, topic, payload))


    def _apply_cover_motion(self, device: Device, module, motion: str | None) -> None:
        if motion == "stop":
            self._handle_cover_stop(device)
        elif motion is not None:
            self._start_cover_motion(device, motion, module.travel_time_s(device))

    def _start_cover_motion(self, device: Device, motion_state: str, travel_time_s: float) -> None:
        old = self._cover_tasks.pop(device.key, None)
        if old is not None:
            old.task.cancel()
        task = asyncio.create_task(self._cover_motion_timer(device, motion_state, travel_time_s))
        self._cover_tasks[device.key] = _CoverMotion(
            task=task,
            motion_state=motion_state,
            started_at=self._loop.time(),
            travel_time_s=travel_time_s,
        )

    def _handle_cover_stop(self, device: Device) -> None:

        motion = self._cover_tasks.pop(device.key, None)
        if motion is None:
            return

        motion.task.cancel()

        elapsed = self._loop.time() - motion.started_at
        ratio = elapsed / motion.travel_time_s if motion.travel_time_s > 0 else 1.0
        reached_destination = ratio >= _COVER_STOP_REACHED_RATIO

        if motion.motion_state == "opening":
            final_state = "open" if reached_destination else "closed"
        else:
            final_state = "closed" if reached_destination else "open"

        topics = DeviceTopics.for_device("cover", device.key)
        self._mqtt.publish(topics.state, final_state, retain=True)
        _LOGGER.debug(
            "Cover %s stopped after %.1fs/%.1fs (%s) -> assumed %s",
            device.key,
            elapsed,
            motion.travel_time_s,
            motion.motion_state,
            final_state,
        )

    async def _cover_motion_timer(self, device: Device, motion_state: str, travel_time_s: float) -> None:

        topics = DeviceTopics.for_device("cover", device.key)
        try:
            await asyncio.sleep(travel_time_s)
        finally:
            self._cover_tasks.pop(device.key, None)

        final_state = "open" if motion_state == "opening" else "closed"
        self._mqtt.publish(topics.state, final_state, retain=True)
        _LOGGER.debug("Cover %s reached assumed %s after %.1fs", device.key, final_state, travel_time_s)

    async def _handle_command(self, topic: str, payload: str) -> None:
        if topic == _RELIABILITY_COMMAND_TOPIC:
            _LOGGER.debug("Ignoring stale message on removed reliability_min topic")
        elif topic == _BIND_DURATION_COMMAND_TOPIC:
            self._handle_bind_duration_command(payload)
        else:
            await self._handle_device_command(topic, payload)
