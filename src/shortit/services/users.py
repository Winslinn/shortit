from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
import jwt
from fastapi import HTTPException, Response
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from shortit.database import RefreshToken, User
from shortit.events import UserRegisteredEvent, publish_user_registered
from shortit.schemas import AuthResponse, LoginRequest, UserCreate

ACCESS_TOKEN_SECONDS = 5 * 60
REFRESH_TOKEN_DAYS = 30
_dummy_password_hash = bcrypt.hashpw(b"shortit-dummy-password", bcrypt.gensalt())

def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    return secret

def _refresh_cookie_secure() -> bool:
    return os.getenv("REFRESH_COOKIE_SECURE", "true").strip().lower() in {"1", "true", "yes"}

def _password_secret() -> bytes:
    secret = os.getenv("PASSWORD_SECRET", "").encode("utf-8")
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="Password hashing is not configured.")
    return secret

def _password_material(password: bytes, secret: bytes) -> bytes:
    return hmac.digest(secret, password, "sha256")

def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def _revoke_refresh_family(
    session: Session,
    user_id: int,
    family_id: str | None,
    revoked_at: str,
) -> None:
    statement = update(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
    )
    if family_id is not None:
        statement = statement.where(RefreshToken.family_id == family_id)
    session.execute(statement.values(revoked_at=revoked_at))

def _record_refresh_reuse(
    session: Session,
    stored: RefreshToken,
    detected_at: str,
) -> None:
    session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == stored.token_hash,
            RefreshToken.reuse_detected_at.is_(None),
        )
        .values(reuse_detected_at=detected_at)
    )
    _revoke_refresh_family(session, stored.user_id, stored.family_id, detected_at)
    session.commit()

def _create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user.id), "iat": now, "exp": now + timedelta(seconds=ACCESS_TOKEN_SECONDS)},
        _jwt_secret(),
        algorithm="HS256",
    )

def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="shortit_refresh",
        value=token,
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=_refresh_cookie_secure(),
        samesite="strict",
        path="/users",
    )

def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=_create_access_token(user),
        token_type="bearer",
        expires_in=ACCESS_TOKEN_SECONDS,
        user=user,
    )

def _issue_refresh_token(
    session: Session,
    user: User,
    response: Response,
    family_id: str | None = None,
) -> None:
    # Fail before committing a user or refresh token if deployment secrets are missing.
    _jwt_secret()
    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_DAYS)
    session.add(
        RefreshToken(
            token_hash=_hash_refresh_token(raw_token),
            user_id=user.id,
            expires_at=expires_at.isoformat(),
            family_id=family_id or uuid4().hex,
        )
    )
    session.commit()
    _set_refresh_cookie(response, raw_token)

async def register(data: UserCreate, session: Session, response: Response) -> AuthResponse:
    email = data.email
    if session.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "already_registered", "message": "This email is already registered."},
        )

    password = data.password.get_secret_value().encode("utf-8")
    password_material = _password_material(password, _password_secret())
    password_hash = await asyncio.to_thread(bcrypt.hashpw, password_material, bcrypt.gensalt())
    registered_at = datetime.now(UTC).isoformat()
    user = User(
        email=email,
        password_hash=password_hash.decode("ascii"),
        is_active=True,
        created_at=registered_at,
    )
    session.add(user)
    try:
        session.flush()
        event = UserRegisteredEvent(
            user_id=user.id,
            email=email,
            registered_at=registered_at,
            provider="password",
        )
        _issue_refresh_token(session, user, response)
    except Exception:
        session.rollback()
        # A concurrent registration can win after the initial existence check.
        if session.scalar(select(User.id).where(User.email == email)) is not None:
            raise HTTPException(
                status_code=409,
                detail={"code": "already_registered", "message": "This email is already registered."},
            ) from None
        raise
    auth_response = _auth_response(user)
    await publish_user_registered(event)
    return auth_response

async def login(data: LoginRequest, session: Session, response: Response) -> AuthResponse:
    user = session.scalar(select(User).where(User.email == data.email))
    password_hash = (
        user.password_hash.encode("ascii")
        if user is not None and user.password_hash is not None
        else _dummy_password_hash
    )
    password = data.password.get_secret_value().encode("utf-8")
    password_material = _password_material(password, _password_secret())
    password_matches, legacy_password_matches = await asyncio.gather(
        asyncio.to_thread(bcrypt.checkpw, password_material, password_hash),
        asyncio.to_thread(bcrypt.checkpw, password, password_hash),
    )
    # Upgrade hashes created before PASSWORD_SECRET was introduced after a successful login.
    if (
        legacy_password_matches
        and not password_matches
        and user is not None
        and user.password_hash is not None
        and user.is_active
    ):
        user.password_hash = (
            await asyncio.to_thread(bcrypt.hashpw, password_material, bcrypt.gensalt())
        ).decode("ascii")
        session.commit()
    if (
        user is None
        or user.password_hash is None
        or not (password_matches or legacy_password_matches)
        or not user.is_active
    ):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    _issue_refresh_token(session, user, response)
    return _auth_response(user)

def refresh(token: str | None, session: Session, response: Response) -> AuthResponse:
    _jwt_secret()
    if not token:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    stored = session.get(RefreshToken, _hash_refresh_token(token))
    now = datetime.now(UTC)
    if stored is None:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    now_iso = now.isoformat()
    if stored.revoked_at is not None:
        _record_refresh_reuse(session, stored, now_iso)
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    if datetime.fromisoformat(stored.expires_at) <= now:
        session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == stored.token_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now_iso)
        )
        session.commit()
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    user = session.get(User, stored.user_id)
    if user is None or not user.is_active:
        _revoke_refresh_family(session, stored.user_id, stored.family_id, now_iso)
        session.commit()
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    family_id = stored.family_id or uuid4().hex
    # Atomically consume the old token so simultaneous refreshes cannot both rotate it.
    consumed = session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == stored.token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now_iso,
        )
        .values(revoked_at=now_iso, family_id=family_id)
    )
    if consumed.rowcount != 1:
        session.rollback()
        stored = session.get(RefreshToken, _hash_refresh_token(token))
        if stored is not None and stored.revoked_at is not None:
            _record_refresh_reuse(session, stored, now_iso)
        elif stored is not None:
            session.execute(
                update(RefreshToken)
                .where(RefreshToken.token_hash == stored.token_hash)
                .values(revoked_at=now_iso)
            )
            session.commit()
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    raw_token = secrets.token_urlsafe(48)
    session.add(
        RefreshToken(
            token_hash=_hash_refresh_token(raw_token),
            user_id=user.id,
            expires_at=(now + timedelta(days=REFRESH_TOKEN_DAYS)).isoformat(),
            family_id=family_id,
        )
    )
    session.commit()
    _set_refresh_cookie(response, raw_token)
    return _auth_response(user)

def logout(token: str | None, session: Session, response: Response) -> dict[str, bool]:
    if token:
        session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == _hash_refresh_token(token),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC).isoformat())
        )
        session.commit()
    response.delete_cookie(
        key="shortit_refresh",
        httponly=True,
        secure=_refresh_cookie_secure(),
        samesite="strict",
        path="/users",
    )
    return {"logged_out": True}

async def login_with_google(
    credential: str,
    session: Session,
    response: Response,
) -> AuthResponse:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")

    try:
        claims = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            credential,
            GoogleRequest(),
            client_id,
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Google sign-in could not be verified.") from None

    email_claim = claims.get("email")
    google_sub = claims.get("sub")
    if (
        claims.get("email_verified") is not True
        or not isinstance(email_claim, str)
        or not isinstance(google_sub, str)
        or not email_claim.strip()
        or not google_sub
    ):
        raise HTTPException(status_code=401, detail="Google sign-in could not be verified.")
    email = email_claim.strip().lower()

    user = session.scalar(select(User).where(User.google_sub == google_sub))
    is_new_user = False
    registered_at = datetime.now(UTC).isoformat()
    if user is None:
        user = session.scalar(select(User).where(User.email == email))
        if user is not None:
            # Google has verified ownership of this email address.
            user.google_sub = google_sub
        else:
            user = User(
                email=email,
                google_sub=google_sub,
                password_hash=None,
                is_active=True,
                created_at=registered_at,
            )
            session.add(user)
            is_new_user = True

    event: UserRegisteredEvent | None = None
    try:
        session.flush()
        if is_new_user:
            event = UserRegisteredEvent(
                user_id=user.id,
                email=email,
                registered_at=registered_at,
                provider="google",
            )
        _issue_refresh_token(session, user, response)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=409, detail="Could not create your account. Please try again.") from None
    auth_response = _auth_response(user)
    if event is not None:
        await publish_user_registered(event)
    return auth_response
