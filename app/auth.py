import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, HTTPBearer
from app.config import get_settings

ALGORITHM = "HS256"

bearer_scheme = HTTPBearer(auto_error=False)
basic_scheme = HTTPBasic(auto_error=False)


def verify_admin_credentials(username: str, password: str) -> bool:
    """使用常數時間比對驗證管理員帳號密碼"""
    settings = get_settings()
    is_user_ok = secrets.compare_digest(username.encode("utf-8"), settings.admin_username.encode("utf-8"))
    is_pass_ok = secrets.compare_digest(password.encode("utf-8"), settings.admin_password.encode("utf-8"))
    return is_user_ok and is_pass_ok


def create_access_token(username: str) -> str:
    """簽發後台管理員 JWT Token"""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def get_current_admin(
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    basic: Optional[HTTPBasicCredentials] = Depends(basic_scheme),
) -> str:
    """
    保護後台 API 的 Dependency：
    同時支援 JWT Bearer Token 與 HTTP Basic Auth
    """
    settings = get_settings()

    # 1. 優先檢查 Bearer Token
    if bearer and bearer.credentials:
        try:
            payload = jwt.decode(
                bearer.credentials,
                settings.jwt_secret_key,
                algorithms=[ALGORITHM],
            )
            username: str = payload.get("sub")
            if username and secrets.compare_digest(username, settings.admin_username):
                return username
        except jwt.PyJWTError:
            pass

    # 2. 次要檢查 HTTP Basic Auth
    if basic and basic.username and basic.password:
        if verify_admin_credentials(basic.username, basic.password):
            return basic.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未經授權的存取，請先登入管理後台",
        headers={"WWW-Authenticate": "Bearer"},
    )
