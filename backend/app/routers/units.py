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


def ensure_sandbox_property(db: Session, org_id: uuid.UUID) -> models.Property:
    """Ensures at least one Property exists to attach default units to."""
    ensure_sandbox_organization(db, org_id)
    prop = db.scalar(select(models.Property).where(models.Property.organization_id == org_id))
    if not prop:
        prop = models.Property(
            id=uuid.uuid4(),
            organization_id=org_id,
            code="PROP-001",
            name="Sunrise Property",
            type="Residential",
            location="Parañaque, Metro Manila",
            status="Active"
        )
        db.add(prop)
        db.commit()
        db.refresh(prop)
    return prop


# 1. GET /api/units/ - Read units scoped by organization_id (optional property_id filter)
@router.get("/", response_model=List[schemas.UnitSchema])
def read_units(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    property_id: Optional[uuid.UUID] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Unit).where(models.Unit.organization_id == organization_id)
    if property_id:
        stmt = stmt.where(models.Unit.property_id == property_id)

    units = list(db.scalars(stmt).all())

    # Seed default sandbox units if database is empty for this org
    if not units and not property_id:
        parent_prop = ensure_sandbox_property(db, organization_id)
        default_units = [
            models.Unit(
                id=uuid.uuid4(),
                organization_id=organization_id,
                property_id=parent_prop.id,
                unit_no="Unit 101",
                type="1BR",
                rent=15000.0,
                status="OCCUPIED"
            ),
            models.Unit(
                id=uuid.uuid4(),
                organization_id=organization_id,
                property_id=parent_prop.id,
                unit_no="Unit 202",
                type="2BR",
                rent=22000.0,
                status="VACANT"
            )
        ]
        db.add_all(default_units)
        db.commit()
        units = list(db.scalars(stmt).all())

    return units


# 2. POST /api/units/ - Create a new unit with org + property validation
@router.post("/", response_model=schemas.UnitSchema, status_code=status.HTTP_201_CREATED)
def create_unit(unit_in: schemas.UnitCreate, db: Session = Depends(get_db)):
    ensure_sandbox_organization(db, unit_in.organization_id)

    # 1. Verify parent property exists under this organization
    prop_stmt = select(models.Property).where(
        models.Property.id == unit_in.property_id,
        models.Property.organization_id == unit_in.organization_id
    )
    parent_prop = db.scalar(prop_stmt)
    if not parent_prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property with ID '{unit_in.property_id}' not found in this organization."
        )

    # 2. Scoped duplicate check: (organization_id, property_id, unit_no) must be unique
    dup_stmt = select(models.Unit).where(
        models.Unit.organization_id == unit_in.organization_id,
        models.Unit.property_id == unit_in.property_id,
        models.Unit.unit_no == unit_in.unit_no
    )
    existing = db.scalar(dup_stmt)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unit '{unit_in.unit_no}' already exists for this property."
        )

    # 3. Save new unit
    db_unit = models.Unit(
        id=uuid.uuid4(),
        organization_id=unit_in.organization_id,
        property_id=unit_in.property_id,
        unit_no=unit_in.unit_no,
        type=unit_in.type,
        rent=unit_in.rent,
        status=unit_in.status,
        created_by=unit_in.created_by
    )

    db.add(db_unit)
    db.commit()
    db.refresh(db_unit)
    return db_unit


# 3. GET /api/units/{unit_id} - Fetch a single unit by UUID
@router.get("/{unit_id}", response_model=schemas.UnitSchema)
def get_unit(
    unit_id: uuid.UUID,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.Unit).where(
        models.Unit.id == unit_id,
        models.Unit.organization_id == organization_id
    )
    unit = db.scalar(stmt)

    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit not found."
        )

    return unit