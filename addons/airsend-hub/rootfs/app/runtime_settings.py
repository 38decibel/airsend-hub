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
        # Duree (en secondes) du bind d'ecoute permanente aupres de chaque
        # box (cf. bind_manager.py). Une valeur modifiee prend effet au
        # PROCHAIN renouvellement naturel du bind, pas immediatement (pas de
        # coupure/redemarrage force du bind en cours pour un simple
        # changement de reglage).
        self.bind_duration_s: float = 3600.0

    # cf. jeeAirSend.php (Jeedom, reference historique) :
    #   reliability > 0x6 (6) && reliability < 0x47 (71)
    # Confirme le 2026-07-09 : la sequence observee sur un vrai appui PFX est
    # 0 -> 64 -> 128 -> 192 (multiples de 64, cohérent avec un compteur de
    # retransmissions plutot qu'une mesure de qualite de signal). La valeur
    # 64 suffit largement a rentrer dans [6, 71] et a declencher
    # l'inclusion ; 128 (observe a 20cm, plus proche que les 50-100cm
    # recommandes par Devmel) n'apportait rien et a ete retire. On revient
    # donc sciemment aux bornes d'origine, sans marge ajoutee.
    RELIABILITY_MIN = 6
    RELIABILITY_MAX = 71
