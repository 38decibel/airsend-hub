""" Domain `switch` - kind AirSend "on_off" """

from __future__ import annotations

from domains.topics import DeviceTopics, base_discovery_payload

COMPONENT = "switch"

_STATE_ON = 20
_STATE_OFF = 19


def discovery_config(device, topics: DeviceTopics, device_info: dict) -> dict:
    payload = base_discovery_payload(device, COMPONENT, topics, device_info)
    payload.update(
        {
            "command_topic": topics.command,
            "payload_on": "ON",
            "payload_off": "OFF",
            "state_on": "ON",
            "state_off": "OFF",
        }
    )
    return payload


def encode_optimistic_state(device, topic: str, payload: str) -> list[tuple[str, str]]:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    if topic != topics.command:
        return []
    value = payload.upper()
    if value in ("ON", "OFF"):
        return [(topics.state, value)]
    return []


def encode_state(device, stype: str, svalue) -> list[tuple[str, str]]:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    if stype == "level":
        return [(topics.state, "ON" if svalue and svalue > 0 else "OFF")]
    if stype == "toggle":
        return []
    return []


def decode_command(device, topic: str, payload: str) -> dict | None:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    if topic != topics.command:
        return None
    value = {"ON": _STATE_ON, "OFF": _STATE_OFF}.get(payload.upper())
    if value is None:
        return None
    return {"notes": [{"method": 1, "type": 0, "value": value}]}
