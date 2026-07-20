"""
Table de correspondance entre le canal DECLARE pour une marque/protocole (tel
que catalogue par airsend.cloud, cf. catalog_data.py) et les canaux
REELLEMENT recus par la box pour ce meme protocole physique.

Necessaire uniquement pour les cas ou la box decode un signal RF recu comme
un protocole DIFFERENT de celui utilise en emission. Confirme empiriquement
UNIQUEMENT pour Profalux (cf. raw_event_body, callback_server.py) : PFX
(25455) est un canal virtuel EMISSION SEULE, un appui reel sur une
telecommande Profalux est recu par la box comme HPD (25454) ou KLQ868
(25457), jamais comme PFX.

Volontairement une LISTE BLANCHE minimale, pas une regle generale : sans
preuve empirique equivalente pour un autre protocole, on ne generalise pas ce
phenomene. Un canal absent de cette table est filtre STRICTEMENT sur
lui-meme lors de l'ecoute d'inclusion (comportement par defaut, correct pour
la grande majorite des protocoles). A completer au cas par cas si un autre
protocole presente le meme comportement (observable via raw_event_body
pendant une session d'ecoute reelle), pas par extrapolation.
"""

from __future__ import annotations

RECEIVE_ALIASES: dict[int, set[int]] = {
    # PFX (Profalux, mais aussi Eveno/FranciaFlex/FliP/France fermetures qui
    # partagent ce meme canal declare, cf. catalog_data.py) -> HPD ou KLQ868
    # selon la trame reellement decodee par la box.
    25455: {25454, 25455, 25457},
}


def expected_receive_channels(declared_channel_id: int) -> set[int]:
    """Canaux sur lesquels un appui peut reellement etre recu, pour un canal
    'declare' (catalogue) donne. Inclut toujours le canal declare lui-meme,
    meme quand une entree existe dans RECEIVE_ALIASES."""
    return RECEIVE_ALIASES.get(declared_channel_id, {declared_channel_id})
