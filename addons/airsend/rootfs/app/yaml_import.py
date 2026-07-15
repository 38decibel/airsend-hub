"""
YAML import parsing for airsend-addon-dev.

Converts a legacy hass_airsend integration YAML config (devices: {...})
into devices.json-shaped preview rows, to be reviewed/edited by the user
before being committed via InclusionApi._create_device.

Design constraints (see project memory / prior discussion):
- `type` is always 4098 on real devices in this YAML, never a domain
  classifier -> ignored entirely.
- domain/kind CANNOT be inferred from protocol_name alone (the same
  channel_id has produced both "cover" and "switch" devices in practice)
  -> for genuinely new devices, left blank, user must choose.
- For devices that already exist (conflict on channel_id+channel_source),
  kind/domain are carried over from the existing device - NOT re-derived
  from protocol, since that's exactly the info we already have and trust.
- domain/kind CANNOT be inferred from `type` (4096-4099) either: real exports
  show every device (shutters AND an on/off light) sharing type 4098, since
  the AirSendWebService has no dedicated "Light" type - confirmed against
  the user's actual cloud exports. `type` reflects the RF command set
  available (open/close/stop), not the intended HA domain, so it's ignored
  entirely here, same as `channel_id`/protocol.
- kind_aliases exists only as a defensive hook for translating an old kind
  vocabulary into the current one, should one ever surface; no such
  mismatch is currently known to exist (an earlier suspected case,
  "interrupteur", turned out to be a documentation slip, not real data).
"""
import json
import re
import unicodedata

import yaml


class _IgnoreSecretLoader(yaml.SafeLoader):
    """Tolerates HA's `!secret xxx` tag (returns a placeholder). We never
    need the actual secret value for import purposes, only the structure."""
    pass


def _construct_secret(loader, node):
    return "__secret_ignored__"


_IgnoreSecretLoader.add_constructor("!secret", _construct_secret)


def load_yaml_devices(yaml_text):
    """Parses the legacy hass_airsend YAML and returns the dict under the
    top-level 'devices:' key. Raises ValueError with a clear message on
    malformed input."""
    try:
        parsed = yaml.load(yaml_text, Loader=_IgnoreSecretLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML parsing failed: {exc}") from exc

    if not isinstance(parsed, dict) or "devices" not in parsed:
        raise ValueError("Expected a top-level 'devices:' key, none found")

    devices = parsed["devices"]
    if not isinstance(devices, dict):
        raise ValueError("'devices:' must be a mapping of name -> config")

    return devices


def load_channel_name_map(channels_json_path):
    """Convenience for standalone/offline use (tests, scripts) - not used
    by the live integration, which sources protocol names from
    ProtocolCatalog instead (single source of truth with the rest of the
    addon)."""
    with open(channels_json_path, encoding="utf-8") as f:
        channels = json.load(f)
    return {c["id"]: c["name"] for c in channels}


def slugify(name):
    """'Volet cuisine fenêtre' -> 'volet_cuisine_fenetre'"""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_only = ascii_only.lower()
    ascii_only = re.sub(r"[^a-z0-9]+", "_", ascii_only)
    return ascii_only.strip("_")


def parse_airsend_yaml(
    yaml_devices,
    protocol_name_for,
    existing_devices,
    box_slug,
    kind_to_domain,
    kind_aliases=None,
):
    """
    yaml_devices: dict under 'devices:', from load_yaml_devices()
    protocol_name_for: callable(channel_id) -> str | None
    existing_devices: {key: {"channel_id", "channel_source", "domain",
                              "kind", "options"}} - typically built from
                       DeviceRegistry.all()
    box_slug: box to attribute newly-created devices to
    kind_to_domain: the addon's canonical {kind: domain} map (passed in
                    rather than imported, to avoid a circular import with
                    inclusion_api.py)
    kind_aliases: {old_kind: new_kind}, applied to kinds carried over from
                  existing_devices before domain lookup

    Returns a list of preview rows. Nothing is written/created here.
    """
    kind_aliases = kind_aliases or {}
    rows = []

    for friendly_name, entry in yaml_devices.items():
        channel = entry.get("channel")
        if channel is None:
            # Gateway/box entry itself (type: 0), not a device.
            continue

        channel_id = channel.get("id")
        channel_source = channel.get("source")
        protocol_name = protocol_name_for(channel_id)

        key = slugify(friendly_name)

        conflict_key = None
        for existing_key, existing_val in existing_devices.items():
            if (
                existing_val.get("channel_id") == channel_id
                and existing_val.get("channel_source") == channel_source
            ):
                conflict_key = existing_key
                break

        kind_translated = False
        if conflict_key:
            status = "conflict"
            existing_val = existing_devices[conflict_key]
            raw_kind = existing_val.get("kind")
            kind = kind_aliases.get(raw_kind, raw_kind)
            kind_translated = kind != raw_kind
            domain = kind_to_domain.get(kind, existing_val.get("domain"))
            options = existing_val.get("options") or {"invert": False}
        elif protocol_name is None:
            status = "unknown_protocol"
            protocol_name = "UNKNOWN"
            kind, domain, options = None, None, {"invert": False}
        else:
            status = "new"
            kind, domain, options = None, None, {"invert": False}

        rows.append({
            "key": key,
            "friendly_name": friendly_name,
            "box": box_slug,
            "channel_id": channel_id,
            "channel_source": channel_source,
            "protocol_name": protocol_name,
            "domain": domain,
            "kind": kind,
            "kind_translated": kind_translated,
            "options": options,
            "status": status,
            "conflict_with": conflict_key,
        })

    return rows
