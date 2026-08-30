import uuid
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


def sync_owner_users_to_owners(db: Session, org_id: uuid.UUID):
    """
    Auto-bridges registered users with role 'owner' into the owners table
    so registered owner accounts appear in dropdowns and directory views.
    """
    try:
        owner_users = db.scalars(
            select(models.User).where(
                models.User.organization_id == org_id,
                or_(
                    models.User.role.ilike("%owner%"),
                    models.User.role.ilike("%investor%")
                )
            )
        ).all()

        for u in owner_users:
            if not u.email:
                continue
            clean_email = u.email.lower().strip()
            existing_owner = db.scalar(
                select(models.Owner).where(
                    models.Owner.organization_id == org_id,
                    models.Owner.email.ilike(clean_email)
                )
            )
            if not existing_owner:
                name_parts = (u.name or "Property Owner").split(maxsplit=1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ""

                owner_data = {
                    "id": uuid.uuid4(),
                    "organization_id": org_id,
                    "email": clean_email,
                    "phone": u.phone or "",
                    "status": "Active"
                }
                if hasattr(models.Owner, "user_id"):
                    owner_data["user_id"] = u.id
                if hasattr(models.Owner, "name"):
                    owner_data["name"] = u.name or "Property Owner"
                if hasattr(models.Owner, "full_name"):
                    owner_data["full_name"] = u.name or "Property Owner"
                if hasattr(models.Owner, "first_name"):
                    owner_data["first_name"] = first_name
                if hasattr(models.Owner, "last_name"):
                    owner_data["last_name"] = last_name
                if hasattr(models.Owner, "own_id"):
                    owner_data["own_id"] = f"OWN-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"
                if hasattr(models.Owner, "type"):
                    owner_data["type"] = "Individual"

                db.add(models.Owner(**owner_data))
        db.commit()
    except Exception as err:
        db.rollback()
        logger.warning(f"Owner auto-sync notice: {err}")


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
    
    # Sync registered owner users before fetching
    sync_owner_users_to_owners(db, organization_id)

    stmt = select(models.Owner).where(models.Owner.organization_id == organization_id)

    if status_filter:
        stmt = stmt.where(models.Owner.status.ilike(f"%{status_filter.strip()}%"))

    if search:
        search_term = search.strip()
        search_terms = []
        if hasattr(models.Owner, "name"):
            search_terms.append(models.Owner.name.ilike(f"%{search_term}%"))
        if hasattr(models.Owner, "full_name"):
            search_terms.append(models.Owner.full_name.ilike(f"%{search_term}%"))
        if hasattr(models.Owner, "email"):
            search_terms.append(models.Owner.email.ilike(f"%{search_term}%"))
        if hasattr(models.Owner, "phone"):
            search_terms.append(models.Owner.phone.ilike(f"%{search_term}%"))
        if hasattr(models.Owner, "own_id"):
            search_terms.append(models.Owner.own_id.ilike(f"%{search_term}%"))
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    return list(db.scalars(stmt).all())


@router.post("/", response_model=schemas.OwnerSchema, status_code=status.HTTP_201_CREATED)
def create_owner(owner_in: schemas.OwnerCreate, db: Session = Depends(get_db)):
    org_id = getattr(owner_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    clean_email = owner_in.email.lower().strip() if owner_in.email else None
    own_id = owner_in.own_id or f"OWN-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

    # Check for duplicate own_id or email
    duplicate_filters = []
    if own_id and hasattr(models.Owner, "own_id"):
        duplicate_filters.append(models.Owner.own_id == own_id)
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
                detail=f"An owner with this ID or email already exists in this organization."
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
    try:
        parsed_uuid = uuid.UUID(owner_id)
        stmt = select(models.Owner).where(
            models.Owner.id == parsed_uuid,
            models.Owner.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Owner, "own_id"):
            stmt = select(models.Owner).where(
                models.Owner.own_id == owner_id.strip(),
                models.Owner.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid owner identifier format."
            )

    owner = db.scalar(stmt)
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found.")
    return owner


@router.put("/{owner_id}", response_model=schemas.OwnerSchema)
@router.patch("/{owner_id}", response_model=schemas.OwnerSchema)
def update_owner(
    owner_id: str,
    owner_update: schemas.OwnerUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(owner_id)
        stmt = select(models.Owner).where(
            models.Owner.id == parsed_uuid,
            models.Owner.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Owner, "own_id"):
            stmt = select(models.Owner).where(
                models.Owner.own_id == owner_id.strip(),
                models.Owner.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid owner identifier format."
            )

    db_owner = db.scalar(stmt)
    if not db_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found.")

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
    try:
        parsed_uuid = uuid.UUID(owner_id)
        stmt = select(models.Owner).where(
            models.Owner.id == parsed_uuid,
            models.Owner.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Owner, "own_id"):
            stmt = select(models.Owner).where(
                models.Owner.own_id == owner_id.strip(),
                models.Owner.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid owner identifier format."
            )

    db_owner = db.scalar(stmt)
    if not db_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found.")

    db.delete(db_owner)
    db.commit()
    return None