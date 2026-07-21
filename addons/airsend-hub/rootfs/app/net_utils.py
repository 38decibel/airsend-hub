"""Miscellaneous network utilities"""

from __future__ import annotations

import ipaddress


def mac_from_link_local(ipv6_str: str) -> str | None:

    try:
        addr = ipaddress.IPv6Address(ipv6_str)
    except ValueError:
        return None

    iid = addr.packed[8:16]
    if iid[3:5] != b"\xff\xfe":
        return None

    mac_bytes = bytearray(iid[0:3] + iid[5:8])
    mac_bytes[0] ^= 0x02
    return ":".join(f"{b:02x}" for b in mac_bytes)
