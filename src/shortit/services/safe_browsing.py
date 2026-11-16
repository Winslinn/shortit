import hashlib
import json
import logging
import math
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException

SAFE_BROWSING_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
SAFE_BROWSING_TIMEOUT_SECONDS = 5
SAFE_BROWSING_CACHE_MAX_ENTRIES = 2048
logger = logging.getLogger(__name__)

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

    query = urlencode({"key": api_key})
    payload = {
        "client": {"clientId": "shortit", "clientVersion": "0.1.0"},
        "threatInfo": {
            "threatTypes": [
                "MALWARE",
                "SOCIAL_ENGINEERING",
                "UNWANTED_SOFTWARE",
                "POTENTIALLY_HARMFUL_APPLICATION",
            ],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": url}],
        },
    }
    request = Request(
        f"{SAFE_BROWSING_URL}?{query}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    response_content_type = "unknown"
    try:
        with urlopen(request, timeout=SAFE_BROWSING_TIMEOUT_SECONDS) as response:
            response_content_type = response.headers.get("Content-Type", "unknown")
            result = json.loads(response.read())
    except HTTPError as exc:
        try:
            error_body = json.loads(exc.read())
        except (OSError, ValueError):
            error_body = {}
        api_error = error_body.get("error", {}) if isinstance(error_body, dict) else {}
        if not isinstance(api_error, dict):
            api_error = {}
        logger.warning(
            "Safe Browsing API returned HTTP %s (%s): %s",
            exc.code,
            api_error.get("status", "unknown status"),
            api_error.get("message", "no error message"),
        )
        raise HTTPException(
            status_code=503,
            detail="Link safety checks are temporarily unavailable.",
        ) from exc
    except (OSError, TimeoutError, URLError) as exc:
        logger.warning(
            "Safe Browsing API request failed (%s): %s",
            type(exc).__name__,
            getattr(exc, "reason", str(exc)),
        )
        raise HTTPException(
            status_code=503,
            detail="Link safety checks are temporarily unavailable.",
        ) from exc
    except ValueError as exc:
        logger.warning(
            "Safe Browsing API returned invalid JSON (Content-Type: %s): %s",
            response_content_type,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail="Link safety checks are temporarily unavailable.",
        ) from exc

    if not isinstance(result, dict):
        logger.warning("Safe Browsing API returned an unexpected response format.")
        raise HTTPException(
            status_code=503,
            detail="Link safety checks are temporarily unavailable.",
        )

    matches = result.get("matches", [])
    if not isinstance(matches, list):
        logger.warning("Safe Browsing API returned an invalid matches field.")
        raise HTTPException(
            status_code=503,
            detail="Link safety checks are temporarily unavailable.",
        )

    is_threat = bool(matches)
    cache_durations = []
    for match in matches:
        if not isinstance(match, dict):
            logger.warning("Safe Browsing API returned an invalid threat match.")
            raise HTTPException(
                status_code=503,
                detail="Link safety checks are temporarily unavailable.",
            )
        cache_duration = match.get("cacheDuration")
        if cache_duration is None:
            continue
        try:
            if not isinstance(cache_duration, str) or not cache_duration.endswith("s"):
                raise ValueError("Invalid Safe Browsing cache duration")
            duration = float(cache_duration[:-1])
            if not math.isfinite(duration) or duration < 0:
                raise ValueError("Invalid Safe Browsing cache duration")
            cache_durations.append(duration)
        except ValueError as exc:
            logger.warning("Safe Browsing API returned an invalid cacheDuration: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Link safety checks are temporarily unavailable.",
            ) from exc

    duration_seconds = min(cache_durations, default=0.0)
    if is_threat and duration_seconds > 0:
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
