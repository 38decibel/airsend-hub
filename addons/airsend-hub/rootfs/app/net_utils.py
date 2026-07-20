"""Utilitaires reseau divers."""

from __future__ import annotations

import ipaddress


def mac_from_link_local(ipv6_str: str) -> str | None:
    """
    Derive l'adresse MAC-48 a partir d'une adresse IPv6 link-local generee en
    modified EUI-64 (cas standard des boxes AirSend). Retourne None si
    l'adresse n'est pas valide ou ne suit pas ce format (pas de "ff:fe" au
    milieu de l'identifiant d'interface).

    Exemple confirme : fe80::dcf6:e5ff:febb:5d74 -> de:f6:e5:bb:5d:74
    """
    try:
        addr = ipaddress.IPv6Address(ipv6_str)
    except ValueError:
        return None

    iid = addr.packed[8:16]  # 8 derniers octets = identifiant d'interface
    if iid[3:5] != b"\xff\xfe":
        return None

    mac_bytes = bytearray(iid[0:3] + iid[5:8])
    mac_bytes[0] ^= 0x02  # flip du bit universal/local (7e bit)
    return ":".join(f"{b:02x}" for b in mac_bytes)
