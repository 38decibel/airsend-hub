""" `binary_sensor` domain – minimal skeleton """

from __future__ import annotations

from domains.topics import DeviceTopics, base_discovery_payload

COMPONENT = "binary_sensor"


def discovery_config(device, topics: DeviceTopics, device_info: dict) -> dict:
    payload = base_discovery_payload(device, COMPONENT, topics, device_info)
    device_class = device.options.get("device_class")
    if device_class:
        payload["device_class"] = device_class
    payload["payload_on"] = "ON"
    payload["payload_off"] = "OFF"
    return payload


def encode_state(device, stype: str, svalue) -> list[tuple[str, str]]:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    if stype == "level":
        return [(topics.state, "ON" if svalue and svalue > 0 else "OFF")]
    return []


def decode_command(device, topic: str, payload: str) -> dict | None:
    return None
