import uuid
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from .. import models, schemas

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures the Organization exists in DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


def find_owner_by_identifier(db: Session, owner_id: str, organization_id: uuid.UUID):
    """Robustly locates an owner by UUID, user_id, or custom own_id string."""
    clean_id = owner_id.strip()
    try:
        parsed_uuid = uuid.UUID(clean_id)
        owner = db.scalar(
            select(models.Owner).where(
                or_(
                    models.Owner.id == parsed_uuid,
                    models.Owner.user_id == parsed_uuid
                ),
                models.Owner.organization_id == organization_id
            )
        )
        if owner:
            return owner
    except ValueError:
        pass

    if hasattr(models.Owner, "own_id"):
        owner = db.scalar(
            select(models.Owner).where(
                models.Owner.own_id.ilike(clean_id),
                models.Owner.organization_id == organization_id
            )
        )
        if owner:
            return owner

    # Fallback lookup by email or virtual user match
    owner = db.scalar(
        select(models.Owner).where(
            models.Owner.email.ilike(clean_id),
            models.Owner.organization_id == organization_id
        )
    )
    if owner:
        return owner

    # Check registered users table directly if not found in owners table
    user = db.scalar(
        select(models.User).where(
            models.User.email.ilike(clean_id),
            models.User.organization_id == organization_id
        )
    )
    if user:
        virtual_owner = models.Owner(
            id=user.id,
            organization_id=organization_id,
            name=user.name or user.full_name or "Registered Owner",
            email=user.email,
            phone=user.phone or "",
            status="Active"
        )
        if hasattr(virtual_owner, "user_id"):
            virtual_owner.user_id = user.id
        return virtual_owner

    return None


# ---------------------------------------------------------------------
# FRACTIONAL EQUITY OWNERSHIP ENDPOINTS
# ---------------------------------------------------------------------
@router.get("/shares/all", response_model=List[schemas.PropertyOwnershipSchema])
def read_property_ownerships(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    property_id: Optional[uuid.UUID] = Query(default=None),
    owner_id: Optional[uuid.UUID] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)
    stmt = select(models.PropertyOwnership).where(
        models.PropertyOwnership.organization_id == organization_id
    )
    if property_id:
        stmt = stmt.where(models.PropertyOwnership.property_id == property_id)
    if owner_id:
        stmt = stmt.where(models.PropertyOwnership.owner_id == owner_id)

    return list(db.scalars(stmt).all())


@router.post("/shares/assign", response_model=schemas.PropertyOwnershipSchema, status_code=status.HTTP_201_CREATED)
def assign_property_ownership(
    share_in: schemas.PropertyOwnershipCreate,
    db: Session = Depends(get_db)
):
    org_id = getattr(share_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    share_data = share_in.model_dump(exclude_unset=True) if hasattr(share_in, "model_dump") else share_in.dict(exclude_unset=True)
    if "id" not in share_data or not share_data["id"]:
        share_data["id"] = uuid.uuid4()
    share_data["organization_id"] = org_id

    db_share = models.PropertyOwnership(**share_data)
    db.add(db_share)
    db.commit()
    db.refresh(db_share)
    return db_share


# ---------------------------------------------------------------------
# OWNERS ENDPOINTS
# ---------------------------------------------------------------------
@router.get("/", response_model=List[schemas.OwnerSchema])
def read_owners(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)
    
    # 1. Fetch existing explicit owner profiles
    owners = list(db.scalars(select(models.Owner).where(models.Owner.organization_id == organization_id)).all())
    
    existing_user_ids = {str(o.user_id) for o in owners if getattr(o, 'user_id', None)}
    existing_emails = {(o.email or '').lower().strip() for o in owners if getattr(o, 'email', None)}

    # 2. Directly grab ALL users registered with owner, investor, or property_owner roles from index.html
    owner_users = db.scalars(
        select(models.User).where(
            models.User.organization_id == organization_id,
            or_(
                models.User.role.ilike("%owner%"),
                models.User.role.ilike("%investor%"),
                models.User.role.ilike("%property_owner%")
            )
        )
    ).all()

    # 3. Merge them on the fly into the response feed so they appear instantly
    for u in owner_users:
        u_email = (u.email or '').lower().strip()
        if str(u.id) not in existing_user_ids and u_email not in existing_emails:
            uname = getattr(u, 'name', None) or getattr(u, 'full_name', None) or 'Registered Owner'
            uphone = getattr(u, 'phone', '') or ''
            
            virtual_owner = models.Owner(
                id=u.id,
                organization_id=organization_id,
                name=uname,
                email=u.email,
                phone=uphone,
                status='Active'
            )
            if hasattr(virtual_owner, 'user_id'):
                virtual_owner.user_id = u.id
            if hasattr(virtual_owner, 'own_id'):
                virtual_owner.own_id = f"OWN-{str(u.id)[:6].upper()}"
            if hasattr(virtual_owner, 'type'):
                virtual_owner.type = 'Individual'
                
            owners.append(virtual_owner)

    if status_filter:
        owners = [o for o in owners if status_filter.lower() in (o.status or '').lower()]

    if search:
        s_term = search.strip().lower()
        owners = [o for o in owners if s_term in (o.name or '').lower() or s_term in (o.email or '').lower()]

    return owners


@router.post("/", response_model=schemas.OwnerSchema, status_code=status.HTTP_201_CREATED)
def create_owner(owner_in: schemas.OwnerCreate, db: Session = Depends(get_db)):
    org_id = getattr(owner_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    clean_email = owner_in.email.lower().strip() if owner_in.email else None
    own_id = getattr(owner_in, "own_id", None) or f"OWN-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

    # Scoped duplicate check
    duplicate_filters = []
    if own_id and hasattr(models.Owner, "own_id"):
        duplicate_filters.append(models.Owner.own_id.ilike(own_id))
    if clean_email and hasattr(models.Owner, "email"):
        duplicate_filters.append(models.Owner.email.ilike(clean_email))

    if duplicate_filters:
        existing = db.scalar(
            select(models.Owner).where(
                models.Owner.organization_id == org_id,
                or_(*duplicate_filters)
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An owner with this ID or email already exists in this organization."
            )

    owner_data = owner_in.model_dump(exclude_unset=True) if hasattr(owner_in, "model_dump") else owner_in.dict(exclude_unset=True)
    if "id" not in owner_data or not owner_data["id"]:
        owner_data["id"] = uuid.uuid4()
    owner_data["organization_id"] = org_id
    if clean_email:
        owner_data["email"] = clean_email
    if "own_id" not in owner_data and hasattr(models.Owner, "own_id"):
        owner_data["own_id"] = own_id
    if "status" not in owner_data or not owner_data["status"]:
        owner_data["status"] = "Active"

    db_owner = models.Owner(**owner_data)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner


@router.get("/{owner_id}", response_model=schemas.OwnerSchema)
def get_owner(
    owner_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    owner = find_owner_by_identifier(db, owner_id, organization_id)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Owner not found."
        )
    return owner


@router.put("/{owner_id}", response_model=schemas.OwnerSchema)
@router.patch("/{owner_id}", response_model=schemas.OwnerSchema)
def update_owner(
    owner_id: str,
    owner_update: schemas.OwnerUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    db_owner = find_owner_by_identifier(db, owner_id, organization_id)
    if not db_owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Owner not found."
        )

    update_data = owner_update.model_dump(exclude_unset=True) if hasattr(owner_update, "model_dump") else owner_update.dict(exclude_unset=True)
    
    if "email" in update_data and update_data["email"]:
        clean_email = update_data["email"].lower().strip()
        update_data["email"] = clean_email
        if clean_email != (db_owner.email or "").lower().strip():
            email_check = db.scalar(
                select(models.Owner).where(
                    models.Owner.organization_id == organization_id,
                    models.Owner.email.ilike(clean_email),
                    models.Owner.id != db_owner.id
                )
            )
            if email_check:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Email '{clean_email}' is already assigned to another owner."
                )

    for field, value in update_data.items():
        if hasattr(db_owner, field):
            setattr(db_owner, field, value)

    db.commit()
    db.refresh(db_owner)
    return db_owner


@router.delete("/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owner(
    owner_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    db_owner = find_owner_by_identifier(db, owner_id, organization_id)
    if not db_owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Owner not found."
        )

    try:
        db.delete(db_owner)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete owner because they hold active property ownership shares."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting owner: {str(e)}"
        )

    return None