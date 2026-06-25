"""
Configuration for the Apple Music -> Discord Rich Presence helper.

Don't hand-edit DISCORD_CLIENT_ID / FALLBACK_ARTWORK_ASSET_KEY / ACTIVITY_NAME
below unless you want to -- running `python3 setup.py` will configure these
for you interactively.
"""

import os

# --- Discord Application settings ---
# From https://discord.com/developers/applications -> your app -> General Information
DISCORD_CLIENT_ID = "YOUR_DISCORD_CLIENT_ID_HERE"

# Asset key uploaded under Rich Presence -> Art Assets in the Discord Developer
# Portal. Used as the large_image when no iTunes artwork match is found.
FALLBACK_ARTWORK_ASSET_KEY = "logo"

# No small badge icon is overlaid on the album art (the small_image/
# small_text fields are simply left unset) -- this keeps the art clean.

# Sent as the activity's "name" field. With activity_type=LISTENING, Discord
# renders the header as "Listening to {ACTIVITY_NAME}" (the app name from
# the Developer Portal is NOT used for this -- it's overridden by this value).
ACTIVITY_NAME = "Apple Music"

# --- Bundle identifiers ---
MUSIC_BUNDLE_ID = "com.apple.Music"

# --- Behavior tuning ---
# Fallback resync interval in seconds. This is a correctness safety net for
# missed `com.apple.Music.playerInfo` notifications, NOT the primary update
# mechanism (which is event-driven). Keep this well above a few seconds.
RESYNC_INTERVAL_SECONDS = 45

# How often to retry connecting to the local Discord IPC socket if Discord
# isn't running yet / isn't reachable.
DISCORD_RECONNECT_INTERVAL_SECONDS = 15

# --- Artwork lookup / cache ---
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
ARTWORK_SIZE = "600x600"  # replaces the default 100x100 in artworkUrl100

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ARTWORK_CACHE_PATH = os.path.join(_THIS_DIR, "cache", "artwork_cache.json")

# --- Logging ---
LOG_LEVEL = "INFO"
LOG_THE_FULL_PLAYERINFO_PAYLOAD_ONCE = True
