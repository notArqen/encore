"""
AppleScript / osascript helpers for querying Music.app directly.

These are used for:
  - checking whether Music.app is running at all (cheap, no AppleScript needed)
  - fetching the full current-track state on startup (in case our helper
    launches after Music.app already is)
  - the periodic fallback resync, to correct any drift if a
    `com.apple.Music.playerInfo` distributed notification was missed

This module intentionally avoids any polling loop itself -- it just exposes
functions that main.py calls on-demand (at startup, on notification, or from
the low-frequency resync timer).
"""

import logging
import subprocess

from AppKit import NSWorkspace

import config

logger = logging.getLogger(__name__)

# Single AppleScript call that grabs everything we need in one round trip.
# Returns a "|"-delimited line so we don't need a JSON bridge inside
# AppleScript itself. Missing/inapplicable fields come back as empty string.
_NOW_PLAYING_SCRIPT = '''
tell application "Music"
    if not running then
        return "STOPPED||||||0|0"
    end if
    set ps to player state as string
    if ps is "playing" or ps is "paused" then
        try
            set trackName to name of current track
        on error
            set trackName to ""
        end try
        try
            set artistName to artist of current track
        on error
            set artistName to ""
        end try
        try
            set albumName to album of current track
        on error
            set albumName to ""
        end try
        try
            set trackDuration to duration of current track
        on error
            set trackDuration to 0
        end try
        try
            set playerPos to player position
        on error
            set playerPos to 0
        end try
        return ps & "|" & trackName & "|" & artistName & "|" & albumName & "|" & trackDuration & "|" & playerPos
    else
        return ps & "||||0|0"
    end if
end tell
'''


def is_music_running() -> bool:
    """
    Cheap check for whether Music.app is currently running.

    Uses NSWorkspace's list of running applications rather than AppleScript's
    `System Events ... exists process`, which requires granting Accessibility
    permission to osascript. This check needs no special permission at all.
    """
    try:
        for app in NSWorkspace.sharedWorkspace().runningApplications():
            if app.bundleIdentifier() == config.MUSIC_BUNDLE_ID:
                return True
        return False
    except Exception:
        logger.exception("Failed to check whether Music.app is running")
        return False


def get_now_playing() -> dict:
    """
    Query Music.app directly for its current state.

    Returns a dict shaped like:
        {
            "state": "Playing" | "Paused" | "Stopped",
            "name": str,
            "artist": str,
            "album": str,
            "duration": float,   # seconds
            "position": float,   # seconds, current playback position
        }

    If Music.app isn't running or a field is unavailable, that field comes
    back empty/zero rather than raising.
    """
    default = {
        "state": "Stopped",
        "name": "",
        "artist": "",
        "album": "",
        "duration": 0.0,
        "position": 0.0,
    }
    try:
        result = subprocess.run(
            ["osascript", "-e", _NOW_PLAYING_SCRIPT],
            capture_output=True,
            text=True,
            timeout=5,
        )
        raw = result.stdout.strip()
        if not raw:
            return default

        parts = raw.split("|")
        if len(parts) < 6:
            logger.warning("Unexpected AppleScript output: %r", raw)
            return default

        state_raw, name, artist, album, duration_raw, position_raw = parts[:6]

        def _to_float(value, fallback=0.0):
            try:
                return float(value)
            except ValueError:
                return fallback

        return {
            "state": state_raw.capitalize() if state_raw else "Stopped",
            "name": name,
            "artist": artist,
            "album": album,
            "duration": _to_float(duration_raw),
            "position": _to_float(position_raw),
        }
    except Exception:
        logger.exception("Failed to query Music.app now-playing state")
        return default
