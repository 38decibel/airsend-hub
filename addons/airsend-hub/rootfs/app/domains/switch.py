"""
Domaine `switch` - kind AirSend "on_off".

Symetrique avec la reception : ON/OFF recus sont deja interpretes comme
level 100/0 par thing_notes.py (cf. hassapi.class.php d'origine), on emet
donc directement les memes codes STATE (ON=20, OFF=19) en commande.
"""

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
    """Etat optimiste publie juste apres une commande envoyee avec succes -
    cf. cover.py pour la justification (pas de retour d'etat fiable en push
    RF pour la plupart des recepteurs on/off)."""
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
        # Pas d'etat ON/OFF absolu deductible d'un simple toggle sans
        # connaitre l'etat precedent cote box : on ignore plutot que de
        # deviner un etat potentiellement faux.
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
