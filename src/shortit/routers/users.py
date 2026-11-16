import os

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from shortit.database import get_session
from shortit.limiter import limiter
from shortit.dependencies import get_current_user
from shortit.schemas import AuthResponse, GoogleLoginRequest, LoginRequest, UserCreate, UserRead
from shortit.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/register")
@limiter.limit("5/minute")
async def register(
    request: Request,
    data: UserCreate,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthResponse:
    return await users_service.register(data, session, response)

@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    data: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthResponse:
    return await users_service.login(data, session, response)


@router.post("/refresh", response_model=AuthResponse)
@limiter.limit("30/minute")
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthResponse:
    return users_service.refresh(request.cookies.get("shortit_refresh"), session, response)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    return users_service.logout(request.cookies.get("shortit_refresh"), session, response)


@router.post("/google", response_model=AuthResponse)
@limiter.limit("10/minute")
async def google_login(
    request: Request,
    data: GoogleLoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthResponse:
    return await users_service.login_with_google(data.credential, session, response)


@router.get("/google/config")
def google_config():
    return {"client_id": os.getenv("GOOGLE_CLIENT_ID", "").strip()}

@router.get("/me", response_model=UserRead)
async def me(user = Depends(get_current_user)):
    return user
