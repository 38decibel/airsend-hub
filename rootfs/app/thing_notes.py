"""
Decoding `thingnotes.notes[]` from a ThingEvent into (derived_type, value).

note.type (integer; see AirSendWebService.yaml ThingNotes.notes[].type):
0 = STATE, 1 = DATA, 2 = TEMPERATURE, 3 = ILLUMINANCE, 4 = R_HUMIDITY, 9 = LEVEL

note.value when type == STATE; integer values ​​encountered in practice:
17=STOP 18=TOGGLE 19=OFF 20=ON 21=CLOSE 22=OPEN 33=MIDDLE 34=DOWN 35=UP
36=LEFT 37=RIGHT 38=USERPOSITION
"""

from __future__ import annotations

_STATE_ENUM_TO_INT = {
    "PING": 1,
    "PROG": 2,
    "UNPROG": 3,
    "RESET": 4,
    "STOP": 17,
    "TOGGLE": 18,
    "OFF": 19,
    "ON": 20,
    "CLOSE": 21,
    "OPEN": 22,
    "MIDDLE": 33,
    "DOWN": 34,
    "UP": 35,
    "LEFT": 36,
    "RIGHT": 37,
    "USERPOSITION": 38,
}


def _as_int_state_value(raw_value) -> int | None:
    if isinstance(raw_value, (int, float)):
        return int(raw_value)
    if isinstance(raw_value, str):
        if raw_value.isdigit():
            return int(raw_value)
        return _STATE_ENUM_TO_INT.get(raw_value)
    return None


def _decode_state_note(raw_value) -> tuple[str, object] | None:
    """Decode a STATE note (type 0) into (stype, svalue)."""
    ivalue = _as_int_state_value(raw_value)
    if ivalue is None:
        return None
    if ivalue == 18:
        return "toggle", "pressed"
    if ivalue in (19, 34):
        return "level", 0
    if ivalue in (20, 35):
        return "level", 100
    if ivalue == 17:
        return "state", "stop"
    if ivalue in (33, 38):
        return "state", "user"
    return "state", ivalue


def _decode_temperature_note(raw_value) -> tuple[str, float] | None:
    """Decode a TEMPERATURE note (type 2): Kelvins -> Celsius."""
    try:
        return "temperature", round((float(raw_value) - 273.15) * 10.0) / 10.0
    except (TypeError, ValueError):
        return None


def _decode_illuminance_note(raw_value) -> tuple[str, float] | None:
    """Decode an ILLUMINANCE note (type 3)."""
    try:
        return "illuminance", float(raw_value)
    except (TypeError, ValueError):
        return None


def _decode_r_humidity_note(raw_value) -> tuple[str, int] | None:
    """Decode a R_HUMIDITY note (type 4)."""
    try:
        return "r_humidity", int(raw_value)
    except (TypeError, ValueError):
        return None


def _decode_level_note(raw_value) -> tuple[str, int] | None:
    """Decode a LEVEL note (type 9)."""
    try:
        return "level", int(raw_value)
    except (TypeError, ValueError):
        return None


def _decode_data_note(raw_value) -> tuple[str, object]:
    """Decode a DATA note (type 1): pass through as-is."""
    return "data", raw_value


_NOTE_DECODERS = {
    0: _decode_state_note,
    1: _decode_data_note,
    2: _decode_temperature_note,
    3: _decode_illuminance_note,
    4: _decode_r_humidity_note,
    9: _decode_level_note,
}


def convert_notes_to_states(notes: list[dict]) -> list[tuple[str, object]]:
    """
    Returns a list of (stype, svalue) pairs that can be used by the domains/* modules.

    stype in {"toggle", "level", "state", "data", "temperature", "illuminance",
              "r_humidity"}
    """
    results: list[tuple[str, object]] = []
    if not notes:
        return results

    for note in notes:
        note_type = note.get("type")
        raw_value = note.get("value")
        decoder = _NOTE_DECODERS.get(note_type)
        if decoder is not None:
            result = decoder(raw_value)
            if result is not None:
                results.append(result)

    return results
