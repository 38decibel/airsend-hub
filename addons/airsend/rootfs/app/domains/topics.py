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
            discovery=f"homeassistant/{component}/airsend_{device_key}/config",
        )


AVAILABILITY_TOPIC = "airsend/bridge/status"
AVAILABILITY_ONLINE = "online"
AVAILABILITY_OFFLINE = "offline"


def build_device_info(identifier: str, name: str, model: str | None = None, mac: str | None = None) -> dict:
    """
    Bloc `device` MQTT discovery commun : regroupe toutes les entites d'une
    meme box AirSend sous un seul appareil cote HA.

    name   : nom affiche = nom configure par l'utilisateur pour cette box
             (PAS un libelle generique "AirSend Addon").
    model  : type de box detecte ("AirSend" / "AirSend Duo"), affiche par HA
             sous forme "<model>, by <manufacturer>". None si pas encore
             detecte (catalogue de protocoles pas encore recupere).
    mac    : adresse MAC derivee de l'IPv6 link-local, exposee via
             "connections" (champ natif HA pour ce genre d'identifiant),
             plutot qu'une entite separee.
    """
    info: dict = {"identifiers": [identifier], "name": name, "manufacturer": "Devmel"}
    if model:
        info["model"] = model
    if mac:
        info["connections"] = [["mac", mac]]
    return info


def base_discovery_payload(device, component: str, topics: DeviceTopics, device_info: dict) -> dict:
    """Champs communs a toute config de discovery, a completer par chaque
    domains/*.py avec ses champs specifiques (device_class, position_topic...).
    `device_info` est calcule par mqtt_bridge (build_device_info) car lui seul
    connait le nom reel et le modele detecte de la box associee.

    has_entity_name=True + object_id : evite que HA prefixe le nom de
    l'entite par le nom de l'appareil (ex. "AIRSEND_BB5D74 Volet cuisine
    porte" -> juste "Volet cuisine porte"), et donne un entity_id propre et
    stable (ex. cover.lames_pergola) independant du nom affiche, qui lui peut
    changer sans casser les automatisations existantes.

    Forme "{device.key}_airsend" (device.key en premier) sur unique_id, au
    lieu de l'ancien "airsend_{device.key}" : le registre HA lie unique_id ->
    entity_id/nom de facon permanente des la premiere creation, et ne les met
    JAMAIS a jour retroactivement meme si la config de discovery change
    (comportement voulu par HA, pour ne pas casser les automatisations
    existantes). Les entites creees avant l'introduction de object_id/
    has_entity_name restaient donc bloquees sur leur ancien nom/entity_id
    malgre tout changement de code. Inverser l'ordre des termes force HA a
    traiter ces entites comme reellement nouvelles. Les anciennes entrees
    (forme "airsend_{key}") deviennent orphelines - a supprimer une fois
    manuellement, plus jamais recreees puisqu'aucun message de discovery ne
    referencera plus leur ancien unique_id."""
    return {
        "name": device.friendly_name,
        "object_id": device.key,
        "has_entity_name": True,
        "unique_id": f"{device.key}_airsend",
        "state_topic": topics.state,
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_available": AVAILABILITY_ONLINE,
        "payload_not_available": AVAILABILITY_OFFLINE,
        "device": device_info,
    }
