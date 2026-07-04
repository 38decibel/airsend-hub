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

    RELIABILITY_MAX = 0x47  # 71, fixe
