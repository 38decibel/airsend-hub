"""
Mode inclusion : quand actif, toute trame RF fiable dont (box, channel.id,
channel.source) n'est pas deja dans le device_registry devient un "candidat"
en attente de confirmation utilisateur (nom + kind + options), plutot que
d'etre auto-cree silencieusement (contrairement a l'ancien hass_cb.php).

Ce module ne fait volontairement AUCUNE deduction automatique de domaine/kind:
c'est toujours l'utilisateur qui tranche (cf. decisions actees Phase 1).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

_LOGGER = logging.getLogger("airsend.inclusion")


@dataclass
class Candidate:
    box: str
    channel_id: int
    channel_source: int
    protocol_name: str | None
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    suggested_kind: str | None = None  # pre-rempli depuis protocol_domain_learned.json
    hint_name: str | None = None  # pre-rempli si dispo (ex: import cloud)

    @property
    def match_key(self) -> tuple[str, int, int]:
        return (self.box, self.channel_id, self.channel_source)


class InclusionState:
    def __init__(self) -> None:
        self.active: bool = False
        self._candidates: dict[tuple[str, int, int], Candidate] = {}

    def start(self) -> None:
        self.active = True
        _LOGGER.info("Inclusion mode ON")

    def stop(self) -> None:
        self.active = False
        _LOGGER.info("Inclusion mode OFF")

    def upsert_candidate(
        self,
        box: str,
        channel_id: int,
        channel_source: int,
        protocol_name: str | None,
        suggested_kind: str | None = None,
        hint_name: str | None = None,
    ) -> Candidate:
        key = (box, channel_id, channel_source)
        existing = self._candidates.get(key)
        if existing is not None:
            existing.last_seen = time.time()
            return existing

        candidate = Candidate(
            box=box,
            channel_id=channel_id,
            channel_source=channel_source,
            protocol_name=protocol_name,
            suggested_kind=suggested_kind,
            hint_name=hint_name,
        )
        self._candidates[key] = candidate
        _LOGGER.info(
            "New inclusion candidate: box=%s channel=%s/%s protocol=%s",
            box, channel_id, channel_source, protocol_name,
        )
        return candidate

    def list_candidates(self) -> list[Candidate]:
        return list(self._candidates.values())

    def pop_candidate(self, box: str, channel_id: int, channel_source: int) -> Candidate | None:
        return self._candidates.pop((box, channel_id, channel_source), None)
