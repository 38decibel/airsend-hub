""" Domain `button` - kind AirSend "1_button" """

from __future__ import annotations

from domains.topics import AVAILABILITY_OFFLINE, AVAILABILITY_ONLINE, AVAILABILITY_TOPIC, DeviceTopics

COMPONENT = "button"

_STATE_TOGGLE = 18


def discovery_config(device, topics: DeviceTopics, device_info: dict) -> dict:
    return {
        "name": None,
        "default_entity_id": f"button.{device.key}",
        "has_entity_name": True,
        "unique_id": f"{device.key}_airsend",
        "command_topic": topics.command,
        "payload_press": "PRESS",
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_available": AVAILABILITY_ONLINE,
        "payload_not_available": AVAILABILITY_OFFLINE,
        "device": device_info,
    }


def encode_state(device, stype: str, svalue) -> list[tuple[str, str]]:
    return []


def decode_command(device, topic: str, payload: str) -> dict | None:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    if topic != topics.command or payload.upper() != "PRESS":
        return None
    return {"notes": [{"method": 1, "type": 0, "value": _STATE_TOGGLE}]}
