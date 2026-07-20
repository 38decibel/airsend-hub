"""
`event` domain – a fallback for rolling-code remote controls that lack 
reliable position feedback (e.g., a detected button press on a third-party
physical Profalux remote linked to a shutter already managed as a `cover`),
or for any device where the user has explicitly chosen not to control it
based on an inferred state.

HA MQTT `event` component (JSON schema, `state_topic` + `event_types`):
each received frame publishes a timestamped event, never a retained state.
"""

from __future__ import annotations

import json
import time

from domains.topics import DeviceTopics, base_discovery_payload

COMPONENT = "event"

_EVENT_TYPES = ["triggered"]


def discovery_config(device, topics: DeviceTopics, device_info: dict) -> dict:
    payload = base_discovery_payload(device, COMPONENT, topics, device_info)
    payload["event_types"] = device.options.get("event_types", _EVENT_TYPES)
    return payload


def encode_state(device, stype: str, svalue) -> list[tuple[str, str]]:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    body = json.dumps(
        {
            "event_type": "triggered",
            "detail": {"type": stype, "value": svalue},
            "timestamp": time.time(),
        }
    )
    return [(topics.state, body)]


def decode_command(device, topic: str, payload: str) -> dict | None:
    return None
