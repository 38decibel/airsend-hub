'''
Mapping table between the channel DECLARED for a brand/protocol (as
cataloged by airsend.cloud; see catalog_data.py) and the channels
ACTUALLY received by the hub for that same physical protocol.

Required only for cases where the hub decodes a received RF signal as
a protocol DIFFERENT from the one used for transmission. Empirically confirmed
ONLY for Profalux (see raw_event_body, callback_server.py): PFX
(25455) is a TRANSMIT-ONLY virtual channel; an actual press on a
Profalux remote is received by the hub as HPD (25454) or KLQ868
(25457), never as PFX.

Intentionally a minimal WHITELIST, not a general rule: without
equivalent empirical evidence for another protocol, this phenomenon is not
generalized. A channel absent from this table is filtered STRICTLY against
itself during inclusion listening (default behavior, correct for
the vast majority of protocols). To be updated on a case-by-case basis if another
protocol exhibits the same behavior (observable via raw_event_body
during an actual listening session), not by extrapolation.
'''

from __future__ import annotations

RECEIVE_ALIASES: dict[int, set[int]] = {
    25455: {25454, 25455, 25457},
}


def expected_receive_channels(declared_channel_id: int) -> set[int]:
    """Channels on which support can actually be received for a given
    'declared' (catalog) channel. This always includes the declared 
    channel itself, even when an entry exists in RECEIVE_ALIASES."""
    return RECEIVE_ALIASES.get(declared_channel_id, {declared_channel_id})
