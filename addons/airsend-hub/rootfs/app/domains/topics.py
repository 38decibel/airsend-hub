"""
Convention de topics MQTT, commune a tous les domains/*.py et a mqtt_bridge.py.

    homeassistant/<component>/airsend_<device.key>/config   (discovery, retained)
    airsend/<device.key>/state                               (etat courant, retained)
    airsend/<device.key>/set                                 (commande simple: OPEN/CLOSE/STOP/ON/OFF/PRESS)
    airsend/<device.key>/set_position                        (cover "niveau" uniquement: 0-100)
    airsend/<device.key>/position                            (cover "niveau" uniquement: position courante 0-100)
    airsend/bridge/status                                    (availability, "online"/"offline", LWT)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceTopics:
    state: str
    command: str
    set_position: str
    position: str
    discovery: str

    @staticmethod
    def for_device(component: str, device_key: str) -> "DeviceTopics":
        base = f"airsend/{device_key}"
        return DeviceTopics(
            state=f"{base}/state",
            command=f"{base}/set",
            set_position=f"{base}/set_position",
            position=f"{base}/position",
            discovery=f"homeassistant/{component}/{device_key}_airsend/config",
        )


AVAILABILITY_TOPIC = "airsend/bridge/status"
AVAILABILITY_ONLINE = "online"
AVAILABILITY_OFFLINE = "offline"


def build_device_info(
    identifier: str,
    name: str,
    model: str | None = None,
    mac: str | None = None,
    via_device: str | None = None,
) -> dict:
    """
    Bloc `device` MQTT discovery.

    Depuis la restructuration "1 device HA par element RF" : chaque
    volet/switch/bouton a son propre device (identifier=device.key), reliee
    au device "box" (le hub AirSend) via `via_device` - le meme pattern que
    Zigbee2MQTT/Z-Wave JS UI pour une passerelle + ses appareils enfants.
    Le device "box" lui-meme (identifier=box_slug) reste utilise tel quel
    pour les entites systeme/diagnostic (cf. mqtt_bridge._device_info_for_box)
    et n'a pas de via_device (c'est la racine).

    name       : nom affiche du device (nom de la box, ou friendly_name de
                 l'element RF selon l'appelant).
    model      : type de box detecte ("AirSend" / "AirSend Duo"), affiche par
                 HA sous forme "<model>, by <manufacturer>". None si pas
                 encore detecte, ou non pertinent (device element RF).
    mac        : adresse MAC derivee de l'IPv6 link-local, exposee via
                 "connections" (champ natif HA), uniquement pour le device box.
    via_device : identifier du device parent (la box), pour les devices
                 element RF - absent pour le device box lui-meme.
    """
    info: dict = {"identifiers": [identifier], "name": name, "manufacturer": "Devmel"}
    if model:
        info["model"] = model
    if mac:
        info["connections"] = [["mac", mac]]
    if via_device:
        info["via_device"] = via_device
    return info


def base_discovery_payload(device, component: str, topics: DeviceTopics, device_info: dict) -> dict:
    """Champs communs a toute config de discovery, a completer par chaque
    domains/*.py avec ses champs specifiques (device_class, position_topic...).
    `device_info` est calcule par mqtt_bridge (build_device_info) - depuis la
    restructuration par-element, c'est desormais un device dedie a `device`
    (identifier=device.key), pas le device box partage.

    has_entity_name=True + name=None : l'element RF n'a qu'une seule entite,
    qui EST la fonctionnalite principale de son device (cf. build_device_info)
    - HA prend alors directement le nom du device comme nom affiche de
    l'entite, sans concatener de nom d'entite (ex. juste "Volet Celyan", pas
    "Volet Celyan Volet Celyan" ni le prefixe de l'ancien device box partage
    "AIRSEND_BB5D74 Volet Celyan"). Valide empiriquement suite au signalement
    de l'ancien comportement (le "name": device.friendly_name precedent, en
    plus de partager le device box, produisait justement ce prefixe indesire).

    default_entity_id donne un entity_id propre et stable (ex.
    cover.lames_pergola) independant du nom affiche, qui lui peut changer sans
    casser les automatisations existantes.

    IMPORTANT : `object_id` (utilise dans une version anterieure) est
    DEPRECIE cote HA depuis 2025.10 et son support a ete retire en HA Core
    2026.4 - il etait donc silencieusement ignore, ce qui expliquait que rien
    ne changait malgre plusieurs tentatives de correction. Le remplacant
    officiel est `default_entity_id`, qui prend la forme complete
    "<component>.<slug>" (ex. "cover.lames_pergola"), pas juste le slug seul.

    Forme "{device.key}_airsend" sur unique_id : inchangee par cette
    restructuration - unique_id ne bouge pas, seul le device auquel l'entite
    est rattachee change (cf. build_device_info), donc HA reassocie l'entite
    existante a son nouveau device sans recreer d'entite fantome ni casser
    les automatisations."""
    return {
        "name": None,
        "default_entity_id": f"{component}.{device.key}",
        "has_entity_name": True,
        "unique_id": f"{device.key}_airsend",
        "state_topic": topics.state,
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_available": AVAILABILITY_ONLINE,
        "payload_not_available": AVAILABILITY_OFFLINE,
        "device": device_info,
    }
