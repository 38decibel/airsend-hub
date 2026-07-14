"""
Cycle de vie du "bind" RF par box.

Decision actee : UN SEUL bind permanent et large par box (pas de "channel"
dans le body => ecoute globale), renouvele avant expiration. Le filtrage par
appareil connu se fait cote callback_server.py sur (channel.id, channel.source),
pas ici. Ca evite le compromis latence/nombre-d'appareils d'un bind en
round-robin façon Jeedom (cf. discussion Phase 1).
"""

from __future__ import annotations

import asyncio
import logging

from airsend_client import AirSendClient, AirSendError, BoxConfig
from runtime_settings import RuntimeSettings

_LOGGER = logging.getLogger("airsend.bind_manager")

# Marge de securite avant expiration du bind pour lancer le renouvellement.
_RENEW_MARGIN_S = 60.0


class BoxBindHandle:
    """Represente le bind actif (ou en cours de (re)tentative) pour une box."""

    def __init__(self, client: AirSendClient, box: BoxConfig, callback_base_url: str, settings: RuntimeSettings) -> None:
        self._client = client
        self.box = box
        self._callback_url = f"{callback_base_url.rstrip('/')}/cb/{box.slug}"
        self._settings = settings
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    @property
    def callback_url(self) -> str:
        return self._callback_url

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(), name=f"bind-{self.box.slug}")

    async def stop(self) -> None:
        self._stopped.set()
    
        try:
            if self._task is not None:
                self._task.cancel()
                await self._task
        finally:
            self._task = None
            try:
                await self._client.unbind(self.box)
            except AirSendError as exc:
                _LOGGER.debug(
                    "unbind failed for box %s (probably already unbound): %s",
                    self.box.name,
                    exc,
                )

    async def start_targeted_listen(self, channel_id: int, duration: float) -> None:
        """
        Interrompt temporairement le bind global permanent pour ecouter UN
        SEUL canal (mirroir de ce que fait l'app cloud lors de l'etape
        d'ecoute a l'inclusion, cf. discussion de conception). Necessaire
        car /airsend/close indique explicitement "stop listening too" - tout
        porte a croire qu'une seule session de bind est active a la fois
        cote AirSendWebService, donc un bind cible REMPLACE le bind global le
        temps de l'ecoute plutot que de s'y ajouter.

        Pendant cette fenetre, les evenements des AUTRES appareils deja
        connus ne sont PAS captes (pas juste retardes - perdus). Le bind
        global est TOUJOURS relance a la fin (succes, echec ou exception),
        pour ne jamais laisser une box sans ecoute active.

        Question ouverte non tranchee (cf. suivi de conception) : si
        l'identite du bouton physique presse s'avere deductible de
        thingnotes.notes de facon fiable, il pourrait devenir preferable de
        garder un bind cible permanent par device plutot que de toujours
        revenir au bind global apres l'inclusion - pas implemente ici tant
        que cette investigation n'a pas conclu, pour ne pas degrader le
        state tracking des devices existants sur une hypothese non validee.
        """
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        try:
            await self._client.bind(
                self.box,
                callback_url=self._callback_url,
                duration=duration,
                channel={"id": channel_id},
            )
            await asyncio.sleep(duration)
        finally:
            self.start()  # relance systematiquement la boucle de bind global

    async def _run(self) -> None:
        """Boucle de (re)bind avec backoff simple en cas d'echec (box offline,
        mot de passe invalide, etc.) - ne doit jamais planter tout le process."""
        backoff = 5.0
        while not self._stopped.is_set():
            duration = self._settings.bind_duration_s
            try:
                _LOGGER.info(
                    "Binding box '%s' (callback=%s, duration=%ss)",
                    self.box.name,
                    self._callback_url,
                    duration,
                )
                await self._client.bind(
                    self.box,
                    callback_url=self._callback_url,
                    duration=duration,
                )
                backoff = 5.0  # succes => on reset le backoff pour la prochaine erreur eventuelle
                sleep_for = max(duration - _RENEW_MARGIN_S, 5.0)
                await asyncio.sleep(sleep_for)
            except asyncio.CancelledError:
                raise
            except AirSendError as exc:
                _LOGGER.warning(
                    "Bind failed for box '%s' (%s) - retrying in %.0fs",
                    self.box.name,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300.0)  # backoff exponentiel plafonne a 5 min


class BindManager:
    """Orchestre un BoxBindHandle par box configuree."""

    def __init__(self, client: AirSendClient, callback_base_url: str, settings: RuntimeSettings) -> None:
        self._client = client
        self._callback_base_url = callback_base_url
        self._settings = settings
        self._handles: dict[str, BoxBindHandle] = {}

    def add_box(self, box: BoxConfig) -> BoxBindHandle:
        handle = BoxBindHandle(self._client, box, self._callback_base_url, self._settings)
        self._handles[box.slug] = handle
        handle.start()
        return handle

    def get_handle(self, box_slug: str) -> BoxBindHandle | None:
        return self._handles.get(box_slug)

    async def stop_all(self) -> None:
        await asyncio.gather(*(h.stop() for h in self._handles.values()), return_exceptions=True)
