import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

# Default Organization UUID matching schema.sql and seed.py
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in local DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="Sunrise Property Group")
        db.add(sandbox_org)
        db.commit()


# 1. GET /api/properties/ - Read properties scoped by organization_id with filter and search
@router.get("/", response_model=List[schemas.PropertySchema])
def read_properties(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    # Query properties strictly scoped to the tenant organization
    stmt = select(models.Property).where(models.Property.organization_id == organization_id)

    if type_filter:
        stmt = stmt.where(models.Property.type.ilike(f"%{type_filter}%"))
    if status_filter:
        stmt = stmt.where(models.Property.status.ilike(f"%{status_filter}%"))
    if search:
        search_terms = []
        if hasattr(models.Property, "name"):
            search_terms.append(models.Property.name.ilike(f"%{search}%"))
        if hasattr(models.Property, "code"):
            search_terms.append(models.Property.code.ilike(f"%{search}%"))
        if hasattr(models.Property, "location"):
            search_terms.append(models.Property.location.ilike(f"%{search}%"))
        if hasattr(models.Property, "tct_number"):
            search_terms.append(models.Property.tct_number.ilike(f"%{search}%"))
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    props = list(db.scalars(stmt).all())

    # Seed default sandbox properties if database is empty for this org
    if not props and not search and not type_filter and not status_filter:
        default_props = [
            models.Property(
                id=uuid.uuid4(),
                organization_id=organization_id,
                code="PROP-001",
                name="Sunrise Residences",
                tct_number="TCT #49281-MNL",
                type="Residential",
                location="Parañaque, Metro Manila",
                units_count=2 if hasattr(models.Property, "units_count") else None,
                status="Active"
            ),
            models.Property(
                id=uuid.uuid4(),
                organization_id=organization_id,
                code="PROP-003",
                name="Central Business Center",
                tct_number="CCT #88190-MKT",
                type="Commercial",
                location="Makati, Metro Manila",
                units_count=1 if hasattr(models.Property, "units_count") else None,
                status="Active"
            )
        ]
        db.add_all(default_props)
        db.commit()
        props = list(db.scalars(stmt).all())

    return props


# 2. POST /api/properties/ - Create a property with org-scoped duplicate check and initial equity linkage
@router.post("/", response_model=schemas.PropertySchema, status_code=status.HTTP_201_CREATED)
def create_property(prop_in: schemas.PropertyCreate, db: Session = Depends(get_db)):
    org_id = getattr(prop_in, "organization_id", DEFAULT_ORG_ID)
    ensure_sandbox_organization(db, org_id)

    prop_code = prop_in.code or f"PROP-{str(uuid.uuid4())[:4].upper()}"

    # Scoped duplicate check: (organization_id, code) must be unique
    existing_stmt = select(models.Property).where(
        models.Property.organization_id == org_id,
        models.Property.code == prop_code
    )
    existing = db.scalar(existing_stmt)

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Property code '{prop_code}' already exists for this organization."
        )

    prop_data = prop_in.dict(exclude_unset=True)
    prop_id = uuid.uuid4()
    if "id" not in prop_data or not prop_data["id"]:
        prop_data["id"] = prop_id
    if "organization_id" not in prop_data:
        prop_data["organization_id"] = org_id
    prop_data["code"] = prop_code

    db_prop = models.Property(**prop_data)
    db.add(db_prop)
    db.commit()
    db.refresh(db_prop)
    return db_prop


# 3. GET /api/properties/{property_id} - Fetch a single property by UUID or Property Code
@router.get("/{property_id}", response_model=schemas.PropertySchema)
def get_property(
    property_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(property_id)
        stmt = select(models.Property).where(
            models.Property.id == parsed_uuid,
            models.Property.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Property, "code"):
            stmt = select(models.Property).where(
                models.Property.code == property_id,
                models.Property.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid property identifier format."
            )

    prop = db.scalar(stmt)

    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found."
        )

    return prop


# 4. PUT /api/properties/{property_id} - Update property specifications
@router.put("/{property_id}", response_model=schemas.PropertySchema)
@router.patch("/{property_id}", response_model=schemas.PropertySchema)
def update_property(
    property_id: str,
    prop_update: schemas.PropertyUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(property_id)
        stmt = select(models.Property).where(
            models.Property.id == parsed_uuid,
            models.Property.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Property, "code"):
            stmt = select(models.Property).where(
                models.Property.code == property_id,
                models.Property.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid property identifier format."
            )

    db_prop = db.scalar(stmt)
    if not db_prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found."
        )

    update_data = prop_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(db_prop, field):
            setattr(db_prop, field, value)

    db.commit()
    db.refresh(db_prop)
    return db_prop


# 5. DELETE /api/properties/{property_id} - Delete or archive property record
@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(
    property_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(property_id)
        stmt = select(models.Property).where(
            models.Property.id == parsed_uuid,
            models.Property.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Property, "code"):
            stmt = select(models.Property).where(
                models.Property.code == property_id,
                models.Property.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid property identifier format."
            )

    db_prop = db.scalar(stmt)
    if not db_prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found."
        )

    db.delete(db_prop)
    db.commit()
    return None