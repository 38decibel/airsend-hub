"""
Reglages ajustables depuis HA (entites MQTT "number", categorie config),
partages par reference entre callback_server.py et mqtt_bridge.py.

Volontairement un objet mutable simple plutot qu'une valeur immuable : le
changement doit prendre effet immediatement sur la prochaine trame recue,
sans redemarrage de l'addon.
"""

from __future__ import annotations


class RuntimeSettings:
    def __init__(self) -> None:
        # cf. hass_cb.php : reliability > 0x6 (6) && reliability < 0x47 (71).
        # Seule la borne basse est exposee comme reglage utilisateur pour
        # l'instant - c'est elle qui a le plus d'impact pratique (exclure le
        # bruit RF ambiant). La borne haute reste fixe, non exposee tant
        # qu'on n'a pas de cas reel justifiant de la rendre ajustable aussi.
        self.reliability_min: int = 6

        # Duree (en secondes) du bind d'ecoute permanente aupres de chaque
        # box (cf. bind_manager.py). Une valeur modifiee prend effet au
        # PROCHAIN renouvellement naturel du bind, pas immediatement (pas de
        # coupure/redemarrage force du bind en cours pour un simple
        # changement de reglage).
        self.bind_duration_s: float = 3600.0

    # Releve le 2026-07-09 : un vrai appui telecommande PFX (Profalux) a
    # produit reliability=128, hors de l'ancienne borne 0x47 (71) heritee de
    # hass_cb.php. Cette ancienne plage n'a probablement ete calibree que sur
    # des protocoles 433 MHz (band=1) ; PFX est 868 MHz (band=2) et semble
    # utiliser une echelle differente. 128 est retenu ici comme borne haute
    # provisoire, EMPIRIQUE et NON DEFINITIVE - a reviser une fois
    # l'echantillonnage (cf. reliability_sample logs) accumule assez de
    # mesures reelles par protocole/bande, notamment a la distance boitier
    # recommandee par Devmel (50-100cm ; le premier test a 20cm peut avoir
    # biaise la mesure).
    RELIABILITY_MAX = 128
