import json
import os
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import HTTPException


def verify_turnstile_token(token: str, remote_ip: str | None) -> bool:
    secret = os.getenv("TURNSTILE_SECRET", "").strip()
    expected_hostnames = {
        hostname.strip().lower().rstrip(".")
        for hostname in os.getenv("TURNSTILE_HOSTNAMES", "").split(",")
        if hostname.strip()
    }
    if not secret or not expected_hostnames:
        raise HTTPException(
            status_code=503,
            detail="Link shortening is temporarily unavailable.",
        )
    if not token.strip() or len(token) > 2048:
        return False

    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    siteverify_request = UrlRequest(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=urlencode(payload).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(siteverify_request, timeout=10) as response:
            result = json.loads(response.read())
    except (OSError, TimeoutError, URLError, ValueError):
        return False

    if not isinstance(result, dict):
        return False
    hostname = str(result.get("hostname", "")).lower().rstrip(".")
    return (
        result.get("success") is True
        and result.get("action") == "shorten"
        and hostname in expected_hostnames
    )
