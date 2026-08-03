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
    decoded: bool = True
    seen_count: int = 1
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    last_action: str | None = None
    last_notes: list = field(default_factory=list)

    @property
    def match_key(self) -> tuple[str, int, int]:
        return (self.box, self.channel_id, self.channel_source)


class InclusionState:
    def __init__(self) -> None:
        self.active: bool = False
        self._candidates: dict[tuple[str, int, int], Candidate] = {}
        # Keys the user explicitly dismissed ("forget"): never re-surfaced,
        # even if the same source keeps transmitting. In-memory only, reset
        # on addon restart (acceptable: not persisted on purpose, see PR
        # discussion - a noisy neighbour source is easy to forget again).
        self._ignored: set[tuple[str, int, int]] = set()

    def upsert_candidate(
        self,
        box: str,
        channel_id: int,
        channel_source: int,
        protocol_name: str | None,
        decoded: bool = True,
        last_action: str | None = None,
        last_notes: list | None = None,
    ) -> Candidate | None:
        key = (box, channel_id, channel_source)
        if key in self._ignored:
            return None

        existing = self._candidates.get(key)
        if existing is not None:
            existing.last_seen = time.time()
            existing.seen_count += 1
            existing.decoded = existing.decoded or decoded
            if last_action is not None:
                existing.last_action = last_action
            if last_notes is not None:
                existing.last_notes = last_notes
            return existing

        candidate = Candidate(
            box=box,
            channel_id=channel_id,
            channel_source=channel_source,
            protocol_name=protocol_name,
            decoded=decoded,
            last_action=last_action,
            last_notes=last_notes if last_notes is not None else [],
        )
        self._candidates[key] = candidate
        _LOGGER.info(
            "New inclusion candidate: box=%s channel=%s/%s protocol=%s decoded=%s",
            box, channel_id, channel_source, protocol_name, decoded,
        )
        return candidate

    def list_candidates(self) -> list[Candidate]:
        return list(self._candidates.values())

    def pop_candidate(self, box: str, channel_id: int, channel_source: int) -> Candidate | None:
        return self._candidates.pop((box, channel_id, channel_source), None)

    def forget_candidate(self, box: str, channel_id: int, channel_source: int) -> bool:
        """Dismiss a candidate for good: removes it and prevents it from
        being re-created by further frames from the same source."""
        key = (box, channel_id, channel_source)
        self._ignored.add(key)
        return self._candidates.pop(key, None) is not None
