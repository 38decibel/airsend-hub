"""
Domaine `sensor` - capteurs natifs de la box AirSend (pas de commande, lecture
seule). device.kind attendu : "temperature" | "illuminance" | "r_humidity",
determine automatiquement selon le premier type de note recu plutot que
choisi manuellement a l'inclusion (cf. mqtt_bridge : auto-detection specifique
aux sensors natifs).
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
    return None  # lecture seule
