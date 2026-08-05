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
from catalog.protocol_catalog import ProtocolCatalog
from core.airsend_client import AirSendClient, AirSendError, BoxConfig
from core.net_utils import mac_from_link_local
from domains import get_domain_module
from domains.topics import (
    AVAILABILITY_OFFLINE,
    AVAILABILITY_ONLINE,
    AVAILABILITY_TOPIC,
    DeviceTopics,
    build_device_info,
)
from registry.device_registry import Device, DeviceRegistry
from runtime_settings import RuntimeSettings

_LOGGER = logging.getLogger("airsend.mqtt_bridge")

_RELIABILITY_COMMAND_TOPIC = "airsend/settings/reliability_min/set"

_BIND_DURATION_COMMAND_TOPIC = "airsend/settings/bind_duration/set"
_BIND_DURATION_STATE_TOPIC = "airsend/settings/bind_duration/state"
_BIND_DURATION_DISCOVERY_TOPIC = "homeassistant/number/bind_duration_airsend/config"

_CAPTURE_UNKNOWN_COMMAND_TOPIC = "airsend/settings/capture_unknown_events/set"
_CAPTURE_UNKNOWN_STATE_TOPIC = "airsend/settings/capture_unknown_events/state"
_CAPTURE_UNKNOWN_DISCOVERY_TOPIC = "homeassistant/switch/capture_unknown_events_airsend/config"
_CAPTURE_UNKNOWN_PAYLOAD_ON = "ON"
_CAPTURE_UNKNOWN_PAYLOAD_OFF = "OFF"

_RF_INBOX_STATE_TOPIC = "airsend/rf_inbox/state"
_RF_INBOX_DISCOVERY_TOPIC = "homeassistant/event/rf_inbox_airsend/config"

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
    # Position (0-100) at the moment this motion started.  None when the cover
    # has no travel_time option and position tracking is disabled.
    start_position: float | None = None
    # Position requested via set_position.  When set, the timer runs only for
    # the partial travel duration and then sends STOP automatically.
    target_position: float | None = None


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
        # Last known position (0-100) for volet_roulant covers with travel_time.
        self._cover_positions: dict[str, float] = {}

        self._mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="airsend-addon")
        if username:
            self._mqtt.username_pw_set(username, password)
        if use_ssl:
            self._mqtt.tls_set()
        self._mqtt.will_set(AVAILABILITY_TOPIC, AVAILABILITY_OFFLINE, retain=True)
        self._mqtt.on_connect = self._on_connect
        self._mqtt.on_connect_fail = self._on_connect_fail
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
        # reason_code is a ReasonCode object in paho v2; value 0 means success.
        rc_value = reason_code.value if hasattr(reason_code, "value") else int(reason_code)
        if rc_value != 0:
            _LOGGER.error(
                "MQTT connection refused (reason_code=%s). "
                "Check MQTT credentials (MQTT_USER / MQTT_PASS). "
                "Stopping reconnect loop.",
                reason_code,
            )
            # Disable automatic reconnection for permanent errors (auth failure, etc.)
            client.loop_stop()
            return

        _LOGGER.info("MQTT connected successfully")
        client.publish(AVAILABILITY_TOPIC, AVAILABILITY_ONLINE, retain=True)
        client.subscribe("airsend/+/set")
        client.subscribe("airsend/+/set_position")
        client.subscribe(_RELIABILITY_COMMAND_TOPIC)
        client.subscribe(_BIND_DURATION_COMMAND_TOPIC)
        client.subscribe(_CAPTURE_UNKNOWN_COMMAND_TOPIC)
        self._cleanup_legacy_discovery_topics()
        for device in self._registry.all():
            self.publish_discovery(device)
        self._publish_bind_duration_discovery()
        self._publish_bind_duration_state()
        self._publish_capture_unknown_discovery()
        self._publish_capture_unknown_state()
        self._publish_rf_inbox_discovery()
        for box in self._boxes_by_slug.values():
            self.publish_box_diagnostics(box)

    def _on_connect_fail(self, client, userdata) -> None:
        _LOGGER.warning("MQTT connection attempt failed (network unreachable?), paho will retry")

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

    def _publish_capture_unknown_discovery(self) -> None:
        box_slug = self._primary_box_slug()
        device_info = (
            self._device_info_for_box(box_slug)
            if box_slug
            else build_device_info("airsend_addon", "AirSend")
        )
        config = {
            "name": "Capture protocoles inconnus",
            "default_entity_id": "switch.capture_unknown_events",
            "has_entity_name": True,
            "unique_id": "capture_unknown_events_airsend",
            "entity_category": "config",
            "command_topic": _CAPTURE_UNKNOWN_COMMAND_TOPIC,
            "state_topic": _CAPTURE_UNKNOWN_STATE_TOPIC,
            "payload_on": _CAPTURE_UNKNOWN_PAYLOAD_ON,
            "payload_off": _CAPTURE_UNKNOWN_PAYLOAD_OFF,
            "state_on": _CAPTURE_UNKNOWN_PAYLOAD_ON,
            "state_off": _CAPTURE_UNKNOWN_PAYLOAD_OFF,
            "availability_topic": AVAILABILITY_TOPIC,
            "payload_available": AVAILABILITY_ONLINE,
            "payload_not_available": AVAILABILITY_OFFLINE,
            "device": device_info,
        }
        self._mqtt.publish(_CAPTURE_UNKNOWN_DISCOVERY_TOPIC, json.dumps(config), retain=True)

    def _publish_capture_unknown_state(self) -> None:
        payload = _CAPTURE_UNKNOWN_PAYLOAD_ON if self._settings.capture_unknown_events else _CAPTURE_UNKNOWN_PAYLOAD_OFF
        self._mqtt.publish(_CAPTURE_UNKNOWN_STATE_TOPIC, payload, retain=True)

    def set_capture_unknown_events(self, enabled: bool) -> None:
        """Single entry point for toggling promiscuous capture, used both by
        the MQTT switch command and by the Ingress `/api/settings` route, so
        the two stay consistent."""
        self._settings.capture_unknown_events = enabled
        self._publish_capture_unknown_state()
        _LOGGER.info("capture_unknown_events updated to %s", enabled)

    def _publish_rf_inbox_discovery(self) -> None:
        """Publish MQTT discovery for the RF inbox event entity.

        The entity is attached to the primary box device and fires on every
        valid RF frame received, whether or not it matches a configured device.
        """
        box_slug = self._primary_box_slug()
        device_info = (
            self._device_info_for_box(box_slug)
            if box_slug
            else build_device_info("airsend_addon", "AirSend")
        )
        config = {
            "name": "Dernière trame RF",
            "default_entity_id": "event.rf_inbox",
            "has_entity_name": True,
            "unique_id": "rf_inbox_airsend",
            "state_topic": _RF_INBOX_STATE_TOPIC,
            "event_types": ["rf_action"],
            "availability_topic": AVAILABILITY_TOPIC,
            "payload_available": AVAILABILITY_ONLINE,
            "payload_not_available": AVAILABILITY_OFFLINE,
            "device": device_info,
        }
        self._mqtt.publish(_RF_INBOX_DISCOVERY_TOPIC, json.dumps(config), retain=True)

    def publish_rf_inbox_event(
        self,
        box_slug: str,
        channel_id: int,
        channel_source: int,
        protocol_name: str | None,
        action: str | None,
        reliability: int | None,
        notes: list | None = None,
    ) -> None:
        """Publish a single RF frame as an HA MQTT event on the inbox topic.

        Called for every valid RF frame (known or unknown device) by
        CallbackServer before device matching.
        """
        payload = json.dumps({
            "event_type": "rf_action",
            "box": box_slug,
            "channel_id": channel_id,
            "channel_source": channel_source,
            "protocol_name": protocol_name,
            "action": action,
            "reliability": reliability,
            "notes": notes or [],
        })
        self._mqtt.publish(_RF_INBOX_STATE_TOPIC, payload, retain=False)


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

    def _handle_capture_unknown_command(self, payload: str) -> None:
        if payload not in (_CAPTURE_UNKNOWN_PAYLOAD_ON, _CAPTURE_UNKNOWN_PAYLOAD_OFF):
            _LOGGER.warning("Invalid capture_unknown_events payload: %r", payload)
            return
        self.set_capture_unknown_events(payload == _CAPTURE_UNKNOWN_PAYLOAD_ON)

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

        # Extract the optional target_position injected by cover.decode_command
        # for volet_roulant set_position commands.  It must not be forwarded to
        # the box — strip it before building the transfer payload.
        target_position: float | None = None
        if "_target_position" in thingnotes:
            target_position = float(thingnotes.pop("_target_position"))

        box = self._boxes_by_slug.get(device.box)
        if box is None:
            _LOGGER.error("Command for device %s references unknown box '%s'", device.key, device.box)
            return

        channel = {"id": device.channel_id, "source": device.channel_source}

        if target_position is not None:
            await self._handle_set_position(device, module, box, channel, target_position)
        else:
            await self._send_standard_command(device, module, box, channel, thingnotes, topic, payload)


    async def _send_standard_command(
        self,
        device: Device,
        module,
        box: BoxConfig,
        channel: dict,
        thingnotes: dict,
        topic: str,
        payload: str,
    ) -> None:
        """Transfer ``thingnotes`` to the box then publish optimistic/motion state."""
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

    async def _handle_set_position(
        self,
        device: Device,
        module,
        box: BoxConfig,
        channel: dict,
        target_position: float,
    ) -> None:
        """Send a directional RF command and start a partial-travel motion timer
        to reach ``target_position`` (0-100) on a volet_roulant with travel_time.
        """
        current = self._cover_positions.get(device.key, 0.0)
        if abs(target_position - current) < 1.0:
            _LOGGER.debug("Cover %s already at target %.0f%%, ignoring", device.key, target_position)
            return
        direction_up = target_position > current
        rf_value = 35 if direction_up else 34  # UP / DOWN (_STATE_UP / _STATE_DOWN)
        motion_state = "opening" if direction_up else "closing"
        directional_notes = {"notes": [{"method": 1, "type": 0, "value": rf_value}]}
        try:
            await self._client.transfer(box, channel=channel, thingnotes=directional_notes, wait=True)
        except AirSendError as exc:
            _LOGGER.warning("Failed to send set_position direction for device %s: %s", device.key, exc)
            return
        # Publish the transitional state optimistically.
        pos_topics = DeviceTopics.for_device("cover", device.key)
        self._mqtt.publish(pos_topics.state, motion_state, retain=True)
        tt = module.travel_time_s(device)
        self._start_cover_motion(device, motion_state, tt, current, target_position)

    def _apply_cover_motion(
        self,
        device: Device,
        module,
        motion: str | None,
        target_position: float | None = None,
    ) -> None:
        if motion == "stop":
            self._handle_cover_stop(device)
        elif motion is not None:
            tt = module.travel_time_s(device)
            current = self._cover_positions.get(device.key)
            self._start_cover_motion(device, motion, tt, current, target_position)

    def _start_cover_motion(
        self,
        device: Device,
        motion_state: str,
        travel_time_s: float,
        start_position: float | None = None,
        target_position: float | None = None,
    ) -> None:
        old = self._cover_tasks.pop(device.key, None)
        if old is not None:
            old.task.cancel()

        # When a target is given, run the timer only for the partial travel duration.
        if target_position is not None and start_position is not None and travel_time_s > 0:
            delta = abs(target_position - start_position)
            timer_duration = delta / 100.0 * travel_time_s
        else:
            timer_duration = travel_time_s

        task = asyncio.create_task(
            self._cover_motion_timer(device, motion_state, travel_time_s, timer_duration)
        )
        self._cover_tasks[device.key] = _CoverMotion(
            task=task,
            motion_state=motion_state,
            started_at=self._loop.time(),
            travel_time_s=travel_time_s,
            start_position=start_position,
            target_position=target_position,
        )

    def _handle_cover_stop(self, device: Device) -> None:

        motion = self._cover_tasks.pop(device.key, None)
        if motion is None:
            return

        motion.task.cancel()

        elapsed = self._loop.time() - motion.started_at
        topics = DeviceTopics.for_device("cover", device.key)

        if motion.start_position is not None and motion.travel_time_s > 0:
            # Position-tracking mode: compute estimated position from elapsed time.
            direction = 1.0 if motion.motion_state == "opening" else -1.0
            progress = min(elapsed / motion.travel_time_s, 1.0) * 100.0
            estimated = motion.start_position + direction * progress
            position = round(max(0.0, min(100.0, estimated)))
            self._cover_positions[device.key] = float(position)
            self._mqtt.publish(topics.position, str(position), retain=True)
            final_state = "open" if position > 0 else "closed"
            self._mqtt.publish(topics.state, final_state, retain=True)
            _LOGGER.debug(
                "Cover %s stopped after %.1fs/%.1fs (%s) -> position %d%% (%s)",
                device.key,
                elapsed,
                motion.travel_time_s,
                motion.motion_state,
                position,
                final_state,
            )
        else:
            # Legacy optimistic mode (no travel_time set).
            ratio = elapsed / motion.travel_time_s if motion.travel_time_s > 0 else 1.0
            reached_destination = ratio >= _COVER_STOP_REACHED_RATIO
            if motion.motion_state == "opening":
                final_state = "open" if reached_destination else "closed"
            else:
                final_state = "closed" if reached_destination else "open"
            self._mqtt.publish(topics.state, final_state, retain=True)
            _LOGGER.debug(
                "Cover %s stopped after %.1fs/%.1fs (%s) -> assumed %s",
                device.key,
                elapsed,
                motion.travel_time_s,
                motion.motion_state,
                final_state,
            )

    async def _cover_motion_timer(
        self,
        device: Device,
        motion_state: str,
        travel_time_s: float,
        timer_duration: float,
    ) -> None:
        """Run for ``timer_duration`` seconds then publish the final position.

        ``travel_time_s`` is the full open↔close travel time and is used to
        compute intermediate positions.  ``timer_duration`` equals
        ``travel_time_s`` for full-travel commands and is shorter when a
        specific target position was requested.
        """
        topics = DeviceTopics.for_device("cover", device.key)
        motion = self._cover_tasks.get(device.key)
        try:
            await asyncio.sleep(timer_duration)
        except asyncio.CancelledError:
            self._cover_tasks.pop(device.key, None)
            raise
        finally:
            self._cover_tasks.pop(device.key, None)

        if motion is not None and motion.start_position is not None and travel_time_s > 0:
            # Position-tracking mode.
            if motion.target_position is not None:
                # Partial travel: we reached the requested target exactly.
                position = round(motion.target_position)
            else:
                # Full travel: cover reached the physical end stop.
                position = 100 if motion_state == "opening" else 0
            self._cover_positions[device.key] = float(position)
            self._mqtt.publish(topics.position, str(position), retain=True)
            final_state = "open" if position > 0 else "closed"

            # For partial travel (set_position), send STOP to the box so the
            # motor halts at the estimated position.
            if motion.target_position is not None:
                box = self._boxes_by_slug.get(device.box)
                if box is not None:
                    channel = {"id": device.channel_id, "source": device.channel_source}
                    stop_notes = {"notes": [{"method": 1, "type": 0, "value": 17}]}
                    stop_task = asyncio.create_task(
                        self._client.transfer(box, channel=channel, thingnotes=stop_notes, wait=False)
                    )
                    # Hold a strong reference until the task completes.
                    stop_task.add_done_callback(
                        lambda t: _LOGGER.debug(
                            "Cover %s auto-STOP sent (target %d%%)", device.key, position
                        )
                        if not t.exception()
                        else _LOGGER.warning(
                            "Cover %s auto-STOP failed: %s", device.key, t.exception()
                        )
                    )
        else:
            # Legacy optimistic mode.
            final_state = "open" if motion_state == "opening" else "closed"

        self._mqtt.publish(topics.state, final_state, retain=True)
        _LOGGER.debug(
            "Cover %s timer elapsed (%.1fs/%s) -> %s",
            device.key,
            timer_duration,
            f"{travel_time_s:.1f}s",
            final_state,
        )

    async def _handle_command(self, topic: str, payload: str) -> None:
        if topic == _RELIABILITY_COMMAND_TOPIC:
            _LOGGER.debug("Ignoring stale message on removed reliability_min topic")
        elif topic == _BIND_DURATION_COMMAND_TOPIC:
            self._handle_bind_duration_command(payload)
        elif topic == _CAPTURE_UNKNOWN_COMMAND_TOPIC:
            self._handle_capture_unknown_command(payload)
        else:
            await self._handle_device_command(topic, payload)
