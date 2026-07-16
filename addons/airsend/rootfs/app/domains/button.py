"""
Domaine `button` - kind AirSend "1_bouton".

Le composant MQTT `button` de HA est command-only (pas de state_topic dans le
schema standard) : on presse, ca envoie une commande, un point c'est tout.

Hypothese non confirmee : quel code STATE envoyer pour "presser" un appareil
de type 1-bouton ? On utilise TOGGLE (18) par defaut - coherent avec le sens
recu (thing_notes.py mappe TOGGLE recu vers "pressed") - mais aucune preuve
qu'un vrai appareil 1-bouton attende ce code precis en emission plutot qu'un
PROG/PING. A confirmer sur le terrain avant usage reel non-supervise.
"""

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
    # Command-only : aucun etat a republier meme si une trame arrive (par ex.
    # une confirmation RF suite a notre propre commande).
    return []


def decode_command(device, topic: str, payload: str) -> dict | None:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    if topic != topics.command or payload.upper() != "PRESS":
        return None
    return {"notes": [{"method": 1, "type": 0, "value": _STATE_TOGGLE}]}
