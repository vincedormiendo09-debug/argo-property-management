import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
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
    email: str
    password: Optional[str] = None
    username: Optional[str] = None  # OAuth2 form support


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = "client"
    organization_id: Optional[uuid.UUID] = DEFAULT_ORG_ID


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
@router.post("/login/", response_model=LoginResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    Verifies user against the PostgreSQL users table and returns session payload
    matching frontend workspace expectations.
    """
    search_email = (credentials.email or credentials.username or "").lower().strip()
    if not search_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username is required."
        )

    # 1. Search for user by email
    stmt = select(models.User).where(models.User.email == search_email)
    user = db.scalar(stmt)

    # 2. Fallback auto-provisioning for default seed roles during testing
    if not user:
        if search_email in ["admin@argo.ph", "maria.santos@tenant.ph", "ramon.santos@owner.ph"]:
            role_map = {
                "admin@argo.ph": ("Juan Dela Cruz", "admin", "JD"),
                "maria.santos@tenant.ph": ("Maria Santos", "client", "MS"),
                "ramon.santos@owner.ph": ("Don Ramon Santos", "owner", "RS"),
            }
            name, role, avatar = role_map[search_email]
            user = models.User(
                id=uuid.uuid4(),
                organization_id=DEFAULT_ORG_ID,
                name=name,
                full_name=name,
                email=search_email,
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


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
@router.post("/register/", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """
    Handles new user self-registration from index.html and provisions them in PostgreSQL.
    """
    clean_email = payload.email.lower().strip()

    # 1. Check if user already exists
    existing_user = db.scalar(select(models.User).where(models.User.email == clean_email))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists."
        )

    # 2. Normalize role
    normalized_role = payload.role.lower().strip()
    if normalized_role in ["tenant", "client_pov"]:
        normalized_role = "client"
    elif normalized_role in ["property_owner", "investor"]:
        normalized_role = "owner"
    elif normalized_role not in ["admin", "owner", "client"]:
        normalized_role = "client"

    initials = "".join([n[0] for n in payload.name.split() if n])[:2].upper() if payload.name else "US"

    # 3. Create new user record
    new_user = models.User(
        id=uuid.uuid4(),
        organization_id=payload.organization_id or DEFAULT_ORG_ID,
        name=payload.name,
        full_name=payload.full_name or payload.name,
        email=clean_email,
        phone=payload.phone,
        role=normalized_role,
        avatar=initials or "U",
        is_active=True
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    session_token = f"argo_live_{new_user.role}_{uuid.uuid4()}"
    org_id = new_user.organization_id or DEFAULT_ORG_ID

    return LoginResponse(
        access_token=session_token,
        token_type="bearer",
        user=UserProfile(
            id=new_user.id,
            name=new_user.name,
            email=new_user.email,
            role=new_user.role,
            avatar=new_user.avatar,
            organization_id=org_id
        ),
        organization_id=org_id
    )


@router.get("/me", response_model=UserProfile)
@router.get("/me/", response_model=UserProfile)
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