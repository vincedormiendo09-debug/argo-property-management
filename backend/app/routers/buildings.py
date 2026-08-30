import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from .. import models, schemas

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

# Default Organization UUID matching schema.sql and seed.py
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


# 1. GET /api/buildings/ - Read real buildings scoped by organization_id with filter and search
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
        stmt = stmt.where(models.Building.status.ilike(f"%{status_filter.strip()}%"))

    if search:
        search_term = search.strip()
        search_terms = [
            models.Building.name.ilike(f"%{search_term}%"),
            models.Building.code.ilike(f"%{search_term}%")
        ]
        stmt = stmt.where(or_(*search_terms))

    return list(db.scalars(stmt).all())


# 2. POST /api/buildings/ - Create building with unit auto-provisioning
@router.post("/", response_model=schemas.BuildingSchema, status_code=status.HTTP_201_CREATED)
def create_building(bldg_in: schemas.BuildingCreate, db: Session = Depends(get_db)):
    org_id = getattr(bldg_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    # 1. Verify parent property exists
    prop_id = getattr(bldg_in, "property_id", None)
    if not prop_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A parent Property ID is required to create a building."
        )

    prop = db.scalar(
        select(models.Property).where(
            models.Property.id == prop_id,
            models.Property.organization_id == org_id
        )
    )
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property with ID '{prop_id}' was not found in this organization."
        )

    bldg_code = (bldg_in.code or f"BLDG-{str(uuid.uuid4())[:4].upper()}").strip()

    # 2. Scoped duplicate check: (organization_id, code) must be unique
    existing = db.scalar(
        select(models.Building).where(
            models.Building.organization_id == org_id,
            models.Building.code.ilike(bldg_code)
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
    bldg_data["property_id"] = prop_id
    bldg_data["code"] = bldg_code
    bldg_data["total_units"] = calculated_total_units
    bldg_data["floor_distribution"] = floor_dist
    if "status" not in bldg_data or not bldg_data["status"]:
        bldg_data["status"] = "ACTIVE"

    db_bldg = models.Building(**bldg_data)
    db.add(db_bldg)

    # 3. Automatically provision corresponding unit rows in inventory
    units_created = 0
    for floor_key, unit_count in floor_dist.items():
        floor_num_str = "".join(filter(str.isdigit, floor_key)) or "1"
        f_num = int(floor_num_str)

        for u_idx in range(1, int(unit_count) + 1):
            unit_num = f"{f_num}0{u_idx}"
            existing_unit = db.scalar(
                select(models.Unit).where(
                    models.Unit.organization_id == org_id,
                    models.Unit.property_id == db_bldg.property_id,
                    models.Unit.unit_no.ilike(unit_num)
                )
            )
            if not existing_unit:
                unit_kwargs = {
                    "id": uuid.uuid4(),
                    "organization_id": org_id,
                    "property_id": db_bldg.property_id,
                    "unit_no": unit_num,
                    "type": "Standard Residential",
                    "status": "Available",
                    "sqm": 45.0
                }
                if hasattr(models.Unit, "building_id"):
                    unit_kwargs["building_id"] = bldg_id
                if hasattr(models.Unit, "floor"):
                    unit_kwargs["floor"] = floor_key
                if hasattr(models.Unit, "rent"):
                    unit_kwargs["rent"] = 15000.00
                elif hasattr(models.Unit, "rent_amount"):
                    unit_kwargs["rent_amount"] = 15000.00
                if hasattr(models.Unit, "subtitle"):
                    unit_kwargs["subtitle"] = f"{floor_key} · Standard Unit"

                db.add(models.Unit(**unit_kwargs))
                units_created += 1

    # Update parent property's units count counter
    if hasattr(prop, "units_count"):
        prop.units_count = (prop.units_count or 0) + units_created

    db.commit()
    db.refresh(db_bldg)
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
            models.Building.code.ilike(building_id.strip()),
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
            models.Building.code.ilike(building_id.strip()),
            models.Building.organization_id == organization_id
        )

    db_bldg = db.scalar(stmt)
    if not db_bldg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found."
        )

    update_data = bldg_update.model_dump(exclude_unset=True) if hasattr(bldg_update, "model_dump") else bldg_update.dict(exclude_unset=True)

    # Scoped duplicate check if code is being modified
    if "code" in update_data and update_data["code"]:
        clean_code = update_data["code"].strip()
        update_data["code"] = clean_code
        if clean_code.lower() != (db_bldg.code or "").lower():
            code_check = db.scalar(
                select(models.Building).where(
                    models.Building.organization_id == organization_id,
                    models.Building.code.ilike(clean_code),
                    models.Building.id != db_bldg.id
                )
            )
            if code_check:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Building code '{clean_code}' is already in use."
                )

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
            models.Building.code.ilike(building_id.strip()),
            models.Building.organization_id == organization_id
        )

    db_bldg = db.scalar(stmt)
    if not db_bldg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found."
        )

    try:
        # Check if units inside this building have active leases attached
        building_units = db.scalars(
            select(models.Unit).where(models.Unit.building_id == db_bldg.id)
        ).all()
        
        unit_ids = [u.id for u in building_units]
        if unit_ids:
            active_leases = db.scalars(
                select(models.Lease).where(models.Lease.unit_id.in_(unit_ids))
            ).all()
            if active_leases:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete this building because one or more units have active lease agreements attached."
                )

            # Safely delete dependent units
            for u in building_units:
                db.delete(u)

        db.delete(db_bldg)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete this building due to foreign key restrictions with active records."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting building: {str(e)}"
        )

    return None