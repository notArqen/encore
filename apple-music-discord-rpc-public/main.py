"""
Apple Music -> Discord Rich Presence helper.

Event-driven by design (no polling loop as the primary mechanism):

  - NSWorkspace notifications tell us when Music.app launches/quits.
  - NSDistributedNotificationCenter delivers `com.apple.Music.playerInfo`
    whenever the track changes or playback state changes.
  - A low-frequency (30-60s) AppleScript resync runs ONLY as a correctness
    safety net for the documented unreliability of that notification on some
    macOS versions -- it is not the primary update path.

Run with: python3 main.py
Stop with Ctrl-C.
"""

import logging
import sys
import time

from AppKit import NSWorkspace, NSWorkspaceDidLaunchApplicationNotification, \
    NSWorkspaceDidTerminateApplicationNotification
from Foundation import (
    NSDistributedNotificationCenter,
    NSObject,
    NSRunLoop,
    NSTimer,
    NSDate,
)
from PyObjCTools import AppHelper

import config
import music_query
import artwork
from discord_client import DiscordClient

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

discord = DiscordClient()

# Tracks whether we've logged the raw playerInfo payload once, per the spec's
# request to verify the exact key names empirically.
_logged_payload_once = False

# Remembers the last state we pushed to Discord so the resync safety net can
# tell "drifted" apart from "unchanged" and avoid redundant RPC calls.
_last_pushed_signature = None
_last_start_epoch = None


def _signature_for(name, artist, album, state):
    return (name, artist, album, state)


def _push_presence(name: str, artist: str, album: str, state: str,
                    position_seconds: float = 0.0) -> None:
    """Build and send (or clear) the Discord Rich Presence for the given state."""
    global _last_pushed_signature, _last_start_epoch

    state_norm = (state or "").strip().lower()

    if state_norm == "stopped" or not name:
        if _last_pushed_signature is not None:
            logger.info("Music stopped/no track -> clearing Discord presence")
            discord.clear()
        _last_pushed_signature = None
        _last_start_epoch = None
        return

    signature = _signature_for(name, artist, album, state_norm)
    if signature == _last_pushed_signature:
        return  # nothing changed, skip a redundant RPC call

    track_changed = (
        _last_pushed_signature is None
        or _last_pushed_signature[:3] != signature[:3]
    )
    if track_changed or _last_start_epoch is None:
        _last_start_epoch = time.time() - max(position_seconds, 0.0)

    image_url = artwork.lookup_artwork_url(artist, album)
    large_image = image_url or config.FALLBACK_ARTWORK_ASSET_KEY

    logger.info("Updating Discord presence: %s - %s (%s) [%s]",
                name, artist, album, state_norm)

    # Only two text lines are available on a standard Discord Rich Presence
    # card (details + state) -- album isn't shown as a third line, but it
    # does show as a tooltip when hovering the album art (large_text).
    discord.update(
        details=name,
        state=f"by {artist}" if artist else "Apple Music",
        large_image=large_image,
        large_text=album or "Apple Music",
        start=_last_start_epoch if state_norm == "playing" else None,
        name=config.ACTIVITY_NAME,
    )

    _last_pushed_signature = signature


def _sync_from_applescript(reason: str) -> None:
    """Query Music.app directly and push whatever it reports."""
    info = music_query.get_now_playing()
    logger.debug("[%s] AppleScript now-playing: %s", reason, info)
    _push_presence(
        name=info["name"],
        artist=info["artist"],
        album=info["album"],
        state=info["state"],
        position_seconds=info.get("position", 0.0),
    )


# --------------------------------------------------------------------------
# NSDistributedNotificationCenter: com.apple.Music.playerInfo
# --------------------------------------------------------------------------

class PlayerInfoListener(NSObject):
    def handlePlayerInfo_(self, notification):
        global _logged_payload_once
        try:
            user_info = notification.userInfo()
            if config.LOG_THE_FULL_PLAYERINFO_PAYLOAD_ONCE and not _logged_payload_once:
                logger.info("Full playerInfo userInfo payload (first time seen): %r",
                            dict(user_info) if user_info else {})
                _logged_payload_once = True

            if user_info is None:
                logger.warning("playerInfo notification with no userInfo; falling back to AppleScript")
                _sync_from_applescript("playerInfo-empty")
                return

            name = user_info.get("Name", "") or ""
            artist = user_info.get("Artist", "") or ""
            album = user_info.get("Album", "") or ""
            player_state = user_info.get("Player State", "") or "Stopped"

            # The notification payload doesn't reliably include current
            # playback position, so for the elapsed-time counter we accept a
            # small inaccuracy on resume rather than querying AppleScript on
            # every single notification (that would reintroduce a sync call
            # per event, which is fine occasionally but unnecessary here).
            _push_presence(name=name, artist=artist, album=album, state=player_state)
        except Exception:
            logger.exception("Error handling playerInfo notification; falling back to AppleScript")
            _sync_from_applescript("playerInfo-exception")


_player_info_listener = PlayerInfoListener.alloc().init()


def _register_player_info_listener() -> None:
    center = NSDistributedNotificationCenter.defaultCenter()
    center.addObserver_selector_name_object_(
        _player_info_listener,
        "handlePlayerInfo:",
        "com.apple.Music.playerInfo",
        None,
    )
    logger.info("Subscribed to com.apple.Music.playerInfo")


def _unregister_player_info_listener() -> None:
    center = NSDistributedNotificationCenter.defaultCenter()
    center.removeObserver_name_object_(
        _player_info_listener, "com.apple.Music.playerInfo", None
    )
    logger.info("Unsubscribed from com.apple.Music.playerInfo")


# --------------------------------------------------------------------------
# NSWorkspace: app launch / terminate
# --------------------------------------------------------------------------

class WorkspaceListener(NSObject):
    def appLaunched_(self, notification):
        app = notification.userInfo().get("NSWorkspaceApplicationKey")
        bundle_id = app.bundleIdentifier() if app else None
        if bundle_id == config.MUSIC_BUNDLE_ID:
            logger.info("Music.app launched -> starting presence tracking")
            _on_music_launched()

    def appTerminated_(self, notification):
        app = notification.userInfo().get("NSWorkspaceApplicationKey")
        bundle_id = app.bundleIdentifier() if app else None
        if bundle_id == config.MUSIC_BUNDLE_ID:
            logger.info("Music.app quit -> clearing presence, going idle")
            _on_music_terminated()


_workspace_listener = WorkspaceListener.alloc().init()
_resync_timer = None


def _on_music_launched() -> None:
    _register_player_info_listener()
    _sync_from_applescript("launch")
    _start_resync_timer()


def _on_music_terminated() -> None:
    _unregister_player_info_listener()
    _stop_resync_timer()
    global _last_pushed_signature, _last_start_epoch
    discord.clear()
    _last_pushed_signature = None
    _last_start_epoch = None


def _resync_tick(timer) -> None:
    _sync_from_applescript("resync")


def _start_resync_timer() -> None:
    global _resync_timer
    if _resync_timer is not None:
        return
    _resync_timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
        config.RESYNC_INTERVAL_SECONDS, True, _resync_tick
    )
    logger.info("Started fallback resync timer (every %ss)", config.RESYNC_INTERVAL_SECONDS)


def _stop_resync_timer() -> None:
    global _resync_timer
    if _resync_timer is not None:
        _resync_timer.invalidate()
        _resync_timer = None
        logger.info("Stopped fallback resync timer")


def _register_workspace_listeners() -> None:
    nc = NSWorkspace.sharedWorkspace().notificationCenter()
    nc.addObserver_selector_name_object_(
        _workspace_listener,
        "appLaunched:",
        NSWorkspaceDidLaunchApplicationNotification,
        None,
    )
    nc.addObserver_selector_name_object_(
        _workspace_listener,
        "appTerminated:",
        NSWorkspaceDidTerminateApplicationNotification,
        None,
    )
    logger.info("Subscribed to NSWorkspace launch/terminate notifications")


def main() -> None:
    logger.info("Apple Music -> Discord RPC helper starting up")
    discord.start()
    _register_workspace_listeners()

    # Initial-state check: our helper may start after Music.app already is
    # running (e.g. on login, or if launched manually while music is playing).
    if music_query.is_music_running():
        logger.info("Music.app already running at startup -> syncing immediately")
        _on_music_launched()
    else:
        logger.info("Music.app not running -> idling until launch notification")

    try:
        AppHelper.runConsoleEventLoop(installInterrupt=True)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down")
        _stop_resync_timer()
        _unregister_player_info_listener()
        discord.stop()


if __name__ == "__main__":
    main()
