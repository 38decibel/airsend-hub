""" Domain `cover` """

from __future__ import annotations

from domains.topics import DeviceTopics, base_discovery_payload

COMPONENT = "cover"

_STATE_UP = 35
_STATE_DOWN = 34
_STATE_STOP = 17

DEFAULT_TRAVEL_TIME_S = 20.0
_MIN_TRAVEL_TIME_S = 1.0
_MAX_TRAVEL_TIME_S = 180.0


def discovery_config(device, topics: DeviceTopics, device_info: dict) -> dict:
    payload = base_discovery_payload(device, COMPONENT, topics, device_info)
    payload.update(
        {
            "command_topic": topics.command,
            "payload_open": "OPEN",
            "payload_close": "CLOSE",
            "payload_stop": "STOP",
        }
    )

    if device.kind == "niveau":
        payload.update(
            {
                "position_topic": topics.position,
                "set_position_topic": topics.set_position,
                "position_open": 100,
                "position_closed": 0,
            }
        )
    else:
        payload["optimistic"] = True

    return payload


def _is_inverted(device) -> bool:
    return bool(device.options.get("invert", False))


def encode_state(device, stype: str, svalue) -> list[tuple[str, str]]:
    topics = DeviceTopics.for_device(COMPONENT, device.key)
    out: list[tuple[str, str]] = []

    if device.kind == "niveau" and stype == "data":
        try:
            raw_byte = int(svalue)
        except (TypeError, ValueError):
            return out
        position = round(max(0, min(255, raw_byte)) / 255 * 100)
        out.append((topics.position, str(position)))
        out.append((topics.state, "open" if position > 0 else "closed"))
        return out

    if device.kind == "volet_roulant":
        if stype == "level":
            out.append((topics.state, "closed" if svalue == 0 else "open"))
        elif stype == "state" and svalue == "stop":
            pass

    return out


def encode_optimistic_state(device, topic: str, payload: str) -> list[tuple[str, str]]:

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

    if topic == topics.command:
        cmd = payload.upper()
        if inverted:
            cmd = {"OPEN": "CLOSE", "CLOSE": "OPEN", "STOP": "STOP"}.get(cmd, cmd)
        value = {"OPEN": _STATE_UP, "CLOSE": _STATE_DOWN, "STOP": _STATE_STOP}.get(cmd)
        if value is None:
            return None
        return {"notes": [{"method": 1, "type": 0, "value": value}]}

    return None


def travel_time_s(device) -> float:

    try:
        value = float(device.options.get("travel_time", DEFAULT_TRAVEL_TIME_S))
    except (TypeError, ValueError):
        return DEFAULT_TRAVEL_TIME_S
    return max(_MIN_TRAVEL_TIME_S, min(_MAX_TRAVEL_TIME_S, value))


def motion_command(device, topic: str, payload: str) -> str | None:
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
