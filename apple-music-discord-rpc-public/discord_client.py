"""
Thin wrapper around pypresence for talking to the local Discord client over
its IPC socket.

Handles the case where Discord isn't running yet (or got closed) by retrying
the connection periodically rather than crashing -- the user may well open
Music.app before Discord.
"""

import logging
import threading
import time

from pypresence import Presence
from pypresence.exceptions import DiscordNotFound, PipeClosed
from pypresence.types import ActivityType

import config

logger = logging.getLogger(__name__)


class DiscordClient:
    def __init__(self, client_id: str = config.DISCORD_CLIENT_ID):
        self._client_id = client_id
        self._rpc: Presence | None = None
        self._connected = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._reconnect_thread: threading.Thread | None = None

    # -- connection lifecycle -------------------------------------------------

    def start(self) -> None:
        """Attempt an initial connection and kick off the reconnect watchdog."""
        self._try_connect()
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop, daemon=True
        )
        self._reconnect_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._disconnect_locked()

    def _try_connect(self) -> bool:
        with self._lock:
            if self._connected:
                return True
            try:
                rpc = Presence(self._client_id)
                rpc.connect()
                self._rpc = rpc
                self._connected = True
                logger.info("Connected to Discord IPC")
                return True
            except (DiscordNotFound, FileNotFoundError, ConnectionRefusedError):
                self._rpc = None
                self._connected = False
                return False
            except Exception:
                logger.exception("Unexpected error connecting to Discord")
                self._rpc = None
                self._connected = False
                return False

    def _disconnect_locked(self) -> None:
        if self._rpc is not None:
            try:
                self._rpc.close()
            except Exception:
                pass
        self._rpc = None
        self._connected = False

    def _reconnect_loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._connected:
                if self._try_connect():
                    logger.info("Discord connection (re)established")
            self._stop_event.wait(config.DISCORD_RECONNECT_INTERVAL_SECONDS)

    # -- presence updates -------------------------------------------------

    def update(
        self,
        details: str,
        state: str,
        large_image: str,
        large_text: str | None = None,
        start: float | None = None,
        name: str | None = None,
    ) -> None:
        if not self._connected:
            # Drop silently -- the reconnect loop will pick things back up,
            # and the next event/resync will push a fresh update once
            # reconnected.
            return
        with self._lock:
            if self._rpc is None:
                return
            try:
                kwargs = dict(
                    activity_type=ActivityType.LISTENING,
                    details=details,
                    state=state,
                    large_image=large_image,
                    large_text=large_text,
                )
                if name:
                    kwargs["name"] = name
                if start is not None:
                    kwargs["start"] = int(start)
                self._rpc.update(**kwargs)
            except (PipeClosed, BrokenPipeError, OSError):
                logger.warning("Discord pipe closed; will attempt to reconnect")
                self._disconnect_locked()
            except Exception:
                logger.exception("Failed to update Discord presence")
                self._disconnect_locked()

    def clear(self) -> None:
        if not self._connected:
            return
        with self._lock:
            if self._rpc is None:
                return
            try:
                self._rpc.clear()
            except (PipeClosed, BrokenPipeError, OSError):
                logger.warning("Discord pipe closed while clearing; will reconnect")
                self._disconnect_locked()
            except Exception:
                logger.exception("Failed to clear Discord presence")
                self._disconnect_locked()
