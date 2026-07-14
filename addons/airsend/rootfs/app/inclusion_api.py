"""
Interface web Ingress pour l'ajout d'appareils, calquee sur le parcours de
l'app cloud officielle (cf. historique de conception) :

  Ajouter un appareil
    -> A: "J'ai la telecommande" ou B: "Je n'ai pas la telecommande"
    -> recherche marque/modele/protocole (autocompletion, cf. catalog_data.py)
    -> si plusieurs protocoles pour la marque choisie: choix explicite
       (ex. Somfy -> IOU/RFY/RTR)
    -> A uniquement: bouton "Play" -> ecoute RF ciblee (cf.
       bind_manager.start_targeted_listen) -> candidat(s) detecte(s)
    -> choix du type de materiel (kind) + nom -> creation du device
       (device_registry + discovery MQTT immediate)

  ATTENTION - changement d'architecture assume : ceci ajoute une UI Ingress,
  ce qui revient sur la decision initiale "MQTT discovery exclusively, no
  Ingress UI" (cf. suivi de conception) - remplacement voulu, uniquement
  pour ce flow de confirmation d'inclusion, le reste (etats, commandes)
  continue de passer entierement par MQTT discovery.

Cette API ne fait AUCUNE creation automatique/silencieuse d'entite : la
confirmation utilisateur (nom + kind, cf. principe acte Phase 1) reste
obligatoire dans tous les cas, y compris branche B.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

from aiohttp import web

from airsend_client import AirSendClient, AirSendError, BoxConfig
from bind_manager import BindManager
from catalog_data import search_brands
from channel_aliases import expected_receive_channels
from device_registry import Device, DeviceRegistry
from inclusion import InclusionState
from mqtt_bridge import MqttBridge
from protocol_catalog import ProtocolCatalog

_LOGGER = logging.getLogger("airsend.inclusion_api")

_WEB_DIR = Path(__file__).parent / "web"

_DEFAULT_LISTEN_DURATION_S = 20.0
_MAX_LISTEN_DURATION_S = 60.0
_SESSION_TTL_S = 600.0  # purge des sessions non confirmees au-dela de 10 min

# kind (choisi dans le formulaire) -> domain HA / MQTT (cf. domains/*.py et
# device_registry.Device.kind/domain). "1_bouton" -> "button" existe deja
# comme domaine command-only cote domains/button.py.
KIND_TO_DOMAIN: dict[str, str] = {
    "1_bouton": "button",
    "on_off": "switch",
    "volet_roulant": "cover",
    "niveau": "cover",
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "device"


class ListenSession:
    """Une session d'ecoute ciblee en cours (etape "Play" de la branche A)."""

    __slots__ = (
        "id", "box_slug", "channel_id", "expected_channels",
        "started_at", "duration", "done", "error",
    )

    def __init__(self, box_slug: str, channel_id: int, duration: float) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.box_slug = box_slug
        self.channel_id = channel_id
        self.expected_channels = expected_receive_channels(channel_id)
        self.started_at = time.time()
        self.duration = duration
        self.done = False
        self.error: str | None = None

    @property
    def remaining_s(self) -> float:
        return max(0.0, self.started_at + self.duration - time.time())

    @property
    def is_stale(self) -> bool:
        return self.done and (time.time() - self.started_at) > _SESSION_TTL_S


class InclusionApi:
    def __init__(
        self,
        boxes_by_slug: dict[str, BoxConfig],
        client: AirSendClient,
        bind_manager: BindManager,
        inclusion: InclusionState,
        registry: DeviceRegistry,
        catalog: ProtocolCatalog,
        mqtt_bridge: MqttBridge,
    ) -> None:
        self._boxes = boxes_by_slug
        self._client = client
        self._bind_manager = bind_manager
        self._inclusion = inclusion
        self._registry = registry
        self._catalog = catalog
        self._mqtt_bridge = mqtt_bridge
        self._sessions: dict[str, ListenSession] = {}
        # Une seule ecoute ciblee a la fois par box : start_targeted_listen
        # relance le bind global des sa propre fin, une 2e session en
        # parallele sur la meme box se ferait donc couper l'herbe sous le
        # pied par la 1ere sans ce garde-fou.
        self._listening_boxes: set[str] = set()

        self.app = web.Application()
        self.app.router.add_get("/api/boxes", self._handle_boxes)
        self.app.router.add_get("/api/devices", self._handle_list_devices)
        self.app.router.add_get("/api/brands", self._handle_search_brands)
        self.app.router.add_get("/api/channel/{channel_id}", self._handle_channel_info)
        self.app.router.add_post("/api/listen", self._handle_start_listen)
        self.app.router.add_get("/api/listen/{session_id}", self._handle_poll_listen)
        self.app.router.add_post("/api/devices", self._handle_confirm_device)
        self.app.router.add_post("/api/devices/manual", self._handle_manual_device)
        self.app.router.add_patch("/api/devices/{key}", self._handle_update_device)
        self.app.router.add_delete("/api/devices/{key}", self._handle_delete_device)
        self.app.router.add_get("/{tail:.*}", self._handle_static)

    # ------------------------------------------------------------------ #
    # Pages statiques (formulaire HTML/JS/CSS, un seul fichier - pas
    # d'outillage de build pour rester coherent avec le reste de l'addon)
    # ------------------------------------------------------------------ #

    async def _handle_static(self, request: web.Request) -> web.Response:
        tail = request.match_info["tail"] or "index.html"
        candidate = (_WEB_DIR / tail).resolve()
        try:
            candidate.relative_to(_WEB_DIR.resolve())
        except ValueError:
            raise web.HTTPForbidden()
        if not candidate.is_file():
            candidate = _WEB_DIR / "index.html"
        return web.FileResponse(candidate)

    # ------------------------------------------------------------------ #
    # Boxes / catalogue
    # ------------------------------------------------------------------ #

    async def _handle_boxes(self, request: web.Request) -> web.Response:
        return web.json_response(
            [{"slug": slug, "name": box.name} for slug, box in self._boxes.items()]
        )

    async def _handle_list_devices(self, request: web.Request) -> web.Response:
        return web.json_response(
            [
                {
                    "key": d.key,
                    "friendly_name": d.friendly_name,
                    "kind": d.kind,
                    "domain": d.domain,
                    "protocol_name": d.protocol_name,
                    "box": d.box,
                    "options": d.options,
                }
                for d in self._registry.all()
            ]
        )

    async def _handle_search_brands(self, request: web.Request) -> web.Response:
        query = request.query.get("q", "")
        return web.json_response(search_brands(query))

    async def _handle_channel_info(self, request: web.Request) -> web.Response:
        box_slug = request.query.get("box") or next(iter(self._boxes), None)
        try:
            channel_id = int(request.match_info["channel_id"])
        except ValueError:
            raise web.HTTPBadRequest(text="channel_id invalide")

        entry = self._catalog.entry_for(box_slug, channel_id) if box_slug else None
        if entry is None:
            return web.json_response({"known": False})
        return web.json_response(
            {
                "known": True,
                "name": entry.get("name"),
                "band": entry.get("band"),
                "counter": entry.get("counter"),
                # cf. channels.json : un `counter` non-nul indique un
                # protocole a code tournant probable. Utilise cote UI pour
                # avertir en branche B (pas de capture RF reelle possible).
                "rolling_code_risk": bool(entry.get("counter")),
            }
        )

    # ------------------------------------------------------------------ #
    # Ecoute RF ciblee (branche A, bouton "Play")
    # ------------------------------------------------------------------ #

    def _prune_stale_sessions(self) -> None:
        for sid in [sid for sid, s in self._sessions.items() if s.is_stale]:
            self._sessions.pop(sid, None)

    async def _handle_start_listen(self, request: web.Request) -> web.Response:
        self._prune_stale_sessions()
        body = await request.json()
        box_slug = body.get("box")
        channel_id = body.get("channel_id")
        try:
            duration = min(float(body.get("duration", _DEFAULT_LISTEN_DURATION_S)), _MAX_LISTEN_DURATION_S)
        except (TypeError, ValueError):
            duration = _DEFAULT_LISTEN_DURATION_S

        box = self._boxes.get(box_slug)
        if box is None or not isinstance(channel_id, int):
            raise web.HTTPBadRequest(text="box ou channel_id invalide")

        if box_slug in self._listening_boxes:
            raise web.HTTPConflict(text="Une ecoute est deja en cours sur cette box")

        handle = self._bind_manager.get_handle(box_slug)
        if handle is None:
            raise web.HTTPBadRequest(text="box inconnue du bind_manager")

        session = ListenSession(box_slug, channel_id, duration)
        self._sessions[session.id] = session
        self._listening_boxes.add(box_slug)

        was_active = self._inclusion.active
        self._inclusion.active = True

        async def _run() -> None:
            try:
                await handle.start_targeted_listen(channel_id, duration)
            except AirSendError as exc:
                session.error = str(exc)
                _LOGGER.warning(
                    "Targeted listen failed for box=%s channel=%s: %s", box_slug, channel_id, exc
                )
            finally:
                if not was_active:
                    self._inclusion.active = False
                session.done = True
                self._listening_boxes.discard(box_slug)

        asyncio.create_task(_run())
        return web.json_response({"session_id": session.id, "duration": duration})

    async def _handle_poll_listen(self, request: web.Request) -> web.Response:
        session = self._sessions.get(request.match_info["session_id"])
        if session is None:
            raise web.HTTPNotFound()

        candidates = [
            {
                "box": c.box,
                "channel_id": c.channel_id,
                "channel_source": c.channel_source,
                "protocol_name": c.protocol_name,
            }
            for c in self._inclusion.list_candidates()
            if c.box == session.box_slug
            and c.channel_id in session.expected_channels
            and c.last_seen >= session.started_at
        ]

        return web.json_response(
            {
                "status": "error" if session.error else ("done" if session.done else "listening"),
                "error": session.error,
                "remaining_s": round(session.remaining_s, 1),
                "candidates": candidates,
            }
        )

    # ------------------------------------------------------------------ #
    # Creation d'appareil (commun aux deux branches)
    # ------------------------------------------------------------------ #

    def _create_device(
        self,
        box_slug: str,
        channel_id: int,
        channel_source: int,
        protocol_name: str | None,
        kind: str,
        friendly_name: str,
        options: dict[str, Any],
        source_of_creation: str,
    ) -> Device:
        domain = KIND_TO_DOMAIN.get(kind)
        if domain is None:
            raise web.HTTPBadRequest(text=f"kind inconnu: {kind}")

        base_key = _slugify(friendly_name)
        key = base_key
        suffix = 2
        while self._registry.get(key) is not None:
            key = f"{base_key}_{suffix}"
            suffix += 1

        device = Device(
            key=key,
            box=box_slug,
            channel_id=channel_id,
            channel_source=channel_source,
            protocol_name=protocol_name,
            kind=kind,
            domain=domain,
            friendly_name=friendly_name,
            options=options or {},
            source_of_creation=source_of_creation,
        )
        self._registry.add(device)
        self._mqtt_bridge.publish_discovery(device)
        _LOGGER.info(
            "New device created via ingress UI: %s (kind=%s domain=%s source=%s)",
            key, kind, domain, source_of_creation,
        )
        return device

    async def _handle_confirm_device(self, request: web.Request) -> web.Response:
        """Branche A : confirmation d'un candidat detecte pendant une session
        d'ecoute (cf. _handle_start_listen)."""
        body = await request.json()
        session = self._sessions.get(body.get("session_id"))
        if session is None:
            raise web.HTTPNotFound(text="session d'ecoute inconnue ou expiree")

        try:
            channel_source = int(body["channel_source"])
            kind = str(body["kind"])
            friendly_name = str(body["friendly_name"]).strip()
        except (KeyError, ValueError, TypeError):
            raise web.HTTPBadRequest(text="champs manquants ou invalides")

        if not friendly_name:
            raise web.HTTPBadRequest(text="friendly_name vide")

        candidate = next(
            (
                c for c in self._inclusion.list_candidates()
                if c.box == session.box_slug
                and c.channel_source == channel_source
                and c.channel_id in session.expected_channels
            ),
            None,
        )
        if candidate is None:
            raise web.HTTPNotFound(text="candidat introuvable (session expiree ?)")

        # IMPORTANT : c'est le canal REELLEMENT RECU (candidate.channel_id,
        # ex. HPD 25454) qu'il faut enregistrer, pas le canal declare choisi
        # par l'utilisateur (ex. PFX 25455, canal virtuel emission seule,
        # cf. channel_aliases.py) - sinon device_registry.match() ne
        # matchera plus jamais les futures trames recues de ce device.
        device = self._create_device(
            box_slug=session.box_slug,
            channel_id=candidate.channel_id,
            channel_source=channel_source,
            protocol_name=candidate.protocol_name,
            kind=kind,
            friendly_name=friendly_name,
            options=body.get("options") or {},
            source_of_creation="rf_listen",
        )
        self._inclusion.pop_candidate(session.box_slug, candidate.channel_id, channel_source)
        self._sessions.pop(session.id, None)
        return web.json_response({"key": device.key})

    async def _handle_manual_device(self, request: web.Request) -> web.Response:
        """
        Branche B : pas de telecommande, pas d'ecoute RF - l'utilisateur
        saisit directement channel_id/channel_source. AUCUNE verification que
        cette valeur correspond a un appareil reel n'est possible ici.

        Si le protocole choisi utilise un compteur (rolling-code probable,
        cf. /api/channel/<id>), on bloque une premiere fois avec un
        avertissement explicite (409) plutot que de creer silencieusement un
        device dont les toutes premieres commandes ont de fortes chances
        d'echouer (compteur jamais synchronise faute de capture reelle) -
        l'utilisateur peut passer outre en renvoyant la meme requete avec
        confirm_rolling_code_risk=true.
        """
        body = await request.json()
        try:
            box_slug = body["box"]
            channel_id = int(body["channel_id"])
            channel_source = int(body["channel_source"])
            kind = str(body["kind"])
            friendly_name = str(body["friendly_name"]).strip()
        except (KeyError, ValueError, TypeError):
            raise web.HTTPBadRequest(text="champs manquants ou invalides")

        if box_slug not in self._boxes:
            raise web.HTTPBadRequest(text="box inconnue")
        if not friendly_name:
            raise web.HTTPBadRequest(text="friendly_name vide")

        entry = self._catalog.entry_for(box_slug, channel_id)
        rolling_code_risk = bool(entry.get("counter")) if entry else False
        if rolling_code_risk and not body.get("confirm_rolling_code_risk"):
            return web.json_response(
                {
                    "warning": "rolling_code_risk",
                    "message": (
                        "Ce protocole utilise un code tournant (rolling code). "
                        "Sans capture reelle de votre telecommande, le compteur "
                        "ne sera pas synchronise et les premieres commandes "
                        "envoyees risquent d'echouer."
                    ),
                },
                status=409,
            )

        device = self._create_device(
            box_slug=box_slug,
            channel_id=channel_id,
            channel_source=channel_source,
            protocol_name=self._catalog.protocol_name_for(box_slug, channel_id),
            kind=kind,
            friendly_name=friendly_name,
            options=body.get("options") or {},
            source_of_creation="manual",
        )
        return web.json_response({"key": device.key})

    async def _handle_update_device(self, request: web.Request) -> web.Response:
        """Edition limitee a friendly_name/options (cf. reponse utilisateur :
        pas de changement de kind/protocole/canal via cette route - cela
        reviendrait a re-inclure un appareil different sous une identite
        existante, avec le risque de desync device_registry <-> discovery
        MQTT deja publiee que ca implique)."""
        key = request.match_info["key"]
        device = self._registry.get(key)
        if device is None:
            raise web.HTTPNotFound(text="appareil inconnu")

        body = await request.json()

        friendly_name = body.get("friendly_name")
        if friendly_name is not None:
            friendly_name = str(friendly_name).strip()
            if not friendly_name:
                raise web.HTTPBadRequest(text="friendly_name vide")

        options = body.get("options")
        if options is not None and not isinstance(options, dict):
            raise web.HTTPBadRequest(text="options invalide")

        updated = self._registry.update(key, friendly_name=friendly_name, options=options)
        # Meme domain/topics qu'a la creation (kind non modifiable ici) : un
        # republish suffit, pas besoin de remove_discovery prealable.
        self._mqtt_bridge.publish_discovery(updated)
        _LOGGER.info(
            "Device %s updated via ingress UI (friendly_name=%s options=%s)",
            key, friendly_name, options,
        )
        return web.json_response(
            {"key": updated.key, "friendly_name": updated.friendly_name, "options": updated.options}
        )

    async def _handle_delete_device(self, request: web.Request) -> web.Response:
        key = request.match_info["key"]
        device = self._registry.get(key)
        if device is None:
            raise web.HTTPNotFound(text="appareil inconnu")

        # Payload vide retenu sur le topic discovery = suppression cote HA
        # (cf. mqtt_bridge.remove_discovery) - a faire AVANT de retirer du
        # registre, sinon plus moyen de retrouver le domain/topics du device.
        self._mqtt_bridge.remove_discovery(device)
        self._registry.remove(key)
        _LOGGER.info("Device %s removed via ingress UI", key)
        return web.json_response({"key": key, "deleted": True})


def create_ingress_app(
    boxes_by_slug: dict[str, BoxConfig],
    client: AirSendClient,
    bind_manager: BindManager,
    inclusion: InclusionState,
    registry: DeviceRegistry,
    catalog: ProtocolCatalog,
    mqtt_bridge: MqttBridge,
) -> web.Application:
    api = InclusionApi(
        boxes_by_slug=boxes_by_slug,
        client=client,
        bind_manager=bind_manager,
        inclusion=inclusion,
        registry=registry,
        catalog=catalog,
        mqtt_bridge=mqtt_bridge,
    )
    return api.app
