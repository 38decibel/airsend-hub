"""
Serveur HTTP interne qui recoit les evenements pousses par AirSendWebService
suite a un `bind` avec callback (cf. bind_manager.py).

Forme confirmee du body recu (source: hass_cb.php, pas seulement le spec) :
    { "events": [ ThingEvent, ThingEvent, ... ] }
=> PAS un ThingEvent unique, toujours un batch. C'etait une hypothese fausse
dans une version anterieure de la conception, corrigee ici.

Deux categories de ThingEvent, distinguees par la presence de thingnotes.uid :

  - AVEC uid : evenement lie a UNE COMMANDE QUE NOUS AVONS ENVOYEE nous-memes
    (uid = sha256 tronque de l'entity_id, genere cote nous au moment du
    POST /airsend/transfer). Sert a acquitter nos propres commandes. On ne
    route PAS ca vers l'inclusion : ce n'est jamais une nouvelle detection.

  - SANS uid : evenement non sollicite = candidat serieux pour "quelqu'un a
    appuye sur une telecommande physique". On ne le traite QUE si :
      * type == 3 (GOT, cf. enum ThingEvent.type du spec)
      * ET reliability compris entre 0x6 (6) et 0x47 (71) inclus/exclusif
        (cf. hass_cb.php : `$val['reliability'] > 0x6 && $val['reliability'] < 0x47`)
    Le champ `reliability` n'apparait dans AUCUN spec OpenAPI vu jusqu'ici :
    c'est une extension non documentee du firmware, mais confirmee critique en
    pratique - sans ce filtre, on capte du bruit RF ambiant en plus des
    vraies pressions de telecommande.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from aiohttp import web

from device_registry import DeviceRegistry
from inclusion import InclusionState
from protocol_catalog import ProtocolCatalog
from runtime_settings import RuntimeSettings
from thing_notes import convert_notes_to_states

_LOGGER = logging.getLogger("airsend.callback_server")

# Signature du callback appele pour chaque etat decode et route vers un device connu.
# (device_key, stype, svalue, channel) -> None
StateSink = Callable[[str, str, object, dict], Awaitable[None]]


class CallbackServer:
    def __init__(
        self,
        registry: DeviceRegistry,
        inclusion: InclusionState,
        catalog: ProtocolCatalog,
        settings: RuntimeSettings,
        on_state: StateSink,
        host: str = "127.0.0.1",
        port: int = 8126,
    ) -> None:
        self._registry = registry
        self._inclusion = inclusion
        self._catalog = catalog
        self._settings = settings
        self._on_state = on_state
        self._host = host
        self._port = port
        self._app = web.Application()
        self._app.router.add_post("/cb/{box_slug}", self._handle_callback)
        self._runner: web.AppRunner | None = None

    @property
    def base_url_hint(self) -> str:
        """Utile pour construire callback_base_url passe a BindManager - a
        remplacer par l'IP interne reelle du conteneur au demarrage (main.py)."""
        return f"http://<addon_ip>:{self._port}"

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        _LOGGER.info("Callback server listening on %s:%s", self._host, self._port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    # ------------------------------------------------------------------ #
    # Handler
    # ------------------------------------------------------------------ #

    async def _handle_callback(self, request: web.Request) -> web.Response:
        box_slug = request.match_info["box_slug"]
        try:
            payload = await request.json()
        except Exception as exc:  # payload malforme : on logue et on repond 200 quand meme
            _LOGGER.warning("Malformed callback payload from box %s: %s", box_slug, exc)
            return web.Response(status=200)

        events = payload.get("events")
        if not isinstance(events, list):
            _LOGGER.debug("Callback payload without 'events' array from box %s: %r", box_slug, payload)
            return web.Response(status=200)

        for event in events:
            try:
                await self._handle_event(box_slug, event)
            except Exception:
                _LOGGER.exception("Error processing event from box %s: %r", box_slug, event)

        return web.Response(status=200)

    async def _handle_event(self, box_slug: str, event: dict) -> None:
        channel = event.get("channel") or {}
        thingnotes = event.get("thingnotes") or {}
        notes = thingnotes.get("notes") or []
        event_type = event.get("type")

        channel_id = channel.get("id")
        channel_source = channel.get("source")
        if channel_id is None or channel_source is None:
            _LOGGER.debug("Event without channel id/source, ignored: %r", event)
            return

        has_uid = "uid" in thingnotes and thingnotes.get("uid") is not None

        if has_uid:
            # Accuse de reception d'une commande qu'on a nous-memes envoyee.
            # Pas de routage inclusion. Log pour debug / futur suivi d'ACK.
            _LOGGER.debug(
                "Command ack event (uid=%s) type=%s on box=%s channel=%s/%s",
                thingnotes.get("uid"), event_type, box_slug, channel_id, channel_source,
            )
            return

        # --- Evenement non sollicite : candidat "telecommande physique" ---
        if event_type != 3:  # GOT uniquement
            _LOGGER.debug(
                "Interrupt event ignored (type=%s != GOT) on box=%s channel=%s/%s",
                event_type, box_slug, channel_id, channel_source,
            )
            return

        reliability = event.get("reliability")
        reliability_min = self._settings.reliability_min
        reliability_max = RuntimeSettings.RELIABILITY_MAX
        if not isinstance(reliability, (int, float)) or not (reliability_min < reliability < reliability_max):
            _LOGGER.debug(
                "Interrupt event dropped (reliability=%s out of range [%s, %s]) on box=%s channel=%s/%s",
                reliability, reliability_min, reliability_max, box_slug, channel_id, channel_source,
            )
            return

        device = self._registry.match(box_slug, channel_id, channel_source)

        if device is not None:
            states = convert_notes_to_states(notes)
            for stype, svalue in states:
                await self._on_state(device.key, stype, svalue, channel)
            return

        # Appareil inconnu : on ne cree JAMAIS automatiquement (contrairement a
        # l'ancien hass_cb.php). On alimente la file de candidats uniquement si
        # le mode inclusion est actif - sinon on ignore silencieusement pour
        # ne pas polluer les logs avec tout le bruit RF ambiant du foyer.
        if not self._inclusion.active:
            _LOGGER.debug(
                "Unknown device, inclusion mode OFF, ignored: box=%s channel=%s/%s",
                box_slug, channel_id, channel_source,
            )
            return

        protocol_name = self._catalog.protocol_name_for(box_slug, channel_id)
        self._inclusion.upsert_candidate(
            box=box_slug,
            channel_id=channel_id,
            channel_source=channel_source,
            protocol_name=protocol_name,
        )
