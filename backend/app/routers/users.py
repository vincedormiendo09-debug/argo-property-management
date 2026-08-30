import uuid
import logging
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from ..database import get_db
from .. import models

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def parse_org_id(org_id_raw: Optional[str]) -> uuid.UUID:
    """Safely converts string, null, or undefined organization IDs to valid UUIDs."""
    if not org_id_raw:
        return DEFAULT_ORG_ID
    clean = str(org_id_raw).strip().lower()
    if clean in ("undefined", "null", ""):
        return DEFAULT_ORG_ID
    try:
        return uuid.UUID(clean)
    except Exception:
        return DEFAULT_ORG_ID


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in local DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


class UserCreate(BaseModel):
    name: Optional[str] = "Admin User"
    full_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    role: Optional[str] = "admin"
    avatar: Optional[str] = "JD"
    is_active: Optional[bool] = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    avatar: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID] = None
    name: Optional[str] = "Admin User"
    full_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    role: str = "admin"
    avatar: Optional[str] = "JD"
    is_active: Optional[bool] = True

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


def parse_user_identifier(db: Session, user_id_str: str, organization_id: uuid.UUID):
    """Robustly resolves a user by UUID or email address with flexible org matching."""
    clean_id = user_id_str.strip()
    try:
        parsed_uuid = uuid.UUID(clean_id)
        user = db.scalar(
            select(models.User).where(
                models.User.id == parsed_uuid,
                or_(
                    models.User.organization_id == organization_id,
                    models.User.organization_id.is_(None)
                )
            )
        )
        if user:
            return user
    except ValueError:
        pass

    user = db.scalar(
        select(models.User).where(
            models.User.email.ilike(clean_id),
            or_(
                models.User.organization_id == organization_id,
                models.User.organization_id.is_(None)
            )
        )
    )
    if user:
        return user

    # Global fallback if not found within strict org bounds
    try:
        parsed_uuid = uuid.UUID(clean_id)
        return db.scalar(select(models.User).where(models.User.id == parsed_uuid))
    except ValueError:
        pass

    return db.scalar(select(models.User).where(models.User.email.ilike(clean_id)))


# ---------------------------------------------------------------------
# 1. GET ALL USERS (Filtered by role and flexible org)
# ---------------------------------------------------------------------
@router.get("")
@router.get("/", response_model=List[UserResponse])
def get_all_users(
    organization_id: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Retrieve all registered users with flexible matching for client/tenant and owner roles."""
    stmt = select(models.User)

    if organization_id:
        org_id = parse_org_id(organization_id)
        ensure_sandbox_organization(db, org_id)
        if hasattr(models.User, "organization_id"):
            stmt = stmt.where(
                or_(
                    models.User.organization_id == org_id,
                    models.User.organization_id.is_(None)
                )
            )
    
    if role:
        clean_role = role.lower().strip()
        if clean_role in ["tenant", "client", "client_pov", "resident"]:
            stmt = stmt.where(
                or_(
                    models.User.role.ilike("%client%"),
                    models.User.role.ilike("%tenant%"),
                    models.User.role.ilike("%resident%")
                )
            )
        elif clean_role in ["owner", "property_owner", "investor"]:
            stmt = stmt.where(
                or_(
                    models.User.role.ilike("%owner%"),
                    models.User.role.ilike("%investor%")
                )
            )
        else:
            stmt = stmt.where(models.User.role.ilike(f"%{clean_role}%"))

    users = list(db.scalars(stmt).all())

    # Ensure compatibility between 'name' and 'full_name' attributes
    for u in users:
        u_name = getattr(u, "name", None)
        u_full = getattr(u, "full_name", None)
        if not u_name and u_full:
            setattr(u, "name", u_full)
        elif not u_full and u_name:
            setattr(u, "full_name", u_name)

    return users


# ---------------------------------------------------------------------
# 2. CREATE OR REGISTER USER
# ---------------------------------------------------------------------
@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_or_register_user(
    user_in: UserCreate,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Handles new user registration and account creation."""
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    # Check for duplicate email across organization
    if user_in.email:
        clean_email = user_in.email.lower().strip()
        existing = db.scalar(
            select(models.User).where(models.User.email.ilike(clean_email))
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"An account with email '{user_in.email}' already exists."
            )

    raw_data = user_in.model_dump(exclude_unset=True) if hasattr(user_in, "model_dump") else user_in.dict(exclude_unset=True)
    raw_data["id"] = uuid.uuid4()
    raw_data["organization_id"] = org_id
    raw_data["email"] = user_in.email.lower().strip()

    name_val = raw_data.get("name") or raw_data.get("full_name") or "User"
    raw_data["name"] = name_val
    raw_data["full_name"] = name_val

    # Safeguard: only pass attributes that actually exist on models.User
    user_kwargs = {}
    for k, v in raw_data.items():
        if hasattr(models.User, k):
            user_kwargs[k] = v

    db_user = models.User(**user_kwargs)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


# ---------------------------------------------------------------------
# 3. GET ACTIVE USER PROFILE (/me)
# ---------------------------------------------------------------------
@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    email: Optional[str] = Query(default=None),
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Retrieve profile data for the active authenticated user session."""
    org_id = parse_org_id(organization_id)
    if email:
        user = db.scalar(
            select(models.User).where(
                models.User.email.ilike(email.strip()),
                or_(
                    models.User.organization_id == org_id,
                    models.User.organization_id.is_(None)
                )
            )
        )
        if user:
            return user
            
    user = db.scalar(
        select(models.User).where(
            or_(
                models.User.organization_id == org_id,
                models.User.organization_id.is_(None)
            )
        )
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User session not found.")
    return user


# ---------------------------------------------------------------------
# 4. GET SINGLE USER BY ID OR EMAIL
# ---------------------------------------------------------------------
@router.get("/{user_id}", response_model=UserResponse)
@router.get("/{user_id}/", response_model=UserResponse)
def get_user_by_id(
    user_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Retrieve a specific user profile by UUID or email."""
    org_id = parse_org_id(organization_id)
    user = parse_user_identifier(db, user_id, org_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# ---------------------------------------------------------------------
# 5. UPDATE USER PROFILE
# ---------------------------------------------------------------------
@router.put("/{user_id}", response_model=UserResponse)
@router.put("/{user_id}/", response_model=UserResponse)
@router.patch("/{user_id}", response_model=UserResponse)
@router.patch("/{user_id}/", response_model=UserResponse)
def update_user_profile(
    user_id: str,
    user_update: UserUpdate,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Update personal credentials, name, email, and phone directly in PostgreSQL."""
    org_id = parse_org_id(organization_id)
    user = parse_user_identifier(db, user_id, org_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True) if hasattr(user_update, "model_dump") else user_update.dict(exclude_unset=True)
    
    if "name" in update_data and "full_name" not in update_data and update_data["name"]:
        update_data["full_name"] = update_data["name"]
    elif "full_name" in update_data and "name" not in update_data and update_data["full_name"]:
        update_data["name"] = update_data["full_name"]

    if "email" in update_data and update_data["email"]:
        update_data["email"] = update_data["email"].lower().strip()

    for key, value in update_data.items():
        if hasattr(user, key):
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user