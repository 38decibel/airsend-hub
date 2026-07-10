"""
Point d'entree de l'addon.

Chaine complete : ecoute RF (bind_manager) -> callback (callback_server,
filtre reliability) -> decodage (thing_notes) -> etat/discovery/commandes
(mqtt_bridge) -> Home Assistant via MQTT discovery. Le mode inclusion est
pilotable depuis HA via l'entite switch "AirSend - Mode inclusion" (plus de
force-start de dev), la confirmation des candidats detectes (nom/kind/options
-> ecriture dans devices.json) reste en revanche a construire : pour l'instant
les candidats sont uniquement publies en lecture sur `airsend/inclusion/candidates`
(JSON), consultables mais pas encore actionnables depuis HA. Prochaine etape
naturelle plutot que de bricoler ca en MQTT pur : exposer un service HA cote
addon (Supervisor API / webhook) pour ce formulaire de confirmation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from airsend_client import AirSendClient, BoxConfig
from bind_manager import BindManager
from callback_server import CallbackServer
from device_registry import DeviceRegistry
from inclusion import InclusionState
from mqtt_bridge import MqttBridge
from net_utils import mac_from_link_local
from protocol_catalog import ProtocolCatalog
from runtime_settings import RuntimeSettings

_LOGGER = logging.getLogger("airsend.main")

CALLBACK_PORT = 8126
# AirSendWebService tourne dans le MEME conteneur que cette app Python (cf.
# Dockerfile/run.sh), donc 127.0.0.1 est toujours la bonne cible pour le
# callback - pas besoin (et pas souhaitable) de deviner une IP via une
# connexion sortante vers un serveur externe (8.8.8.8).
CALLBACK_HOST = "127.0.0.1"

# Valeur par defaut du champ "name" dans config.yaml : si l'utilisateur ne l'a
# pas modifie, on derive un nom lisible depuis la MAC de la box plutot que de
# publier une entite MQTT nommee litteralement "AIRSEND_".
_DEFAULT_NAME_PREFIX = "AIRSEND_"


def _derive_name(entry_name: str, localip: str) -> str:
    name = (entry_name or "").strip()
    if name and name != _DEFAULT_NAME_PREFIX:
        return name
    mac = mac_from_link_local(localip)
    if mac:
        suffix = mac.replace(":", "")[-6:].upper()
        return f"{_DEFAULT_NAME_PREFIX}{suffix}"
    return name or "AirSend"


def _load_boxes() -> list[BoxConfig]:
    raw = os.environ.get("BOXES_JSON", "[]")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _LOGGER.exception("BOXES_JSON is not valid JSON, no box will be configured: %r", raw)
        return []

    # bashio::config sur une liste d'objets peut renvoyer un objet nu plutot
    # qu'un tableau a un element (observe en pratique avec une seule box
    # configuree) - on normalise dans tous les cas vers une liste.
    if isinstance(parsed, dict):
        entries: list = [parsed]
    elif isinstance(parsed, list):
        entries = parsed
    else:
        _LOGGER.error("BOXES_JSON has an unexpected shape (%s): %r", type(parsed).__name__, parsed)
        entries = []

    boxes: list[BoxConfig] = []
    for entry in entries:
        if isinstance(entry, str):
            try:
                entry = json.loads(entry)
            except json.JSONDecodeError:
                _LOGGER.exception("Skipping unparsable box entry string: %r", entry)
                continue
        if not isinstance(entry, dict):
            _LOGGER.error("Skipping malformed box entry (not an object): %r", entry)
            continue

        try:
            boxes.append(
                BoxConfig(
                    name=_derive_name(entry.get("name", ""), entry["localip"]),
                    localip=entry["localip"],
                    ipv4=entry["ipv4"],
                    password=entry["password"],
                    gw=bool(entry.get("gw", False)),
                )
            )
        except KeyError as exc:
            _LOGGER.exception("Skipping malformed box entry %r (missing %s)", entry, exc)
    return boxes


async def async_main() -> None:
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    boxes = _load_boxes()
    if not boxes:
        _LOGGER.error("No AirSend box configured, nothing to do. Check addon configuration.")
        # On ne quitte pas immediatement : ca permettrait a l'utilisateur de
        # voir l'erreur dans les logs plutot qu'un crash-loop silencieux.
        while True:
            await asyncio.sleep(3600)

    client = AirSendClient()
    client.start()

    catalog = ProtocolCatalog(client)
    registry = DeviceRegistry()
    inclusion = InclusionState()

    for box in boxes:
        await catalog.refresh(box)
        is_duo = catalog.is_duo_best_effort(box.slug)
        if is_duo is True:
            duo_label = "AirSend Duo (433+868MHz)"
        elif is_duo is False:
            duo_label = "AirSend (433MHz)"
        else:
            duo_label = "unknown"
        _LOGGER.info(
            "Box '%s' detection (best effort): %s",
            box.name,
            duo_label,
        )

    boxes_by_slug = {box.slug: box for box in boxes}
    settings = RuntimeSettings()

    mqtt_bridge = MqttBridge(
        registry=registry,
        client=client,
        boxes_by_slug=boxes_by_slug,
        inclusion=inclusion,
        catalog=catalog,
        settings=settings,
        host=os.environ.get("MQTT_HOST", "core-mosquitto"),
        port=int(os.environ.get("MQTT_PORT") or 1883),
        username=os.environ.get("MQTT_USER") or None,
        password=os.environ.get("MQTT_PASS") or None,
        use_ssl=os.environ.get("MQTT_SSL", "false").lower() == "true",
    )
    await mqtt_bridge.start()
    for box in boxes:
        mqtt_bridge.publish_box_diagnostics(box)

    callback_server = CallbackServer(
        registry=registry,
        inclusion=inclusion,
        catalog=catalog,
        settings=settings,
        on_state=mqtt_bridge.publish_state,
        port=CALLBACK_PORT,
    )
    await callback_server.start()

    # Plain HTTP is intentional: both ends run inside the same container, on
    # loopback only. AirSendWebService does not support HTTPS callbacks.
    _callback_scheme = "http"
    callback_base_url = f"{_callback_scheme}://{CALLBACK_HOST}:{CALLBACK_PORT}"
    _LOGGER.info("Callback base URL: %s", callback_base_url)

    bind_manager = BindManager(client, callback_base_url, settings)
    for box in boxes:
        bind_manager.add_box(box)

    _LOGGER.info(
        "Ready. Toggle 'AirSend - Mode inclusion' in HA to start detecting new devices."
    )

    try:
        await asyncio.Event().wait()  # tourne indefiniment
    finally:
        await bind_manager.stop_all()
        await callback_server.stop()
        mqtt_bridge.stop()
        await client.close()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()