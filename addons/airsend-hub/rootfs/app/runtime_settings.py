"""
Old settings adjustable from HA (MQTT "number" entities, config category),
shared by reference between callback_server.py and mqtt_bridge.py.

Deliberately a simple mutable object rather than an immutable value: the
change must take effect immediately on the next received frame,
without restarting the app.
"""

from __future__ import annotations


class RuntimeSettings:
    def __init__(self) -> None:
        self.bind_duration_s: float = 3600.0

    RELIABILITY_MIN = 6
    RELIABILITY_MAX = 71
