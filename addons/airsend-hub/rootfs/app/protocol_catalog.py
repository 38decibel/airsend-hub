"""
Cache local du catalogue de protocoles RF (GET /channels, cf. airsend_client),
par box. Sert a :
  - retrouver un nom de protocole lisible (ex: "PFX") depuis un channel.id lors
    de l'inclusion, pour affichage/suggestion a l'utilisateur.
  - detecter au mieux si la box est un AirSend mono-bande ou un AirSend Duo.

Detection Duo - BEST EFFORT, pas une certitude absolue :
  Regle retenue : si la liste retournee par /channels contient au moins un
  protocole `band == 2` (868 MHz), on considere la box comme un AirSend Duo.
  Tous les exemples confirmes de marques 868 MHz (Profalux/PFX, Somfy-Velux
  IO/IOU, Legrand Celiane/IOBL, Deltadore/X2D868+X3D, Thomson ARW, Blyss/BLY)
  sont bien `band: 2` dans le catalogue observe, donc logiquement equivalent
  a la liste de marques fournie par l'utilisateur - MAIS non confirme que le
  firmware filtre reellement ce catalogue selon le modele physique plutot que
  de renvoyer un catalogue logiciel universel. A confirmer par comparaison
  avec le retour d'un AirSend mono-bande reel. En attendant, affiche comme
  "best effort" cote UI, jamais comme fait certain.
"""

from __future__ import annotations

import logging
import time

from airsend_client import AirSendClient, AirSendError, BoxConfig

_LOGGER = logging.getLogger("airsend.protocol_catalog")

_CACHE_TTL_S = 3600.0

# Valeur du champ "band" renvoyee par GET /channels pour un protocole 868MHz.
# Toute autre valeur (typiquement 1) est traitee comme du 433MHz. Exportee
# pour eviter de dupliquer ce nombre magique ailleurs (cf. inclusion_api.py,
# recherche generique 433MHz).
BAND_868_MHZ = 2


class ProtocolCatalog:
    def __init__(self, client: AirSendClient) -> None:
        self._client = client
        # box_slug -> {"channels": [...], "fetched_at": float}
        self._cache: dict[str, dict] = {}

    async def refresh(self, box: BoxConfig) -> list[dict]:
        try:
            channels = await self._client.list_channels(box)
        except AirSendError as exc:
            _LOGGER.warning("Failed to fetch channel catalog for box '%s': %s", box.name, exc)
            return self._cache.get(box.slug, {}).get("channels", [])

        self._cache[box.slug] = {"channels": channels, "fetched_at": time.time()}
        _LOGGER.info("Cached %d protocol(s) for box '%s'", len(channels), box.name)
        return channels

    def _get_cached(self, box_slug: str) -> list[dict]:
        entry = self._cache.get(box_slug)
        if entry is None:
            return []
        if time.time() - entry["fetched_at"] > _CACHE_TTL_S:
            _LOGGER.debug("Protocol cache for box '%s' is stale, refresh recommended", box_slug)
        return entry["channels"]

    def protocol_name_for(self, box_slug: str, channel_id: int) -> str | None:
        for entry in self._get_cached(box_slug):
            if entry.get("id") == channel_id:
                return entry.get("name")
        return None

    def entry_for(self, box_slug: str, channel_id: int) -> dict | None:
        """Retourne l'entree catalogue complete (name, band, id, ...) pour ce
        channel_id, si connue. Utilise pour l'echantillonnage de reliability
        par protocole/bande (cf. callback_server.py), le nom seul ne suffit
        pas a distinguer un biais lie a la bande (433 vs 868 MHz)."""
        for entry in self._get_cached(box_slug):
            if entry.get("id") == channel_id:
                return entry
        return None

    def is_duo_best_effort(self, box_slug: str) -> bool | None:
        """True/False si on a un catalogue en cache pour cette box, None si pas
        encore recupere (ne pas afficher de faux negatif avant le premier refresh)."""
        channels = self._get_cached(box_slug)
        if not channels:
            return None
        return any(entry.get("band") == BAND_868_MHZ for entry in channels)

