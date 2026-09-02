"""Domain `cover`."""

from __future__ import annotations

from domains.topics import DeviceTopics, base_discovery_payload

COMPONENT = "cover"

_STATE_UP = 35
_STATE_DOWN = 34
_STATE_STOP = 17

DEFAULT_TRAVEL_TIME_S = 20.0
_MIN_TRAVEL_TIME_S = 1.0
_MAX_TRAVEL_TIME_S = 180.0

_POSITION_OPEN = 100
_POSITION_CLOSED = 0


def _is_inverted(device) -> bool:
    return bool(device.options.get("invert", False))


def _has_travel_time(device) -> bool:
    """Return True when the device has an explicit travel_time option set."""
    return "travel_time" in device.options


def _has_estimated_position(device) -> bool:
    """Return True when the user has opted in to timer-based position tracking.

    For volet_roulant covers, position tracking is only enabled when the
    ``estimated_position`` option is explicitly set to True.  This keeps the
    cover entity in plain optimistic mode (all three buttons always active)
    unless the user consciously enables the feature.
    """
    return bool(device.options.get("estimated_position", False))


def travel_time_s(device) -> float:
    """Return the configured travel time in seconds, clamped to the valid range."""
    try:
        value = float(device.options.get("travel_time", DEFAULT_TRAVEL_TIME_S))
    except (TypeError, ValueError):
        return DEFAULT_TRAVEL_TIME_S
    return max(_MIN_TRAVEL_TIME_S, min(_MAX_TRAVEL_TIME_S, value))


def discovery_config(device, topics: DeviceTopics, device_info: dict) -> dict:
    """Build the MQTT discovery payload for a cover device."""
    payload = base_discovery_payload(device, COMPONENT, topics, device_info)
    payload.update(
        {
            "command_topic": topics.command,
            "payload_open": "OPEN",
            "payload_close": "CLOSE",
            "payload_stop": "STOP",
        }
    )

    if device.kind == "niveau" or (
        device.kind == "volet_roulant" and _has_estimated_position(device)
    ):
        # niveau: native position feedback from the motor.
        # volet_roulant + estimated_position: timer-based position tracking.
        payload.update(
            {
                "position_topic": topics.position,
                "set_position_topic": topics.set_position,
                "position_open": _POSITION_OPEN,
                "position_closed": _POSITION_CLOSED,
            }
        )
    else:
        payload["optimistic"] = True

    return payload


def encode_state(device, stype: str, svalue) -> list[tuple[str, str]]:
    """Convert an incoming RF state into MQTT publish tuples."""
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    out: list[tuple[str, str]] = []
    inverted = _is_inverted(device)

    if device.kind == "niveau" and stype == "data":
        try:
            raw_byte = int(svalue)
        except (TypeError, ValueError):
            return out
        position_raw = round(max(0, min(255, raw_byte)) / 255 * 100)
        # Apply inversion: a motor physically wired in reverse reports the
        # complement of the logical position.
        position = 100 - position_raw if inverted else position_raw
        out.append((topics.position, str(position)))
        out.append((topics.state, "open" if position > 0 else "closed"))
        return out

    if device.kind == "volet_roulant" and stype == "level":
        out.append((topics.state, "closed" if svalue == 0 else "open"))

    return out


def encode_optimistic_state(device, topic: str, payload: str) -> list[tuple[str, str]]:
    """Return optimistic state updates triggered by outbound commands."""
    topics = DeviceTopics.for_device(COMPONENT, device.key)

    if topic == topics.command and device.kind == "volet_roulant":
        cmd = payload.upper()

        if cmd == "OPEN":
            return [(topics.state, "opening")]

        if cmd == "CLOSE":
            return [(topics.state, "closing")]

    if topic == topics.set_position and device.kind == "niveau":
        try:
            position = max(0, min(100, int(payload)))
        except ValueError:
            return []

        return [
            (topics.position, str(position)),
            (topics.state, "open" if position > 0 else "closed"),
        ]

    return []


def decode_command(device, topic: str, payload: str) -> dict | None:
    """Decode an MQTT command into a thingnotes dict.

    For volet_roulant with estimated_position, set_position commands return a
    dict with an extra ``_target_position`` key (int 0-100) alongside ``notes``.
    This key is consumed by mqtt_bridge and never forwarded to the box.
    """
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    inverted = _is_inverted(device)

    if topic == topics.set_position and device.kind == "niveau":
        try:
            position = max(0, min(100, int(payload)))
        except ValueError:
            return None
        raw_position = 100 - position if inverted else position
        raw_byte = round(raw_position / 100 * 255)
        return {"notes": [{"method": 1, "type": 1, "value": raw_byte}]}

    if (
        topic == topics.set_position
        and device.kind == "volet_roulant"
        and _has_estimated_position(device)
    ):
        try:
            target = max(0, min(100, int(payload)))
        except ValueError:
            return None
        # Direction is resolved in mqtt_bridge once current position is known.
        # We embed the target so mqtt_bridge can compute duration and send STOP.
        return {"notes": [], "_target_position": target}

    if topic == topics.command:
        cmd = payload.upper()
        if inverted:
            cmd = {"OPEN": "CLOSE", "CLOSE": "OPEN", "STOP": "STOP"}.get(cmd, cmd)
        value = {"OPEN": _STATE_UP, "CLOSE": _STATE_DOWN, "STOP": _STATE_STOP}.get(cmd)
        if value is None:
            return None
        return {"notes": [{"method": 1, "type": 0, "value": value}]}

    return None


def motion_command(device, topic: str, payload: str) -> str | None:
    """Return the motion state string triggered by an outbound command, or None."""
    if device.kind != "volet_roulant":
        return None

    topics = DeviceTopics.for_device(COMPONENT, device.key)
    if topic != topics.command:
        return None

    cmd = payload.upper()
    if cmd == "OPEN":
        return "opening"
    if cmd == "CLOSE":
        return "closing"
    if cmd == "STOP":
        return "stop"
    return None
