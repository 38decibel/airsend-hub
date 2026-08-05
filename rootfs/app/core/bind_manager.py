"""
RF "bind" lifecycle per box.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from runtime_settings import RuntimeSettings

from core.airsend_client import AirSendClient, AirSendError, BoxConfig

_LOGGER = logging.getLogger("airsend.bind_manager")

_RENEW_MARGIN_S = 60.0


class BoxBindHandle:

    def __init__(
        self, client: AirSendClient, box: BoxConfig, callback_base_url: str, settings: RuntimeSettings
    ) -> None:
        self._client = client
        self.box = box
        self._callback_url = f"{callback_base_url.rstrip('/')}/cb/{box.slug}"
        self._settings = settings
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    @property
    def callback_url(self) -> str:
        return self._callback_url

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(), name=f"bind-{self.box.slug}")

    async def stop(self) -> None:
        self._stopped.set()

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        try:
            await self._client.unbind(self.box)
        except AirSendError as exc:
            _LOGGER.debug(
                "unbind failed for box %s (probably already unbound): %s",
                self.box.name,
                exc,
            )

    async def restart(self) -> None:
        """Stop the current bind loop and immediately start a new one.

        Used when settings that affect the bind parameters (e.g. bind_channel_id)
        change at runtime, so the new channel takes effect without waiting for
        the next scheduled renewal.
        """
        _LOGGER.info(
            "Restarting bind for box '%s' (bind_channel_id=%s)",
            self.box.name,
            self._settings.bind_channel_id,
        )
        await self.stop()
        self.start()

    async def start_targeted_listen(self, channel_id: int | None, duration: float) -> None:

        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        try:
            await self._client.bind(
                self.box,
                callback_url=self._callback_url,
                duration=duration,
                channel={"id": channel_id} if channel_id is not None else None,
            )
            await asyncio.sleep(duration)
        finally:
            self.start()

    async def _run(self) -> None:
        backoff = 5.0
        while not self._stopped.is_set():
            duration = self._settings.bind_duration_s
            channel_id = self._settings.bind_channel_id
            channel = {"id": channel_id} if channel_id is not None else None
            try:
                _LOGGER.info(
                    "Binding box '%s' (callback=%s, duration=%ss, channel=%s)",
                    self.box.name,
                    self._callback_url,
                    duration,
                    channel_id if channel_id is not None else "all",
                )
                await self._client.bind(
                    self.box,
                    callback_url=self._callback_url,
                    duration=duration,
                    channel=channel,
                )
                backoff = 5.0
                sleep_for = max(duration - _RENEW_MARGIN_S, 5.0)
                await asyncio.sleep(sleep_for)
            except asyncio.CancelledError:
                raise
            except AirSendError as exc:
                _LOGGER.warning(
                    "Bind failed for box '%s' (%s) - retrying in %.0fs",
                    self.box.name,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300.0)


class BindManager:

    def __init__(self, client: AirSendClient, callback_base_url: str, settings: RuntimeSettings) -> None:
        self._client = client
        self._callback_base_url = callback_base_url
        self._settings = settings
        self._handles: dict[str, BoxBindHandle] = {}

    def add_box(self, box: BoxConfig) -> BoxBindHandle:
        handle = BoxBindHandle(self._client, box, self._callback_base_url, self._settings)
        self._handles[box.slug] = handle
        handle.start()
        return handle

    def get_handle(self, box_slug: str) -> BoxBindHandle | None:
        return self._handles.get(box_slug)

    async def restart_all(self) -> None:
        """Restart the bind loop on every box (e.g. after a channel change)."""
        await asyncio.gather(
            *(h.restart() for h in self._handles.values()),
            return_exceptions=True,
        )

    async def stop_all(self) -> None:
        await asyncio.gather(*(h.stop() for h in self._handles.values()), return_exceptions=True)
