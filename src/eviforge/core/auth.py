from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from eviforge.config import ACK_TEXT, load_settings
from eviforge.core.db import create_session_factory
from eviforge.core.db import get_setting
from eviforge.core.models import User

SECRET_KEY = os.getenv("EVIFORGE_SECRET_KEY", "eviforge-dev-insecure")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(request: Request, token: str | None = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            token = cookie_token[7:] if cookie_token.startswith("Bearer ") else cookie_token
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
        
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == token_data.username).first()
        if user is None:
            raise credentials_exception
        return user

def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_admin_user(current_user: User = Depends(get_current_active_user)):
    if current_user.role != "admin":
         raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


def require_roles(*roles: str):
    """RBAC guard. Usage: `Depends(require_roles("admin", "analyst"))`."""

    def _dep(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return current_user

    return _dep

async def ack_dependency():
    """
    Dependency to enforce legal acknowledgement.
    Blocks access until the user explicitly acknowledges the required text.
    """
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        ack = get_setting(session, "authorization_ack")
        if not ack:
            raise HTTPException(
                status_code=428,
                detail={"error": "authorization_required", "ack_text": ACK_TEXT},
            )


def ensure_bootstrap_admin(session: Session) -> None:
    """
    Production-safe bootstrap: if there are no users, create an admin user
    using env vars. This avoids the insecure "create admin on first login"
    anti-pattern.

    Env:
      - EVIFORGE_ADMIN_USERNAME (default: admin)
      - EVIFORGE_ADMIN_PASSWORD (required to bootstrap)
    """
    username = os.getenv("EVIFORGE_ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("EVIFORGE_ADMIN_PASSWORD")
    enforce_env_admin = os.getenv("EVIFORGE_ENFORCE_ENV_ADMIN", "1") == "1"

    try:
        user_count = session.query(User).count()
    except Exception:
        return

    # Keep configured env admin usable even if DB already exists.
    if enforce_env_admin:
        existing = session.query(User).filter(User.username == username).first()
        if existing:
            changed = False
            if existing.role != "admin":
                existing.role = "admin"
                changed = True
            if not existing.is_active:
                existing.is_active = True
                changed = True
            if password:
                needs_password_update = False
                try:
                    needs_password_update = not verify_password(password, existing.hashed_password)
                except Exception:
                    needs_password_update = True
                if needs_password_update:
                    existing.hashed_password = get_password_hash(password)
                    changed = True
            if changed:
                session.add(existing)
                session.commit()
            return

    if user_count != 0:
        return

    if not password:
        return

    session.add(
        User(
            username=username,
            hashed_password=get_password_hash(password),
            role="admin",
            is_active=True,
        )
    )
    session.commit()
