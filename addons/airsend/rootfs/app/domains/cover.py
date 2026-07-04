"""
Domaine `cover`.

Deux kinds AirSend mappes ici (cf. table de decision Phase 1) :

  - "volet_roulant" (Profalux, rolling code) : PAS de retour de position fiable.
    On envoie UP/DOWN/STOP, on affiche un etat "assumed" (open/closed/unknown)
    sans `current_position` — comportement HA standard pour les covers sans
    feedback (`assumed_state: true`), plutot que d'inventer une position.

  - "niveau" (ex: IOU/Somfy - "Lames Pergola") : un octet de position 0-255
    (value_binsize=8, confirme par l'export cloud reel). On expose
    current_position (0-100%) et set_position.

ATTENTION - hypothese non confirmee empiriquement (a valider sur le terrain
avant mise en prod reelle) : le mapping OPEN->UP(35)/CLOSE->DOWN(34) pour le
kind "volet_roulant" est deduit par symetrie avec la reception (ou UP/DOWN
recus sont interpretes comme level 100/0 dans thing_notes.py), MAIS jamais
verifie en emission reelle vers une box. A confirmer par un premier test
manuel (envoyer la commande, observer si le volet monte/descend dans le bon
sens) avant de considerer ce mapping comme acquis.
"""

from __future__ import annotations

from domains.topics import DeviceTopics, base_discovery_payload

COMPONENT = "cover"

_STATE_UP = 35
_STATE_DOWN = 34
_STATE_STOP = 17


def discovery_config(device, topics: DeviceTopics, device_info: dict) -> dict:
    payload = base_discovery_payload(device, COMPONENT, topics, device_info)
    payload.update(
        {
            "command_topic": topics.command,
            "payload_open": "OPEN",
            "payload_close": "CLOSE",
            "payload_stop": "STOP",
        }
    )

    kind = device.kind
    if kind == "niveau":
        payload.update(
            {
                "position_topic": topics.position,
                "set_position_topic": topics.set_position,
                "position_open": 100,
                "position_closed": 0,
            }
        )
    else:
        # volet_roulant : pas de position fiable, HA doit se contenter de
        # l'etat open/closed/unknown sans feedback continu.
        payload["assumed_state"] = True

    invert = device.options.get("invert", False)
    if invert:
        payload["state_open"] = "closed"
        payload["state_closed"] = "open"

    return payload


def encode_state(device, stype: str, svalue) -> list[tuple[str, str]]:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    out: list[tuple[str, str]] = []

    if device.kind == "niveau" and stype == "data":
        try:
            raw_byte = int(svalue)
        except (TypeError, ValueError):
            return out
        position = round(max(0, min(255, raw_byte)) / 255 * 100)
        out.append((topics.position, str(position)))
        out.append((topics.state, "open" if position > 0 else "closed"))
        return out

    if device.kind == "volet_roulant":
        if stype == "level":
            # DOWN/UP recus -> level 0/100 (cf. thing_notes.py)
            out.append((topics.state, "closed" if svalue == 0 else "open"))
        elif stype == "state" and svalue == "stop":
            # Pas de position connue apres un STOP intermediaire : on ne
            # republie pas un etat qu'on ne connait pas.
            pass

    return out


def decode_command(device, topic: str, payload: str) -> dict | None:
    topics = DeviceTopics.for_device(COMPONENT, device.key)

    if topic == topics.set_position and device.kind == "niveau":
        try:
            position = max(0, min(100, int(payload)))
        except ValueError:
            return None
        raw_byte = round(position / 100 * 255)
        return {"notes": [{"method": 1, "type": 1, "value": raw_byte}]}

    if topic == topics.command:
        value = {"OPEN": _STATE_UP, "CLOSE": _STATE_DOWN, "STOP": _STATE_STOP}.get(payload.upper())
        if value is None:
            return None
        return {"notes": [{"method": 1, "type": 0, "value": value}]}

    return None
