from fastapi import APIRouter, Depends, Request
from shortit.limiter import limiter
from shortit.dependencies import get_current_user
from shortit.schemas import LoginRequest, UserCreate, UserRead
from shortit.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, data: UserCreate):
    return await users_service.register(data)

@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, data: LoginRequest):
    return await users_service.login(data)

@router.get("/me", response_model=UserRead)
async def me(user = Depends(get_current_user)):
    return user
