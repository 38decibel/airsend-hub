"""
App entry point.

Main flow: RF listening (bind_manager) -> callback (callback_server, reliability filter) 
-> decoding (thing_notes) -> state/discovery/commands (mqtt_bridge) -> Home Assistant via MQTT discovery.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from aiohttp import web
from api.inclusion_api import create_ingress_app
from catalog.protocol_catalog import ProtocolCatalog
from core.airsend_client import AirSendClient, BoxConfig
from core.bind_manager import BindManager
from core.callback_server import CallbackServer
from core.net_utils import mac_from_link_local
from inclusion import InclusionState
from mqtt_bridge import MqttBridge
from registry.device_registry import DeviceRegistry
from runtime_settings import RuntimeSettings

_LOGGER = logging.getLogger("airsend.main")

CALLBACK_PORT = 8126
CALLBACK_HOST = "127.0.0.1"

INGRESS_PORT = 8127
INGRESS_HOST = "0.0.0.0"

_DEFAULT_NAME_PREFIX = "AIRSEND_"

# MQTT env vars are exported by run.sh (resolved from addon options / Supervisor / defaults)
_MQTT_HOST_DEFAULT = "core-mosquitto"
_MQTT_PORT_DEFAULT = 1883


def _load_mqtt_config() -> dict:
    """Read MQTT connection parameters from env vars set by run.sh."""
    host = os.environ.get("MQTT_HOST") or _MQTT_HOST_DEFAULT
    port = int(os.environ.get("MQTT_PORT") or _MQTT_PORT_DEFAULT)
    username = os.environ.get("MQTT_USER") or None
    password = os.environ.get("MQTT_PASS") or None
    use_ssl = os.environ.get("MQTT_SSL", "").lower() == "true"
    _LOGGER.info("MQTT config: host=%s port=%s user=%s ssl=%s", host, port, username, use_ssl)
    return {"host": host, "port": port, "username": username, "password": password, "use_ssl": use_ssl}


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

    if isinstance(parsed, dict):
        entries: list = [parsed]
    elif isinstance(parsed, list):
        entries = parsed
    else:
        _LOGGER.error("BOXES_JSON has an unexpected shape (%s): %r", type(parsed).__name__, raw)
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
        except KeyError:
            _LOGGER.exception("Skipping malformed box entry %r (missing key)", entry)
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
        _LOGGER.info("Box '%s' detection: %s", box.name, duo_label)

    boxes_by_slug = {box.slug: box for box in boxes}
    settings = RuntimeSettings()

    mqtt_cfg = _load_mqtt_config()
    mqtt_bridge = MqttBridge(
        registry=registry,
        client=client,
        boxes_by_slug=boxes_by_slug,
        catalog=catalog,
        settings=settings,
        host=mqtt_cfg["host"],
        port=mqtt_cfg["port"],
        username=mqtt_cfg["username"],
        password=mqtt_cfg["password"],
        use_ssl=mqtt_cfg["use_ssl"],
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
        on_rf_inbox=mqtt_bridge.publish_rf_inbox_event,
        port=CALLBACK_PORT,
    )
    await callback_server.start()

    callback_base_url = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}"
    _LOGGER.info("Callback base URL: %s", callback_base_url)

    bind_manager = BindManager(client, callback_base_url, settings)
    for box in boxes:
        bind_manager.add_box(box)

    ingress_app = create_ingress_app(
        boxes_by_slug=boxes_by_slug,
        client=client,
        bind_manager=bind_manager,
        inclusion=inclusion,
        registry=registry,
        catalog=catalog,
        mqtt_bridge=mqtt_bridge,
        settings=settings,
    )
    ingress_runner = web.AppRunner(ingress_app)
    await ingress_runner.setup()
    ingress_site = web.TCPSite(ingress_runner, INGRESS_HOST, INGRESS_PORT)
    await ingress_site.start()
    _LOGGER.info("Ingress device-inclusion form listening on %s:%s", INGRESS_HOST, INGRESS_PORT)

    _LOGGER.info("Ready. Use the 'AirSend' Ingress panel to add devices.")

    try:
        await asyncio.Event().wait()
    finally:
        await ingress_runner.cleanup()
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
