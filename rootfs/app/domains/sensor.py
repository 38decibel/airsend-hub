"""
`sensor` domain – native sensors of the AirSend hub (read-only, no control).
Expected `device.kind`: "temperature" | "illuminance" | "r_humidity"; determined
automatically based on the first type of message received, rather than being
manually selected during inclusion
(see `mqtt_bridge`: auto-detection specific to native sensors).
"""

from __future__ import annotations

from domains.topics import DeviceTopics, base_discovery_payload

COMPONENT = "sensor"

_DEVICE_CLASS_BY_STYPE = {
    "temperature": ("temperature", "°C"),
    "illuminance": ("illuminance", "lx"),
    "r_humidity": ("humidity", "%"),
}


def discovery_config(device, topics: DeviceTopics, device_info: dict) -> dict:
    payload = base_discovery_payload(device, COMPONENT, topics, device_info)
    device_class, unit = _DEVICE_CLASS_BY_STYPE.get(device.kind, (None, None))
    if device_class:
        payload["device_class"] = device_class
    if unit:
        payload["unit_of_measurement"] = unit
    return payload


def encode_state(device, stype: str, svalue) -> list[tuple[str, str]]:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    if stype != device.kind:
        return []
    return [(topics.state, str(svalue))]


def decode_command(device, topic: str, payload: str) -> dict | None:
    return None
