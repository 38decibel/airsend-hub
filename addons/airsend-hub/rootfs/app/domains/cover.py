"""
Domaine `cover`.

Deux kinds AirSend mappes ici (cf. table de decision Phase 1) :

  - "volet_roulant" (Profalux, rolling code) : PAS de retour de position fiable.
    On envoie UP/DOWN/STOP, on affiche un etat "assumed" (open/closed)
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

IMPORTANT - le state_topic MQTT du composant `cover` de HA n'accepte QUE
"open"/"closed"/"opening"/"closing"/"stopped" comme payload (cf.
homeassistant/components/mqtt/cover.py) : "unknown" y est rejete (log
"Payload is not supported"). Pour un volet_roulant sans confirmation RF
fiable de la position finale, la bonne reponse cote HA est donc de NE RIEN
PUBLIER sur `state` plutot que de publier une valeur inventee ou invalide -
le dernier etat connu reste affiche, et `optimistic: true` (cf.
discovery_config) garde deja les boutons Ouvrir/Fermer/Stop actifs
independamment de cet etat affiche (PAS `assumed_state`, qui n'existe pas
dans le schema MQTT Cover et est silencieusement ignore par HA - verifie sur
la doc officielle, cf. commentaire dans discovery_config). Ne pas
reintroduire de publication "unknown" ici sans avoir d'abord verifie la
liste des payloads acceptes par le composant HA cible.
"""

from __future__ import annotations

from domains.topics import DeviceTopics, base_discovery_payload

COMPONENT = "cover"

_STATE_UP = 35
_STATE_DOWN = 34
_STATE_STOP = 17

# Duree de course (secondes) par defaut pour un "volet_roulant" sans retour
# de position RF, utilisee par mqtt_bridge.py pour simuler la fin de course
# (cf. travel_time_s ci-dessous et _cover_motion_timer). Editable par device
# via l'option "travel_time" (UI Ingress).
DEFAULT_TRAVEL_TIME_S = 20.0
_MIN_TRAVEL_TIME_S = 1.0
_MAX_TRAVEL_TIME_S = 180.0


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
        # volet_roulant : pas de position fiable, HA doit se contenter du
        # dernier etat open/closed connu, sans feedback continu. IMPORTANT :
        # "assumed_state" n'existe PAS dans le schema MQTT Cover (verifie sur
        # la doc officielle a jour - liste complete des champs de config) et
        # est donc silencieusement ignore par HA, sans erreur ni log. Le vrai
        # levier est "optimistic" : sans lui (valeur par defaut False des que
        # state_topic est defini, cf. doc), HA desactive le bouton correspondant
        # a l'etat courant (ex. "fermer" grise si is_closed=true), quelle que
        # soit la carte utilisee (tuile ou entites) - confirme empiriquement
        # sur le terrain (cf. discussion PR travel_time). "optimistic: true"
        # reste compatible avec un state_topic deja defini (documente
        # explicitement : "Optimistic mode can be forced, even if a
        # state_topic / position_topic is defined").
        payload["optimistic"] = True

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
            # STOP recu depuis une telecommande physique tierce : la
            # position reelle a ce moment est inconnue et "unknown" n'est
            # pas un payload valide pour le state_topic MQTT cover (cf. note
            # de module). On ne publie donc rien : le dernier etat open/closed
            # connu reste affiche tel quel plutot que d'etre remplace par une
            # valeur invalide ou une supposition non fondee.
            pass

    return out


def encode_optimistic_state(device, topic: str, payload: str) -> list[tuple[str, str]]:
    """
    Publie un état optimiste après une commande réussie.

    Pour les volets roulants sans retour de position :
    - OPEN  => état supposé opening (cf. mqtt_bridge._cover_motion_timer pour
      la transition vers "open" au bout de travel_time)
    - CLOSE => état supposé closing (idem, vers "closed")
    - STOP  => rien n'est publié ici. IMPORTANT : ne PAS publier "stopped" -
      le composant MQTT Cover de HA resout ce payload en interne en "closed"
      si l'etat precedent etait "closing", "open" sinon, et ce QUELLE QUE
      SOIT la duree de course deja ecoulee (verifie empiriquement : un STOP
      apres 1s de fermeture affichait quand meme "closed"). C'est donc
      mqtt_bridge._handle_cover_stop qui calcule et publie l'etat final,
      a partir du temps ecoule vs travel_time (cf. discussion PR travel_time).

    La position réelle reste inconnue.
    """

    topics = DeviceTopics.for_device(COMPONENT, device.key)

    if topic == topics.command and device.kind == "volet_roulant":
        cmd = payload.upper()

        if cmd == "OPEN":
            return [(topics.state, "opening")]

        if cmd == "CLOSE":
            return [(topics.state, "closing")]

    if topic == topics.set_position and device.kind == "niveau":
        try:
            position = max(0, min(100, int(payload)))
        except ValueError:
            return []

        return [
            (topics.position, str(position)),
            (topics.state, "open" if position > 0 else "closed"),
        ]

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


def travel_time_s(device) -> float:
    """
    Duree de course (secondes) a utiliser pour simuler la fin de course
    d'un "volet_roulant" (cf. motion_command / mqtt_bridge._cover_motion_timer).
    Valeur par device, option "travel_time" editable via l'UI Ingress ;
    retombe sur DEFAULT_TRAVEL_TIME_S si absente ou invalide, et est bornee
    pour eviter un minuteur degenere (0s, ou une duree demesuree en cas de
    saisie erronee).
    """
    try:
        value = float(device.options.get("travel_time", DEFAULT_TRAVEL_TIME_S))
    except (TypeError, ValueError):
        return DEFAULT_TRAVEL_TIME_S
    return max(_MIN_TRAVEL_TIME_S, min(_MAX_TRAVEL_TIME_S, value))


def motion_command(device, topic: str, payload: str) -> str | None:
    """
    Traduit une commande MQTT entrante en mouvement pour le minuteur de fin
    de course simulee : "opening"/"closing" pour lancer un minuteur (cf.
    mqtt_bridge._start_cover_motion), "stop" pour l'annuler et calculer
    l'etat final a partir du temps de course ecoule (cf.
    mqtt_bridge._handle_cover_stop), None si non concerne.

    Uniquement pertinent pour "volet_roulant" : "niveau" a une position reelle
    deja publiee de facon synchrone (cf. encode_optimistic_state), pas de fin
    de course a simuler.
    """
    if device.kind != "volet_roulant":
        return None

    topics = DeviceTopics.for_device(COMPONENT, device.key)
    if topic != topics.command:
        return None

    cmd = payload.upper()
    if cmd == "OPEN":
        return "opening"
    if cmd == "CLOSE":
        return "closing"
    if cmd == "STOP":
        return "stop"
    return None
