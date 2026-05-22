from datetime import timedelta
from typing import List
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    AccessRequest,
    LoginRequest,
    SetPasswordRequest,
    Token,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.core.security import (
    create_access_token,
    create_signup_token,
    decode_signup_token,
    get_password_hash,
    verify_password,
)
from app.config import get_settings
from app.api.deps import get_current_active_user
from app.core.limiter import email_limiter, limiter
from app.services import email as email_service

router = APIRouter()
settings = get_settings()


def _signup_link(token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/set-password?token={token}"


def _send_signup_link(
    background: BackgroundTasks,
    user: User,
    invited_by: str | None = None,
) -> None:
    token = create_signup_token(user.id)
    link = _signup_link(token)
    background.add_task(
        email_service.send_signup_link_email,
        user.email,
        link,
        invited_by=invited_by,
    )


@router.post("/request-access", response_model=dict)
@limiter.limit("3/hour")
async def request_access(
    request: Request,
    payload: AccessRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Public endpoint: anyone can request access by email.

    Always returns the same shape regardless of whether the email is new,
    duplicate, or already an active user — prevents account enumeration.
    """
    if not email_limiter.hit(
        f"request-access:{payload.email}", limit=1, window=timedelta(days=1)
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests for this email — try again later",
        )

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is None:
        user = User(
            email=payload.email,
            password_hash=None,
            role="reviewer",
            is_active=False,
        )
        db.add(user)
        db.commit()

        owner_emails = [
            o.email
            for o in db.query(User).filter(User.role == "owner", User.is_active.is_(True)).all()
        ]
        background.add_task(
            email_service.send_access_request_notification,
            payload.email,
            owner_emails,
        )

    return {"status": "ok"}


@router.post("/set-password", response_model=Token)
async def set_password(payload: SetPasswordRequest, db: Session = Depends(get_db)):
    """Consume a signup token to set the user's password and log them in."""
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    user_id = decode_signup_token(payload.token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link is invalid or expired",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.password_hash is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This link is invalid or expired",
        )

    user.password_hash = get_password_hash(payload.password)
    user.is_active = True
    db.commit()
    db.refresh(user)

    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role}
    )
    return Token(access_token=access_token)


@router.post("/invite", response_model=UserResponse)
async def invite_user(
    payload: AccessRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Owner-initiated invite: skip the approval step and email a signup link."""
    if current_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access required",
        )

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        if existing.password_hash is not None:
            detail = "User already has an account"
        elif existing.is_active:
            detail = "Invite already sent — link is still valid"
        else:
            detail = "This email already has a pending access request — approve it instead"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    user = User(
        email=payload.email,
        password_hash=None,
        role="reviewer",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _send_signup_link(background, user, invited_by=current_user.email)
    return user


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request, login_data: LoginRequest, db: Session = Depends(get_db)
):
    """Login and get access token."""
    if not email_limiter.hit(
        f"login:{login_data.email}", limit=20, window=timedelta(hours=1)
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts for this account — try again later",
        )

    user = db.query(User).filter(User.email == login_data.email).first()
    if (
        not user
        or user.password_hash is None
        or not verify_password(login_data.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not yet approved",
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role}
    )
    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
):
    """Get current user info."""
    return current_user


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all users. Admin or Owner only."""
    if current_user.role not in ("admin", "owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner access required",
        )
    return db.query(User).all()


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_update: UserUpdate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update user. Owners approve (activate) requests; Admins change roles."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    role_change = user_update.role is not None and user_update.role != user.role
    activation = (
        user_update.is_active is not None and user_update.is_active != user.is_active
    )

    if role_change and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to change role",
        )
    if activation and current_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access required to approve users",
        )

    becomes_active = (
        activation
        and user_update.is_active is True
        and user.password_hash is None
    )

    if role_change:
        user.role = user_update.role
    if activation:
        user.is_active = user_update.is_active

    db.commit()
    db.refresh(user)

    if becomes_active:
        _send_signup_link(background, user)
    return user


@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new user (admin creates active users). Admin only."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        role="reviewer",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
