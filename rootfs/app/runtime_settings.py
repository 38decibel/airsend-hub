"""
Settings adjustable from HA.
"""

from __future__ import annotations


class RuntimeSettings:
    def __init__(self) -> None:
        self.bind_duration_s: float = 3600.0
        self.capture_unknown_events: bool = False

    RELIABILITY_MIN = 6
    RELIABILITY_MAX = 71

