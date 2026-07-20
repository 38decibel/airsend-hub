"""
Static brand-to-protocol/channel catalog, extracted from the official 
airsend.cloud web bundle and cross-referenced with `channels.json` during 
extraction (only channels actually supported locally are retained; see `data/catalog.json`).

It is used ONLY for autocompletion in the inclusion form 
(ingress UI; see `inclusion_api.py`), never to infer a device type or 
automatically create a device.

This catalog may be incomplete or slightly outdated (as it is a snapshot
of the official site); a brand or model missing from the list does not 
prevent manual addition, but simply means autocompletion
is unavailable for that specific case.
"""

from __future__ import annotations

import json
import os

_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "data", "catalog.json")

_catalog: dict[str, list[dict]] | None = None


def _load() -> dict[str, list[dict]]:
    global _catalog
    if _catalog is None:
        try:
            with open(_CATALOG_PATH, "r", encoding="utf-8") as fh:
                _catalog = json.load(fh)
        except (OSError, json.JSONDecodeError):
            _catalog = {}
    return _catalog


def search_brands(query: str, limit: int = 20) -> list[dict]:
    catalog = _load()
    q = query.strip().lower()
    if not q:
        return []
    results = [
        {"brand": brand, "protocols": protocols}
        for brand, protocols in catalog.items()
        if q in brand.lower()
    ]
    results.sort(key=lambda b: (not b["brand"].lower().startswith(q), b["brand"]))
    return results[:limit]


def protocols_for_brand(brand: str) -> list[dict]:
    return _load().get(brand, [])
