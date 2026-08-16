import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter()

# Default Organization UUID matching seed.py and schema.sql
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


# =====================================================================
# REQUEST & RESPONSE SCHEMAS
# =====================================================================
class LoginRequest(BaseModel):
    email: EmailStr
    password: Optional[str] = None


class UserProfile(BaseModel):
    id: uuid.UUID
    name: Optional[str] = None
    email: str
    role: str
    avatar: Optional[str] = None
    organization_id: uuid.UUID


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile
    organization_id: uuid.UUID


# =====================================================================
# AUTHENTICATION ENDPOINTS
# =====================================================================
@router.post("/login", response_model=LoginResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    Verifies user against the PostgreSQL users table and returns session payload
    matching the expectations of auth.js and frontend workspaces.
    """
    # 1. Search for user by email
    stmt = select(models.User).where(models.User.email == credentials.email.lower().strip())
    user = db.scalar(stmt)

    # 2. Fallback auto-provisioning for default seed roles during testing
    if not user:
        email_str = credentials.email.lower().strip()
        if email_str in ["admin@argo.ph", "maria.santos@tenant.ph", "ramon.santos@owner.ph"]:
            role_map = {
                "admin@argo.ph": ("Juan Dela Cruz", "admin", "JD"),
                "maria.santos@tenant.ph": ("Maria Santos", "client", "MS"),
                "ramon.santos@owner.ph": ("Don Ramon Santos", "owner", "RS"),
            }
            name, role, avatar = role_map[email_str]
            user = models.User(
                id=uuid.uuid4(),
                organization_id=DEFAULT_ORG_ID,
                name=name,
                email=email_str,
                role=role,
                avatar=avatar,
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials. User account not found in database."
            )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is currently disabled. Contact system administrator."
        )

    org_id = user.organization_id or DEFAULT_ORG_ID

    # 3. Generate structured session token
    session_token = f"argo_live_{user.role}_{uuid.uuid4()}"

    return LoginResponse(
        access_token=session_token,
        token_type="bearer",
        user=UserProfile(
            id=user.id,
            name=user.name or "User",
            email=user.email,
            role=user.role,
            avatar=user.avatar or "JD",
            organization_id=org_id
        ),
        organization_id=org_id
    )


@router.get("/me", response_model=UserProfile)
def get_current_user_profile(
    email: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Fetches the profile for the currently active session user.
    """
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User identifier is required."
        )

    stmt = select(models.User).where(models.User.email == email.lower().strip())
    user = db.scalar(stmt)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found."
        )

    return UserProfile(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        avatar=user.avatar or "JD",
        organization_id=user.organization_id or DEFAULT_ORG_ID
    )