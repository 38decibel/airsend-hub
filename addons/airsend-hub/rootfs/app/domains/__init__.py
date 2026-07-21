"""Registry of available domain modules, indexed by device.domain"""

from __future__ import annotations

from types import ModuleType

from domains import binary_sensor, button, cover, event, sensor, switch

REGISTRY: dict[str, ModuleType] = {
    "cover": cover,
    "switch": switch,
    "button": button,
    "sensor": sensor,
    "binary_sensor": binary_sensor,
    "event": event,
}


def get_domain_module(domain: str) -> ModuleType | None:
    return REGISTRY.get(domain)
