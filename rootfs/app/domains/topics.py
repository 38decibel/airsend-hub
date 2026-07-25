"""
MQTT topic convention, common to all domains/*.py and mqtt_bridge.py. 

    homeassistant/<component>/airsend_<device.key>/config (discovery, retained) 
    airsend/<device.key>/state (current state, retained) 
    airsend/<device.key>/set (simple command: OPEN/CLOSE/STOP/ON/OFF/PRESS) 
    airsend/<device.key>/set_position (cover "level" only: 0-100) 
    airsend/<device.key>/position (cover "level" only: current position 0-100) 
    airsend/bridge/status (availability, "online"/"offline", LWT)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceTopics:
    state: str
    command: str
    set_position: str
    position: str
    discovery: str

    @staticmethod
    def for_device(component: str, device_key: str) -> "DeviceTopics":
        base = f"airsend/{device_key}"
        return DeviceTopics(
            state=f"{base}/state",
            command=f"{base}/set",
            set_position=f"{base}/set_position",
            position=f"{base}/position",
            discovery=f"homeassistant/{component}/{device_key}_airsend/config",
        )


AVAILABILITY_TOPIC = "airsend/bridge/status"
AVAILABILITY_ONLINE = "online"
AVAILABILITY_OFFLINE = "offline"


def build_device_info(
    identifier: str,
    name: str,
    model: str | None = None,
    mac: str | None = None,
    via_device: str | None = None,
) -> dict:
    info: dict = {"identifiers": [identifier], "name": name, "manufacturer": "Devmel"}
    if model:
        info["model"] = model
    if mac:
        info["connections"] = [["mac", mac]]
    if via_device:
        info["via_device"] = via_device
    return info


def base_discovery_payload(device, component: str, topics: DeviceTopics, device_info: dict) -> dict:
    return {
        "name": None,
        "default_entity_id": f"{component}.{device.key}",
        "has_entity_name": True,
        "unique_id": f"{device.key}_airsend",
        "state_topic": topics.state,
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_available": AVAILABILITY_ONLINE,
        "payload_not_available": AVAILABILITY_OFFLINE,
        "device": device_info,
    }
