from __future__ import annotations

import asyncio
import os
import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from shortit.database import db
from shortit.dependencies import get_current_user
from shortit.limiter import limiter
from shortit.schemas import Link, LinkCreate
from shortit.services.safe_browsing import check_url_safety
from shortit.services.turnstile import verify_turnstile_token

APP_HOSTNAME = os.getenv("APP_HOSTNAME")
router = APIRouter(tags=["links"])

def validate_url(url: str) -> None:
    url_parse = urlsplit(url)

    if url_parse.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail="Only http or https schemas")
    if APP_HOSTNAME and (
        url_parse.hostname == APP_HOSTNAME
        or (url_parse.hostname and url_parse.hostname.endswith("." + APP_HOSTNAME))
    ):
        raise HTTPException(status_code=400, detail="Cannot shorten URLs pointing to this domain")


async def create(data: LinkCreate, request: Request, user_id: int) -> Link:
    validate_url(str(data.url))
    await asyncio.to_thread(check_url_safety, str(data.url))

    if not verify_turnstile_token(
        data.turnstile_token or "",
        request.client.host if request.client else None,
    ):
        raise HTTPException(status_code=403, detail="Complete the security check and try again.")

    code = secrets.token_urlsafe(8)
    link = await db.insert_link(code=code, url=str(data.url), user_id=user_id)
    return Link.model_validate(link)


async def resolve(code: str) -> str | None:
    link = await db.get_link(code)
    if not link:
        return None
    await db.increment_clicks(link.id)
    return link.url


async def list_for_user(user_id: int) -> list[Link]:
    links = await db.get_links(user_id)
    return [Link.model_validate(link) for link in links]


@router.post("/links/")
@limiter.limit("5/month")
async def create_link(
    request: Request,
    data: LinkCreate,
    user=Depends(get_current_user),
):
    return await create(data, request, user_id=user.id)


@router.get("/s/{code}")
async def redirect_url(code: str) -> RedirectResponse:
    destination = await resolve(code)
    if destination is None:
        raise HTTPException(status_code=404, detail="Short URL not found")
    return RedirectResponse(url=destination, status_code=302)
