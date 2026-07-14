"""
Client HTTP pour AirSendWebService.

Points confirmes empiriquement (cf. historique de conception) :
- Le service ecoute en HTTP simple (pas HTTPS) sur le port 33863, malgre un
  nginx.conf "listen ... ssl" retrouve dans l'ancien addon : ce fichier semble
  obsolete/inactif, le code de l'integration officielle utilise bien
  "http://<ip>:33863/", confirme par curl reel. On ne fait donc AUCUNE gestion
  TLS ici, volontairement.
- L'authentification se fait via un header "Authorization: Bearer <locator>".
  ATTENTION, forme confirmee par un test curl reussi de l'utilisateur (pas le
  simple commentaire du spec, qui est trompeur) :
      sp://<password>@[<localip>]/?gw=<0|1>&rhost=<ipv4>
  CORRECTION IMPORTANTE (les noms de champs etaient inverses dans une version
  anterieure) : "localip" est le nom OFFICIEL Devmel de l'adresse IPv6
  LINK-LOCAL de la box (ex. fe80::dcf6:e5ff:febb:5d74, imprimee sous le
  boitier a cote du mot de passe - c'est litteralement ce qui est appele
  "Local IP" dans l'app officielle). "ipv4" est l'adresse IPv4 LAN
  secondaire (ex. 192.168.1.17), transmise via le parametre "rhost".
- Le endpoint /device n'existe PAS en local (teste avec et sans Bearer) : la
  notion de "device" nomme/type est une construction cloud/app uniquement.
- POST /airsend/bind SANS "channel" dans le body = ecoute globale (aucune
  restriction), c'est le mode qu'on utilise systematiquement (cf. bind_manager).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger("airsend.client")


class AirSendError(Exception):
    """Erreur generique lors d'un appel a AirSendWebService."""


class AirSendAuthError(AirSendError):
    """Locator invalide (401)."""


@dataclass
class BoxConfig:
    """
    Configuration d'une box AirSend, telle que saisie dans les options de
    l'addon.

    localip : adresse IPv6 LINK-LOCAL de la box (ex. fe80::dcf6:e5ff:febb:5d74,
              SANS les crochets) - c'est le nom officiel Devmel ("Local IP"),
              c'est elle qui va entre crochets dans le locator.
    ipv4    : adresse IPv4 LAN secondaire de la box (ex. 192.168.1.17) -
              utilisee comme parametre "rhost" du locator.
    """

    name: str
    localip: str
    ipv4: str
    password: str
    gw: bool = False

    @property
    def slug(self) -> str:
        """Identifiant court utilisable dans une URL de callback (/cb/<slug>)."""
        return "".join(c if c.isalnum() else "_" for c in self.name.lower()) or "box"

    def locator(self) -> str:
        """Construit le locator sp://password@[localip]/?gw=0|1&rhost=ipv4 utilise en Bearer."""
        gw_flag = "1" if self.gw else "0"
        return f"sp://{self.password}@[{self.localip}]/?gw={gw_flag}&rhost={self.ipv4}"


class AirSendClient:
    """
    Un client par instance d'AirSendWebService (le binaire vendorise dans notre
    conteneur, joignable en local sur 127.0.0.1:33863). Le locator (donc la box
    ciblee) est passe par requete, une seule instance du service peut donc
    servir plusieurs box AirSend differentes.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:33863") -> None:
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        # Confirme empiriquement le 2026-07-11 : AirSendWebService retourne
        # 500 (corps vide) des qu'un peu trop de /airsend/transfer arrivent
        # en concurrence (2 simultanes passent, au-dela ca casse - limite
        # exacte non garantie stable). D'ou ce verrou strict (1 seul
        # transfer en vol a la fois). Verrou GLOBAL au client (pas par box)
        # car un seul process AirSendWebService sert potentiellement
        # plusieurs box (cf. docstring de la classe) - la contention
        # observee n'a ete testee qu'avec une seule box configuree, donc on
        # ne sait pas si la limite est par-box (radio physique) ou globale
        # au service. A revalider si une 2e box est ajoutee un jour : un
        # verrou par-box serait faux si la limite s'avere globale.
        self._transfer_lock = asyncio.Lock()

    def start(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "AirSendClient":
        self.start()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------ #
    # Bas niveau
    # ------------------------------------------------------------------ #

    async def _request(
        self,
        method: str,
        path: str,
        box: BoxConfig | None = None,
        json_body: dict | None = None,
    ) -> Any:
        if self._session is None:
            raise AirSendError("AirSendClient.start() must be called before use")

        url = f"{self._base_url}{path}"
        headers = {}
        if box is not None:
            headers["Authorization"] = f"Bearer {box.locator()}"

        try:
            async with self._session.request(
                method, url, json=json_body, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 401:
                    raise AirSendAuthError(f"Invalid locator for {url}")
                if resp.status >= 500:
                    text = await resp.text()
                    raise AirSendError(f"AirSendWebService error {resp.status} on {url}: {text}")
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.text()
        except aiohttp.ClientError as exc:
            raise AirSendError(f"Connection error calling {url}: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Service
    # ------------------------------------------------------------------ #

    async def get_status(self) -> dict:
        """GET /service/status - version du service, pas d'auth requise."""
        return await self._request("GET", "/service/status")

    # ------------------------------------------------------------------ #
    # Catalogue de protocoles
    # ------------------------------------------------------------------ #

    async def list_channels(self, box: BoxConfig) -> list[dict]:
        """GET /channels - liste des ChannelInfo (protocoles RF supportes)."""
        result = await self._request("GET", "/channels", box=box)
        if isinstance(result, list):
            return result
        raise AirSendError("Unexpected /channels response shape")

    # ------------------------------------------------------------------ #
    # Ecoute / emission RF
    # ------------------------------------------------------------------ #

    async def bind(
        self,
        box: BoxConfig,
        callback_url: str,
        duration: float = 3600.0,
        channel: dict | None = None,
    ) -> dict:
        """
        POST /airsend/bind - demarre l'ecoute RF.

        channel=None => ecoute globale (aucun filtre de protocole), c'est le mode
        utilise par defaut par bind_manager : le filtrage se fait cote addon sur
        (channel.id, channel.source) plutot que de multiplier les bind cibles
        (evite la latence d'un round-robin, cf. decision Phase 1).

        BUG CORRIGE (2026-07-14) : cette methode ignorait purement et
        simplement le parametre `channel` et envoyait TOUJOURS un bind cible
        sur {"id": 25455} (PFX), quel que soit l'appelant. Consequence
        pratique : le "bind global" cense tourner en permanence
        (bind_manager.py) etait en realite scope sur PFX depuis le debut -
        les evenements RF entrants sur tout autre protocole (IOU/Somfy,
        etc.) n'ont donc jamais ete recus via bind, seul l'envoi de commandes
        (transfer, qui ne depend pas du bind) fonctionnait normalement pour
        ces appareils. A surveiller apres deploiement : le state tracking de
        devices non-PFX peut se mettre a fonctionner different qu'avant.
        """
        body: dict[str, Any] = {
            "duration": duration,
            "callback": callback_url,
        }
        if channel is not None:
            body["channel"] = channel
        return await self._request("POST", "/airsend/bind", box=box, json_body=body)

    async def unbind(self, box: BoxConfig) -> None:
        """GET /airsend/unbind - stoppe l'ecoute en cours sur cette box."""
        await self._request("GET", "/airsend/unbind", box=box)

    async def transfer(
        self,
        box: BoxConfig,
        channel: dict,
        thingnotes: dict,
        wait: bool = True,
        callback_url: str | None = None,
    ) -> dict:
        """POST /airsend/transfer - envoie une commande sur un channel donne."""
        body: dict[str, Any] = {
            "wait": wait,
            "channel": channel,
            "thingnotes": thingnotes,
        }
        if callback_url is not None:
            body["callback"] = callback_url
        # Serialisation stricte : cf. commentaire sur self._transfer_lock
        # dans __init__. Sans ca, une rafale de commandes (ex. "fermer tous
        # les volets" depuis HA) declenche plusieurs /airsend/transfer
        # concurrents et AirSendWebService en 500 une partie d'entre eux.
        async with self._transfer_lock:
            return await self._request("POST", "/airsend/transfer", box=box, json_body=body)

    async def list_events(self, box: BoxConfig) -> list[dict]:
        """GET /airsend/events - derniers ThingEvent (utilise en secours/debug, on
        prefere le mode callback pousse via bind pour l'usage temps reel)."""
        result = await self._request("GET", "/airsend/events", box=box)
        return result if isinstance(result, list) else []

    async def close_box(self, box: BoxConfig) -> None:
        """GET /airsend/close - ferme toutes les communications RF sur cette box."""
        await self._request("GET", "/airsend/close", box=box)