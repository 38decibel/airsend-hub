"""
Registration (pairing/programming/memorization) endpoint.

After a device has been created via POST /api/devices, the ingress UI calls
POST /api/registration/{key}/command  to send one RF command to the
AirSendWebService on behalf of the newly added device.

Command mapping (mirrors the cloud app's /device/{id}/command/{n} numbering):
  0 = OFF     (STATE 19)
  1 = ON      (STATE 20)
  2 = PROG    (STATE  2)
  3 = STOP    (STATE 17)
  4 = DOWN    (STATE 34)
  5 = UP      (STATE 35)
  6 = TOGGLE  (STATE 18)
  7 = UNPROG  (STATE  3)
 64 = PING    (STATE  1)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web
from core.airsend_client import AirSendClient, AirSendError, BoxConfig
from registry.device_registry import DeviceRegistry

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Command number -> STATE integer value
# ---------------------------------------------------------------------------
_CMD_TO_STATE: dict[int, int] = {
    0: 19,   # OFF
    1: 20,   # ON
    2:  2,   # PROG
    3: 17,   # STOP
    4: 34,   # DOWN
    5: 35,   # UP
    6: 18,   # TOGGLE
    7:  3,   # UNPROG
    64: 1,   # PING
}

_VALID_COMMANDS: frozenset[int] = frozenset(_CMD_TO_STATE)

# Maximum optional duration (ms) accepted from the caller.
_MAX_DURATION_MS: int = 30_000

# Maximum optional seed value (for FLOR install_code).
_MAX_SEED: int = 0xFFFF_FFFF


def _parse_duration(raw: Any) -> int:
    """Parse and validate the optional hold-duration field from a request body.

    Args:
        raw: Raw value from the JSON body.

    Returns:
        Duration in milliseconds.

    Raises:
        web.HTTPBadRequest: When the value is not a valid integer or out of range.
    """
    try:
        duration_ms = int(raw)
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(text="invalid 'duration': must be an integer") from None
    if not (0 < duration_ms <= _MAX_DURATION_MS):
        raise web.HTTPBadRequest(
            text=f"'duration' out of range (1-{_MAX_DURATION_MS} ms)"
        )
    return duration_ms


def _parse_seed(raw: Any) -> int:
    """Parse and validate the optional seed field (used for FLOR install_code).

    Args:
        raw: Raw value from the JSON body.

    Returns:
        Seed integer value.

    Raises:
        web.HTTPBadRequest: When the value is not a valid integer or out of range.
    """
    try:
        seed = int(raw)
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(text="invalid 'seed': must be an integer") from None
    if not (0 <= seed <= _MAX_SEED):
        raise web.HTTPBadRequest(
            text=f"'seed' out of range (0-{_MAX_SEED})"
        )
    return seed


class RegistrationApi:
    """Thin wrapper that exposes the RF command endpoint for device registration."""

    def __init__(
        self,
        boxes_by_slug: dict[str, BoxConfig],
        client: AirSendClient,
        registry: DeviceRegistry,
    ) -> None:
        self._boxes = boxes_by_slug
        self._client = client
        self._registry = registry

        self.router = web.RouteTableDef()
        # Registered manually - see attach_to().
        self._routes: list[tuple[str, str, Any]] = [
            ("POST", "/api/registration/{key}/command", self._handle_command),
        ]

    def attach_to(self, app: web.Application) -> None:
        """Register all routes onto an existing aiohttp Application."""
        for method, path, handler in self._routes:
            app.router.add_route(method, path, handler)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_command(self, request: web.Request) -> web.Response:
        """Handle POST /api/registration/{key}/command.

        Body (JSON):
          {
            "command": <int>,          # required - one of _VALID_COMMANDS
            "duration": <int|null>,    # optional - hold duration in ms
            "seed": <int|null>         # optional - for FLOR install_code
          }
        Returns 200 {"ok": true} on success, 4xx/5xx on error.
        """
        key = request.match_info["key"]
        device = self._registry.get(key)
        if device is None:
            raise web.HTTPNotFound(text=f"unknown device: {key}")

        box = self._boxes.get(device.box)
        if box is None:
            raise web.HTTPBadRequest(text=f"box not configured: {device.box}")

        try:
            body: dict[str, Any] = await request.json()
        except (json.JSONDecodeError, ValueError):
            raise web.HTTPBadRequest(text="invalid JSON body") from None

        # --- command (required) ---
        try:
            cmd = int(body["command"])
        except (KeyError, ValueError, TypeError):
            raise web.HTTPBadRequest(text="missing or invalid 'command'") from None

        if cmd not in _VALID_COMMANDS:
            raise web.HTTPBadRequest(
                text=f"unsupported command: {cmd}. Valid: {sorted(_VALID_COMMANDS)}"
            )

        state_value = _CMD_TO_STATE[cmd]

        # --- optional fields ---
        raw_duration = body.get("duration")
        duration_ms: int | None = _parse_duration(raw_duration) if raw_duration is not None else None

        raw_seed = body.get("seed")
        seed: int | None = _parse_seed(raw_seed) if raw_seed is not None else None

        # --- build AirSendWebService payload ---
        note: dict[str, Any] = {
            "method": 1,   # PUT
            "type": 0,     # STATE
            "value": state_value,
        }
        if duration_ms is not None:
            note["duration"] = duration_ms

        channel: dict[str, Any] = {
            "id": device.channel_id,
            "source": device.channel_source,
        }
        if seed is not None:
            channel["seed"] = seed

        thingnotes: dict[str, Any] = {"notes": [note]}

        try:
            await self._client.transfer(
                box,
                channel=channel,
                thingnotes=thingnotes,
                wait=True,
            )
        except AirSendError as exc:
            _LOGGER.warning(
                "Registration command %d failed for device %s: %s", cmd, key, exc
            )
            raise web.HTTPInternalServerError(
                text=f"RF command failed: {exc}"
            ) from exc

        _LOGGER.info(
            "Registration command %d (STATE %d) sent to device %s (channel_id=%d source=%d)",
            cmd, state_value, key, device.channel_id, device.channel_source,
        )
        return web.json_response({"ok": True})
