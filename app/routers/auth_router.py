from fastapi import APIRouter, Depends, HTTPException, status
from app.auth import create_access_token, get_current_admin, verify_admin_credentials
from app.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse, summary="後台管理員登入")
def login(payload: LoginRequest):
    """驗證管理員帳號密碼並回傳 JWT Access Token"""
    if not verify_admin_credentials(payload.username, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="帳號或密碼錯誤",
        )
    token = create_access_token(payload.username)
    return TokenResponse(access_token=token, username=payload.username)


@router.get("/me", summary="驗證目前登入狀態")
def get_me(current_admin: str = Depends(get_current_admin)):
    return {"username": current_admin, "authenticated": True}
