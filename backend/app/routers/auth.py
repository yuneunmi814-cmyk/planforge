from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas import (
    AccessTokenRes,
    LoginReq,
    RefreshReq,
    SignupReq,
    TokenPair,
    UserRes,
)
from app.services import audit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", response_model=UserRes, status_code=status.HTTP_201_CREATED)
def signup(body: SignupReq, db: Session = Depends(get_db)) -> User:
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_taken")

    # The very first user becomes an approved admin (bootstrap); others pending.
    first_user = db.scalar(select(func.count()).select_from(User)) == 0
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role="admin" if first_user else "user",
        status="approved" if first_user else "pending",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.record(
        db, actor_user_id=user.id, action="user.signup", target_type="user", target_id=user.id
    )
    return user


@router.post("/login", response_model=TokenPair)
def login(body: LoginReq, db: Session = Depends(get_db)) -> TokenPair:
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials"
        )
    if user.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account_disabled")
    return TokenPair(
        accessToken=create_access_token(user.id, user.role),
        refreshToken=create_refresh_token(user.id, user.role),
        role=user.role,
        status=user.status,
    )


@router.post("/refresh", response_model=AccessTokenRes)
def refresh(body: RefreshReq, db: Session = Depends(get_db)) -> AccessTokenRes:
    payload = decode_token(body.refreshToken)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_refresh_token")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
    return AccessTokenRes(accessToken=create_access_token(user.id, user.role))


@router.get("/me", response_model=UserRes)
def me(user: User = Depends(get_current_user)) -> User:
    return user
