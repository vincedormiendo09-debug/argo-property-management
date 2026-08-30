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
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


# 1. GET /api/buildings/ - Read buildings scoped by organization_id with filter and search
@router.get("/", response_model=List[schemas.BuildingSchema])
def read_buildings(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    property_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Building).where(models.Building.organization_id == organization_id)

    if property_id:
        try:
            p_uuid = uuid.UUID(property_id)
            stmt = stmt.where(models.Building.property_id == p_uuid)
        except ValueError:
            pass

    if status_filter:
        stmt = stmt.where(models.Building.status.ilike(f"%{status_filter}%"))

    if search:
        search_terms = [
            models.Building.name.ilike(f"%{search}%"),
            models.Building.code.ilike(f"%{search}%")
        ]
        stmt = stmt.where(or_(*search_terms))

    buildings = list(db.scalars(stmt).all())
    return buildings


# 2. POST /api/buildings/ - Create building with floor-by-floor unit distribution and auto-provisioning
@router.post("/", response_model=schemas.BuildingSchema, status_code=status.HTTP_201_CREATED)
def create_building(bldg_in: schemas.BuildingCreate, db: Session = Depends(get_db)):
    org_id = getattr(bldg_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    bldg_code = bldg_in.code or f"BLDG-{str(uuid.uuid4())[:4].upper()}"

    # Scoped duplicate check: (organization_id, code) must be unique
    existing = db.scalar(
        select(models.Building).where(
            models.Building.organization_id == org_id,
            models.Building.code == bldg_code
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Building code '{bldg_code}' already exists for this organization."
        )

    floors = bldg_in.floors or 1
    floor_dist = bldg_in.floor_distribution or {}

    if not floor_dist or not isinstance(floor_dist, dict):
        floor_dist = {f"Floor {i}": 4 for i in range(1, floors + 1)}

    calculated_total_units = sum(int(v) for v in floor_dist.values())

    bldg_id = uuid.uuid4()
    bldg_data = bldg_in.model_dump(exclude_unset=True) if hasattr(bldg_in, "model_dump") else bldg_in.dict(exclude_unset=True)
    
    bldg_data["id"] = bldg_id
    bldg_data["organization_id"] = org_id
    bldg_data["code"] = bldg_code
    bldg_data["total_units"] = calculated_total_units
    bldg_data["floor_distribution"] = floor_dist

    db_bldg = models.Building(**bldg_data)
    db.add(db_bldg)
    db.commit()
    db.refresh(db_bldg)

    # Automatically provision corresponding unit rows in property_units
    prop = db.scalar(select(models.Property).where(models.Property.id == db_bldg.property_id))
    prop_name = prop.name if prop else "Property Asset"

    for floor_key, unit_count in floor_dist.items():
        floor_num_str = "".join(filter(str.isdigit, floor_key)) or "1"
        f_num = int(floor_num_str)

        for u_idx in range(1, int(unit_count) + 1):
            unit_num = f"{f_num}0{u_idx}"
            existing_unit = db.scalar(
                select(models.Unit).where(
                    models.Unit.organization_id == org_id,
                    models.Unit.property_id == db_bldg.property_id,
                    models.Unit.unit_no == unit_num
                )
            )
            if not existing_unit:
                new_unit = models.Unit(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    property_id=db_bldg.property_id,
                    building_id=bldg_id,
                    unit_no=unit_num,
                    type="Standard Residential",
                    floor=floor_key,
                    sqm=45.0,
                    rent=15000.00,
                    status="VACANT",
                    subtitle=f"{floor_key} · Standard Unit"
                )
                db.add(new_unit)

    db.commit()
    return db_bldg


# 3. GET /api/buildings/{building_id} - Fetch a single building record
@router.get("/{building_id}", response_model=schemas.BuildingSchema)
def get_building(
    building_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(building_id)
        stmt = select(models.Building).where(
            models.Building.id == parsed_uuid,
            models.Building.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Building).where(
            models.Building.code == building_id,
            models.Building.organization_id == organization_id
        )

    bldg = db.scalar(stmt)
    if not bldg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found."
        )
    return bldg


# 4. PUT / PATCH /api/buildings/{building_id} - Update building specifications
@router.put("/{building_id}", response_model=schemas.BuildingSchema)
@router.patch("/{building_id}", response_model=schemas.BuildingSchema)
def update_building(
    building_id: str,
    bldg_update: schemas.BuildingUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(building_id)
        stmt = select(models.Building).where(
            models.Building.id == parsed_uuid,
            models.Building.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Building).where(
            models.Building.code == building_id,
            models.Building.organization_id == organization_id
        )

    db_bldg = db.scalar(stmt)
    if not db_bldg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found."
        )

    update_data = bldg_update.model_dump(exclude_unset=True) if hasattr(bldg_update, "model_dump") else bldg_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(db_bldg, field):
            setattr(db_bldg, field, value)

    db.commit()
    db.refresh(db_bldg)
    return db_bldg


# 5. DELETE /api/buildings/{building_id} - Cleanly delete building and associated units
@router.delete("/{building_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_building(
    building_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(building_id)
        stmt = select(models.Building).where(
            models.Building.id == parsed_uuid,
            models.Building.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Building).where(
            models.Building.code == building_id,
            models.Building.organization_id == organization_id
        )

    db_bldg = db.scalar(stmt)
    if not db_bldg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found."
        )

    # Safely delete dependent units first to avoid foreign key restriction errors
    db.query(models.Unit).where(models.Unit.building_id == db_bldg.id).delete()

    db.delete(db_bldg)
    db.commit()
    return None