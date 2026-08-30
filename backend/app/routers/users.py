import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, ConfigDict, Field

from ..database import get_db
from .. import models

router = APIRouter()

DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


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
    email: EmailStr
    phone: Optional[str] = None
    role: Optional[str] = "admin"
    avatar: Optional[str] = "JD"
    is_active: Optional[bool] = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
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
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


def parse_user_identifier(db: Session, user_id_str: str, organization_id: uuid.UUID):
    """Robustly resolves a user by UUID or email address."""
    try:
        parsed_uuid = uuid.UUID(user_id_str)
        user = db.scalar(
            select(models.User).where(
                models.User.id == parsed_uuid,
                models.User.organization_id == organization_id
            )
        )
        if user:
            return user
    except ValueError:
        pass

    user = db.scalar(
        select(models.User).where(
            models.User.email.ilike(user_id_str),
            models.User.organization_id == organization_id
        )
    )
    return user


@router.get("/", response_model=List[UserResponse])
def get_all_users(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    role: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Retrieve all registered users (used by properties owner combobox and admin directories)."""
    stmt = select(models.User).where(models.User.organization_id == organization_id)
    if role:
        stmt = stmt.where(models.User.role.ilike(f"%{role}%"))
    users = list(db.scalars(stmt).all())
    return users


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_or_register_user(
    user_in: UserCreate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    """Handles new user registration and account creation."""
    org_id = organization_id or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    # Check for duplicate email across organization
    if user_in.email:
        existing = db.scalar(
            select(models.User).where(models.User.email.ilike(user_in.email))
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"An account with email '{user_in.email}' already exists."
            )

    user_data = user_in.model_dump(exclude_unset=True) if hasattr(user_in, "model_dump") else user_in.dict(exclude_unset=True)
    user_data["id"] = uuid.uuid4()
    user_data["organization_id"] = org_id

    if "name" in user_data and not user_data.get("full_name"):
        user_data["full_name"] = user_data["name"]
    elif "full_name" in user_data and not user_data.get("name"):
        user_data["name"] = user_data["full_name"]

    db_user = models.User(**user_data)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    email: Optional[str] = Query(default=None),
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    """Retrieve profile data for the active authenticated user session."""
    if email:
        user = db.scalar(
            select(models.User).where(
                models.User.email.ilike(email),
                models.User.organization_id == organization_id
            )
        )
        if user:
            return user
            
    user = db.scalar(select(models.User).where(models.User.organization_id == organization_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User session not found.")
    return user


@router.get("/{user_id}", response_model=UserResponse)
def get_user_by_id(
    user_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    """Retrieve a specific user profile by UUID or email."""
    user = parse_user_identifier(db, user_id, organization_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user_profile(
    user_id: str,
    user_update: UserUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    """Update personal credentials, name, email, and phone directly in PostgreSQL."""
    user = parse_user_identifier(db, user_id, organization_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True) if hasattr(user_update, "model_dump") else user_update.dict(exclude_unset=True)
    
    if "name" in update_data and "full_name" not in update_data and update_data["name"]:
        update_data["full_name"] = update_data["name"]
    elif "full_name" in update_data and "name" not in update_data and update_data["full_name"]:
        update_data["name"] = update_data["full_name"]

    for key, value in update_data.items():
        if hasattr(user, key):
            setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user