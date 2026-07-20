"""
Catalogue statique marque -> protocole(s)/canal(aux), extrait du bundle web
officiel airsend.cloud (reverse engineering du JS Dart, cf. historique de
conception) et croise avec channels.json au moment de l'extraction (seuls les
canaux reellement supportes localement sont gardes, cf. data/catalog.json).

Sert UNIQUEMENT a l'autocompletion du formulaire d'inclusion (UI ingress,
cf. inclusion_api.py) - jamais utilise pour deviner un kind ou creer un
appareil automatiquement (cf. principe acte Phase 1 : confirmation
utilisateur systematique).

Ce catalogue peut etre incomplet ou legerement date (capture ponctuelle du
site officiel) : une marque/un modele absent d'ici n'empeche pas l'ajout
manuel (branche B du formulaire), il prive juste l'utilisateur de
l'autocompletion pour ce cas precis.
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
    """
    Recherche insensible a la casse sur le nom de marque (sous-chaine).
    Retourne une liste triee (prefixe exact d'abord) de :
        [{"brand": "Somfy", "protocols": [{"protocol": "IOU", "channel_id": 26848}, ...]}, ...]
    """
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
