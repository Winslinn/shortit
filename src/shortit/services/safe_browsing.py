import hashlib
import json
import math
import os
import threading
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException

SAFE_BROWSING_URL = "https://safebrowsing.googleapis.com/v5/urls:search"
SAFE_BROWSING_TIMEOUT_SECONDS = 5
SAFE_BROWSING_CACHE_MAX_ENTRIES = 2048

_cache: dict[str, tuple[float, bool]] = {}
_cache_lock = threading.Lock()

def check_url_safety(url: str) -> None:
    """Raise if Safe Browsing flags the URL or the check cannot be completed."""
    api_key = os.getenv("SAFE_BROWSING_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Link safety checks are not configured.",
        )

    cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and cached[0] > now:
            if cached[1]:
                raise HTTPException(
                    status_code=400,
                    detail="This URL may be unsafe and cannot be shortened.",
                )
            return
        if cached:
            del _cache[cache_key]

    query = urlencode({"key": api_key, "urls": url})
    request = Request(
        f"{SAFE_BROWSING_URL}?{query}",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=SAFE_BROWSING_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read())
    except (OSError, TimeoutError, URLError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Link safety checks are temporarily unavailable.",
        ) from exc

    if not isinstance(result, dict) or not isinstance(result.get("threats"), list):
        raise HTTPException(
            status_code=503,
            detail="Link safety checks are temporarily unavailable.",
        )

    cache_duration = result.get("cacheDuration")
    try:
        if not isinstance(cache_duration, str) or not cache_duration.endswith("s"):
            raise ValueError("Invalid Safe Browsing cache duration")
        duration_seconds = float(cache_duration[:-1])
        if not math.isfinite(duration_seconds) or duration_seconds < 0:
            raise ValueError("Invalid Safe Browsing cache duration")
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="Link safety checks are temporarily unavailable.",
        ) from exc

    is_threat = bool(result["threats"])
    if duration_seconds > 0:
        with _cache_lock:
            now = time.monotonic()
            expired = [
                key for key, (expires_at, _) in _cache.items()
                if expires_at <= now
            ]
            for key in expired:
                del _cache[key]
            if len(_cache) >= SAFE_BROWSING_CACHE_MAX_ENTRIES:
                oldest_key = next(iter(_cache))
                del _cache[oldest_key]
            _cache[cache_key] = (now + duration_seconds, is_threat)

    if is_threat:
        raise HTTPException(
            status_code=400,
            detail="This URL may be unsafe and cannot be shortened.",
        )