import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="Sunrise Property Group")
        db.add(sandbox_org)
        db.commit()


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
    stmt = select(models.Owner).where(models.Owner.organization_id == organization_id)

    if status_filter:
        stmt = stmt.where(models.Owner.status.ilike(f"%{status_filter}%"))
    if search:
        search_terms = [
            models.Owner.name.ilike(f"%{search}%"),
            models.Owner.email.ilike(f"%{search}%"),
            models.Owner.phone.ilike(f"%{search}%"),
            models.Owner.own_id.ilike(f"%{search}%")
        ]
        stmt = stmt.where(or_(*search_terms))

    owners = list(db.scalars(stmt).all())

    # Fallback seed for sandbox testing if empty
    if not owners and not search and not status_filter:
        default_owner = models.Owner(
            id=uuid.uuid4(),
            organization_id=organization_id,
            own_id="OWN-2001",
            name="Don Ramon Santos",
            email="ramon.santos@owner.ph",
            phone="09183334444",
            type="INDIVIDUAL",
            status="ACTIVE"
        )
        db.add(default_owner)
        db.commit()
        owners = list(db.scalars(stmt).all())

    return owners


@router.post("/", response_model=schemas.OwnerSchema, status_code=status.HTTP_201_CREATED)
def create_owner(owner_in: schemas.OwnerCreate, db: Session = Depends(get_db)):
    org_id = getattr(owner_in, "organization_id", DEFAULT_ORG_ID)
    ensure_sandbox_organization(db, org_id)

    own_id = owner_in.own_id or f"OWN-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

    existing = db.scalar(
        select(models.Owner).where(
            models.Owner.organization_id == org_id,
            or_(models.Owner.own_id == own_id, models.Owner.email == owner_in.email)
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Owner with ID '{own_id}' or email '{owner_in.email}' already exists."
        )

    owner_data = owner_in.dict(exclude_unset=True)
    if "id" not in owner_data or not owner_data["id"]:
        owner_data["id"] = uuid.uuid4()
    owner_data["organization_id"] = org_id
    owner_data["own_id"] = own_id

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
        stmt = select(models.Owner).where(
            models.Owner.own_id == owner_id,
            models.Owner.organization_id == organization_id
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
        stmt = select(models.Owner).where(
            models.Owner.own_id == owner_id,
            models.Owner.organization_id == organization_id
        )

    db_owner = db.scalar(stmt)
    if not db_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found.")

    update_data = owner_update.dict(exclude_unset=True)
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
        stmt = select(models.Owner).where(
            models.Owner.own_id == owner_id,
            models.Owner.organization_id == organization_id
        )

    db_owner = db.scalar(stmt)
    if not db_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found.")

    db.delete(db_owner)
    db.commit()
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
    org_id = getattr(share_in, "organization_id", DEFAULT_ORG_ID)
    ensure_sandbox_organization(db, org_id)

    share_data = share_in.dict(exclude_unset=True)
    if "id" not in share_data or not share_data["id"]:
        share_data["id"] = uuid.uuid4()
    share_data["organization_id"] = org_id

    db_share = models.PropertyOwnership(**share_data)
    db.add(db_share)
    db.commit()
    db.refresh(db_share)
    return db_share
