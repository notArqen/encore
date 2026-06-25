"""
Album artwork lookup via the iTunes Search API, with an in-memory + on-disk
cache so repeated tracks/albums don't trigger a new network request every
time.

This is "Option A" from the design doc: free, no-auth, public API. If a
lookup fails or returns no usable artwork, callers should fall back to the
static Discord Rich Presence asset configured in config.FALLBACK_ARTWORK_ASSET_KEY.
"""

import json
import logging
import os
import threading
import urllib.parse
import urllib.request

import config

logger = logging.getLogger(__name__)

_cache_lock = threading.Lock()
_cache: dict = {}
_cache_loaded = False


def _load_cache() -> None:
    global _cache, _cache_loaded
    if _cache_loaded:
        return
    with _cache_lock:
        if _cache_loaded:
            return
        try:
            os.makedirs(os.path.dirname(config.ARTWORK_CACHE_PATH), exist_ok=True)
            if os.path.exists(config.ARTWORK_CACHE_PATH):
                with open(config.ARTWORK_CACHE_PATH, "r", encoding="utf-8") as f:
                    _cache = json.load(f)
        except Exception:
            logger.exception("Failed to load artwork cache; starting empty")
            _cache = {}
        _cache_loaded = True


def _save_cache() -> None:
    try:
        os.makedirs(os.path.dirname(config.ARTWORK_CACHE_PATH), exist_ok=True)
        with open(config.ARTWORK_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f)
    except Exception:
        logger.exception("Failed to persist artwork cache")


def _cache_key(artist: str, album: str) -> str:
    return f"{artist.strip().lower()}::{album.strip().lower()}"


def _upscale(artwork_url_100: str) -> str:
    """Replace the default 100x100 sizing in an artworkUrl100 with a larger size."""
    return artwork_url_100.replace("100x100", config.ARTWORK_SIZE)


def lookup_artwork_url(artist: str, album: str) -> str | None:
    """
    Look up an album artwork URL via the iTunes Search API.

    Returns None if no match is found, the network call fails, or the
    artist/album are empty -- callers should treat None as "use the fallback
    asset".
    """
    if not artist and not album:
        return None

    _load_cache()
    key = _cache_key(artist, album)

    with _cache_lock:
        if key in _cache:
            return _cache[key] or None

    term = f"{artist} {album}".strip()
    query = urllib.parse.urlencode({
        "term": term,
        "entity": "album",
        "limit": 1,
    })
    url = f"{config.ITUNES_SEARCH_URL}?{query}"

    artwork_url = None
    try:
        with urllib.request.urlopen(url, timeout=6) as response:
            data = json.load(response)
        results = data.get("results") or []
        if results:
            raw_artwork = results[0].get("artworkUrl100")
            if raw_artwork:
                artwork_url = _upscale(raw_artwork)
    except Exception:
        logger.warning("iTunes artwork lookup failed for %r", term, exc_info=True)
        artwork_url = None

    with _cache_lock:
        _cache[key] = artwork_url or ""
        _save_cache()

    return artwork_url
