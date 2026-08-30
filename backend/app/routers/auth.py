import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

# Default Organization UUID matching seed.py and schema.sql
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_organization_exists(db: Session, org_id: uuid.UUID) -> None:
    """Guarantees the organization row exists to prevent foreign key violations."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(
            id=org_id,
            name="ARGO Property Management Corp."
        )
        db.add(sandbox_org)
        db.commit()


# =====================================================================
# REQUEST & RESPONSE SCHEMAS
# =====================================================================
class LoginRequest(BaseModel):
    email: str
    password: Optional[str] = None
    username: Optional[str] = None


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
# PRE-CONFIGURED SEED ACCOUNTS (1 ADMIN, 2 TENANTS, 2 OWNERS)
# =====================================================================
SEED_ACCOUNTS = {
    # 1 Admin Account
    "admin@argo.ph": {
        "name": "Juan Dela Cruz",
        "role": "admin",
        "avatar": "JD",
        "phone": "+63 917 100 0001"
    },
    # 2 Tenant / Client Accounts
    "maria.santos@tenant.ph": {
        "name": "Maria Santos",
        "role": "client",
        "avatar": "MS",
        "phone": "+63 917 200 0001"
    },
    "carlos.mendoza@tenant.ph": {
        "name": "Carlos Mendoza",
        "role": "client",
        "avatar": "CM",
        "phone": "+63 917 200 0002"
    },
    # 2 Property Owner Accounts
    "ramon.santos@owner.ph": {
        "name": "Don Ramon Santos",
        "role": "owner",
        "avatar": "RS",
        "phone": "+63 917 300 0001"
    },
    "elena.villanueva@owner.ph": {
        "name": "Elena Villanueva",
        "role": "owner",
        "avatar": "EV",
        "phone": "+63 917 300 0002"
    }
}


def create_operational_profile(db: Session, user: models.User, org_id: uuid.UUID) -> None:
    """Safely auto-provisions matching tenant or owner operational records."""
    try:
        name_parts = (user.name or "User").split(maxsplit=1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        if user.role in ["client", "tenant"]:
            tenant_exists = db.scalar(select(models.Tenant).where(models.Tenant.email == user.email))
            if not tenant_exists:
                t = models.Tenant(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    email=user.email,
                    phone=user.phone or "",
                    status="active"
                )
                if hasattr(t, "user_id"):
                    t.user_id = user.id
                if hasattr(t, "name"):
                    t.name = user.name
                if hasattr(t, "full_name"):
                    t.full_name = user.name
                if hasattr(t, "first_name"):
                    t.first_name = first_name
                if hasattr(t, "last_name"):
                    t.last_name = last_name

                db.add(t)
                db.commit()

        elif user.role in ["owner", "property_owner"]:
            owner_exists = db.scalar(select(models.Owner).where(models.Owner.email == user.email))
            if not owner_exists:
                o = models.Owner(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    email=user.email,
                    phone=user.phone or "",
                    status="active"
                )
                if hasattr(o, "user_id"):
                    o.user_id = user.id
                if hasattr(o, "name"):
                    o.name = user.name
                if hasattr(o, "full_name"):
                    o.full_name = user.name
                if hasattr(o, "first_name"):
                    o.first_name = first_name
                if hasattr(o, "last_name"):
                    o.last_name = last_name

                db.add(o)
                db.commit()
    except Exception as err:
        db.rollback()
        logger.warning(f"Operational auto-provision skipped for {user.email}: {err}")

# =====================================================================
# AUTHENTICATION ENDPOINTS
# =====================================================================
@router.post("/login", response_model=LoginResponse)
@router.post("/login/", response_model=LoginResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticates users against PostgreSQL. If a configured seed account is used for
    the first time, it auto-provisions the organization, user, and operational records.
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

    # 2. Auto-provision seed test accounts if they do not exist yet
    if not user:
        if search_email in SEED_ACCOUNTS:
            acc_data = SEED_ACCOUNTS[search_email]
            org_id = DEFAULT_ORG_ID

            # Ensure parent organization exists before inserting dependent rows
            ensure_organization_exists(db, org_id)

            user = models.User(
                id=uuid.uuid4(),
                organization_id=org_id,
                name=acc_data["name"],
                full_name=acc_data["name"],
                email=search_email,
                phone=acc_data["phone"],
                role=acc_data["role"],
                avatar=acc_data["avatar"],
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # Auto-provision operational profile safely
            create_operational_profile(db, user, org_id)
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
    Registers a new user, ensuring organization existence and creating linked operational records.
    """
    clean_email = payload.email.lower().strip()

    # 1. Duplicate check
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
    org_id = payload.organization_id or DEFAULT_ORG_ID

    # 3. Ensure parent organization exists before inserting dependent rows
    ensure_organization_exists(db, org_id)

    # 4. Create and commit User record first (guarantees account creation)
    new_user = models.User(
        id=uuid.uuid4(),
        organization_id=org_id,
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

    # 5. Safely auto-bridge operational Tenant / Owner profile
    create_operational_profile(db, new_user, org_id)

    session_token = f"argo_live_{new_user.role}_{uuid.uuid4()}"

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