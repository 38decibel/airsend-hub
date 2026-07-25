"""
Inclusion mode: when active, any valid RF frame where the tuple 
(box, channel.id, channel.source) is not already in the `device_registry`
becomes a "candidate" awaiting user confirmation (name + kind + options),
rather than being silently auto-created.

This module intentionally makes NO automatic inferences regarding domain
or kind: the user always makes the final decision.
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

    @property
    def match_key(self) -> tuple[str, int, int]:
        return (self.box, self.channel_id, self.channel_source)


class InclusionState:
    def __init__(self) -> None:
        self.active: bool = False
        self._candidates: dict[tuple[str, int, int], Candidate] = {}

    def upsert_candidate(
        self,
        box: str,
        channel_id: int,
        channel_source: int,
        protocol_name: str | None,
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
