"""
Native backup/restore for the addon's own device registry (devices.json).
"""

from __future__ import annotations

import time
from typing import Any

BACKUP_SCHEMA_VERSION = 1

_DEVICE_FIELDS = (
    "box",
    "channel_id",
    "channel_source",
    "protocol_name",
    "kind",
    "domain",
    "friendly_name",
    "options",
    "source_of_creation",
)

_DEFAULT_ACTION_BY_STATUS = {
    "new": "import",
    "identical": "skip",
    "conflict": "skip",
    "unknown_box": "skip",
    "invalid_kind": "skip",
}


def build_backup(devices: list[Any]) -> dict[str, Any]:
    payload = {device.key: {f: getattr(device, f) for f in _DEVICE_FIELDS} for device in devices}
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "exported_at": int(time.time()),
        "devices": payload,
    }


def parse_backup(raw: Any) -> dict[str, dict]:
    if not isinstance(raw, dict):
        raise TypeError("backup must be a JSON object")
    if raw.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {raw.get('schema_version')!r}")

    devices = raw.get("devices")
    if not isinstance(devices, dict):
        raise TypeError("expected a 'devices' object")

    for key, fields in devices.items():
        if not isinstance(fields, dict):
            raise TypeError(f"{key}: device entry must be an object")
        missing = [f for f in _DEVICE_FIELDS if f not in fields]
        if missing:
            raise ValueError(f"{key}: missing field(s) {', '.join(missing)}")

    return devices


def _same_device(a: dict, b: dict) -> bool:
    return all(a.get(f) == b.get(f) for f in _DEVICE_FIELDS)


def _row_status(fields: dict, key: str, existing_devices: dict, known_boxes: set, known_kinds: set) -> str:
    if fields.get("kind") not in known_kinds:
        return "invalid_kind"
    if fields.get("box") not in known_boxes:
        return "unknown_box"
    if key not in existing_devices:
        return "new"
    if _same_device(fields, existing_devices[key]):
        return "identical"
    return "conflict"


def diff_backup_devices(
    backup_devices: dict[str, dict],
    existing_devices: dict[str, dict],
    known_boxes: set[str],
    known_kinds: set[str],
) -> list[dict]:
    rows = []
    for key, fields in backup_devices.items():
        status = _row_status(fields, key, existing_devices, known_boxes, known_kinds)
        row = {"key": key, "status": status, "action": _DEFAULT_ACTION_BY_STATUS[status]}
        row.update({f: fields.get(f) for f in _DEVICE_FIELDS})
        rows.append(row)
    return rows
