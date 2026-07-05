"""
Domaine `cover`.

Deux kinds AirSend mappes ici (cf. table de decision Phase 1) :

  - "volet_roulant" (Profalux, rolling code) : PAS de retour de position fiable.
    On envoie UP/DOWN/STOP, on affiche un etat "assumed" (open/closed/unknown)
    sans `current_position` - comportement HA standard pour les covers sans
    feedback (`assumed_state: true`), plutot que d'inventer une position.

  - "niveau" (ex: IOU/Somfy - "Lames Pergola") : un octet de position 0-255
    (value_binsize=8, confirme par l'export cloud reel). On expose
    current_position (0-100%) et set_position.

  ATTENTION - "Lames Pergola" (pid 26848) s'est avere fonctionner en pratique
  comme un "volet_roulant" classique (OPEN/CLOSE/STOP), pas en "niveau" - le
  mapping protocole -> kind reste donc bien du ressort de l'utilisateur, pas
  une deduction fiable depuis le pid seul (confirme sur le terrain).

`invert` (option par device) : gere ICI, au niveau de la traduction
commande/etat, PAS via un simple label HA (state_open/state_closed) comme
dans une version anterieure - cette approche ne compensait que l'AFFICHAGE,
pas le sens reel de la commande RF envoyee, ce qui ne resolvait pas le cas
d'un volet physiquement monte/cable a l'envers (CLOSE qui ouvre reellement).
Avec l'inversion faite ici, les valeurs "open"/"closed" publiees sur MQTT
signifient toujours l'etat physique reel, quel que soit le cablage.
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

    if device.kind == "niveau":
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

    return payload


def _is_inverted(device) -> bool:
    return bool(device.options.get("invert", False))


def encode_state(device, stype: str, svalue) -> list[tuple[str, str]]:
    """
    Interprete un ThingEvent RECU (typiquement une telecommande physique
    tierce, cf. callback_server.py). IMPORTANT : `invert` n'est PAS applique
    ici, volontairement - `invert` corrige la traduction de NOS PROPRES
    commandes emises (cf. decode_command), pas necessairement la lecture d'un
    evenement emis par un autre emetteur (la telecommande physique d'origine).
    Rien ne prouve que ces deux sens soient affectes symetriquement par le
    meme probleme de cablage/orientation - le confirmer avant d'etendre le
    swap ici, plutot que de deviner et risquer d'inverser un affichage qui
    etait correct.
    """
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
            # Meme raisonnement que dans encode_optimistic_state : publier
            # "unknown" explicitement plutot que de ne rien faire, sinon le
            # dernier open/closed connu reste fige et grise le bouton
            # correspondant cote HA.
            out.append((topics.state, "unknown"))

    return out


def encode_optimistic_state(device, topic: str, payload: str) -> list[tuple[str, str]]:
    """
    Publie un etat optimiste juste apres l'envoi reussi d'une commande, tant
    qu'aucun retour RF reel ne confirme la position (cas normal pour un
    rolling-code sans feedback). C'est une approximation assumee, pas une
    verite terrain - si la commande echoue silencieusement cote materiel
    (hors-portee, obstacle...), cet etat optimiste restera incorrect jusqu'a
    la prochaine action reelle (physique ou HA) qui le corrige.

    IMPORTANT : contrairement a `decode_command`, on ne re-applique PAS le
    swap `invert` ici. `invert` ne sert qu'a choisir le bon code RF a
    envoyer pour obtenir l'effet physique demande - une fois cet effet
    obtenu, l'etat affiche doit rester ce que l'utilisateur a demande
    (CLOSE -> "closed"), pas son inverse.

    STOP : publie explicitement "unknown" (pas juste une absence de
    publication). Sans ca, l'etat MQTT retenu restait bloque sur le dernier
    "open"/"closed" optimiste envoye par la commande PRECEDENTE (ex. OPEN),
    alors qu'un arret en cours de route ne garantit ni l'un ni l'autre. Le
    frontend HA desactive le bouton correspondant des que l'etat vaut
    exactement "open" ou "closed" - meme avec assumed_state=true (comportement
    documente, cf. github.com/home-assistant/core/issues/147976) - donc
    laisser trainer l'ancien etat bloquait le bouton "ouvrir" apres un
    STOP survenu pendant une montee. "unknown" reactive les deux boutons.
    """
    topics = DeviceTopics.for_device(COMPONENT, device.key)

    if topic == topics.command:
        cmd = payload.upper()
        if cmd == "OPEN":
            return [(topics.state, "open")]
        if cmd == "CLOSE":
            return [(topics.state, "closed")]
        if cmd == "STOP":
            return [(topics.state, "unknown")]
        return []

    if topic == topics.set_position and device.kind == "niveau":
        try:
            position = max(0, min(100, int(payload)))
        except ValueError:
            return []
        return [(topics.position, str(position)), (topics.state, "open" if position > 0 else "closed")]

    return []


def decode_command(device, topic: str, payload: str) -> dict | None:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    inverted = _is_inverted(device)

    if topic == topics.set_position and device.kind == "niveau":
        try:
            position = max(0, min(100, int(payload)))
        except ValueError:
            return None
        raw_position = 100 - position if inverted else position
        raw_byte = round(raw_position / 100 * 255)
        return {"notes": [{"method": 1, "type": 1, "value": raw_byte}]}

    if topic == topics.command:
        cmd = payload.upper()
        if inverted:
            cmd = {"OPEN": "CLOSE", "CLOSE": "OPEN", "STOP": "STOP"}.get(cmd, cmd)
        value = {"OPEN": _STATE_UP, "CLOSE": _STATE_DOWN, "STOP": _STATE_STOP}.get(cmd)
        if value is None:
            return None
        return {"notes": [{"method": 1, "type": 0, "value": value}]}

    return None
