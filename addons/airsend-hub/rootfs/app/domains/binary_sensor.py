"""
Domaine `binary_sensor` - squelette minimal.

Conserve pour un futur capteur ouverture/mouvement si un jour rencontre dans
le parc reel de l'utilisateur, mais volontairement pas de logique de decodage
speculative avant un premier cas confirme par les logs (cf. principe acte des
le debut : pas de deduction sans preuve de terrain).
"""

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
    return None  # lecture seule
