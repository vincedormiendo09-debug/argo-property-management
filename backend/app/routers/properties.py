import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

# Default Organization UUID for local sandbox testing
DEFAULT_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in local DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="Default Sandbox Org")
        db.add(sandbox_org)
        db.commit()


# 1. GET /api/properties/ - Read properties scoped by organization_id
@router.get("/", response_model=List[schemas.PropertySchema])
def read_properties(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    # Query properties strictly scoped to the tenant
    stmt = select(models.Property).where(models.Property.organization_id == organization_id)
    props = list(db.scalars(stmt).all())

    # Seed default sandbox properties if database is empty for this org
    if not props:
        default_props = [
            models.Property(
                id=uuid.uuid4(),
                organization_id=organization_id,
                code="PROP-001",
                name="Sunrise Property",
                type="Residential",
                location="Parañaque, Metro Manila",
                status="Active"
            ),
            models.Property(
                id=uuid.uuid4(),
                organization_id=organization_id,
                code="PROP-002",
                name="Greenfield Apartments",
                type="Residential",
                location="Quezon City, Metro Manila",
                status="Active"
            )
        ]
        db.add_all(default_props)
        db.commit()
        props = list(db.scalars(stmt).all())

    return props


# 2. POST /api/properties/ - Create a property with org-scoped duplicate check
@router.post("/", response_model=schemas.PropertySchema, status_code=status.HTTP_201_CREATED)
def create_property(prop_in: schemas.PropertyCreate, db: Session = Depends(get_db)):
    ensure_sandbox_organization(db, prop_in.organization_id)

    # Scoped duplicate check: (organization_id, code) must be unique
    existing_stmt = select(models.Property).where(
        models.Property.organization_id == prop_in.organization_id,
        models.Property.code == prop_in.code
    )
    existing = db.scalar(existing_stmt)

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Property code '{prop_in.code}' already exists for this organization."
        )

    db_prop = models.Property(
        id=uuid.uuid4(),
        organization_id=prop_in.organization_id,
        code=prop_in.code,
        name=prop_in.name,
        type=prop_in.type,
        location=prop_in.location,
        status=prop_in.status,
        created_by=prop_in.created_by
    )

    db.add(db_prop)
    db.commit()
    db.refresh(db_prop)
    return db_prop


# 3. GET /api/properties/{property_id} - Fetch a single property by UUID
@router.get("/{property_id}", response_model=schemas.PropertySchema)
def get_property(
    property_id: uuid.UUID,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.Property).where(
        models.Property.id == property_id,
        models.Property.organization_id == organization_id
    )
    prop = db.scalar(stmt)

    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found."
        )

    return prop