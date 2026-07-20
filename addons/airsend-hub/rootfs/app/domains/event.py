"""
Domaine `event` - fallback sur pour les telecommandes rolling-code sans retour
de position fiable (ex: appui detecte sur une telecommande physique tierce
Profalux liee a un volet deja gere en `cover`) ou tout appareil dont
l'utilisateur a explicitement choisi de ne pas piloter d'etat devine.

Composant MQTT `event` de HA (schema JSON, state_topic + event_types) :
chaque trame recue publie un evenement horodate, jamais un etat retenu.
"""

from __future__ import annotations

import json
import time

from domains.topics import DeviceTopics, base_discovery_payload

COMPONENT = "event"

_EVENT_TYPES = ["triggered"]


def discovery_config(device, topics: DeviceTopics, device_info: dict) -> dict:
    payload = base_discovery_payload(device, COMPONENT, topics, device_info)
    payload["event_types"] = device.options.get("event_types", _EVENT_TYPES)
    return payload


def encode_state(device, stype: str, svalue) -> list[tuple[str, str]]:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    body = json.dumps(
        {
            "event_type": "triggered",
            "detail": {"type": stype, "value": svalue},
            "timestamp": time.time(),
        }
    )
    return [(topics.state, body)]


def decode_command(device, topic: str, payload: str) -> dict | None:
    return None  # lecture seule
