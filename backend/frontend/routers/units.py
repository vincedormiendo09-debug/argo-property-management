import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
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


def find_unit_by_identifier(db: Session, unit_id: str, organization_id: uuid.UUID):
    """Robustly resolves a unit by UUID, exact unit_no, normalized slug, or unit_number."""
    # 1. Try parsing as UUID
    try:
        parsed_uuid = uuid.UUID(unit_id)
        unit = db.scalar(
            select(models.Unit).where(
                models.Unit.id == parsed_uuid,
                models.Unit.organization_id == organization_id
            )
        )
        if unit:
            return unit
    except ValueError:
        pass

    if not hasattr(models.Unit, "unit_no"):
        return None

    # 2. Exact match on unit_no
    unit = db.scalar(
        select(models.Unit).where(
            models.Unit.unit_no.ilike(unit_id.strip()),
            models.Unit.organization_id == organization_id
        )
    )
    if unit:
        return unit

    # 3. Normalized match (e.g., "unit-101" -> "Unit 101")
    normalized_name = unit_id.replace("-", " ").title().strip()
    unit = db.scalar(
        select(models.Unit).where(
            models.Unit.unit_no.ilike(normalized_name),
            models.Unit.organization_id == organization_id
        )
    )
    if unit:
        return unit

    # 4. Match on unit_number if present in model
    if hasattr(models.Unit, "unit_number"):
        unit = db.scalar(
            select(models.Unit).where(
                or_(
                    models.Unit.unit_number.ilike(unit_id.strip()),
                    models.Unit.unit_number.ilike(normalized_name)
                ),
                models.Unit.organization_id == organization_id
            )
        )
        if unit:
            return unit

    # 5. Substring fallback match
    unit = db.scalar(
        select(models.Unit).where(
            models.Unit.unit_no.ilike(f"%{unit_id.strip()}%"),
            models.Unit.organization_id == organization_id
        )
    )
    if unit:
        return unit

    return None


# 1. GET /api/units/ - Read real units from DB with cascading filters
@router.get("/", response_model=List[schemas.UnitSchema])
def read_units(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    property_id: Optional[uuid.UUID] = Query(default=None),
    building_id: Optional[uuid.UUID] = Query(default=None),
    floor_filter: Optional[str] = Query(default=None, alias="floor"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Unit).where(models.Unit.organization_id == organization_id)
    
    if property_id:
        stmt = stmt.where(models.Unit.property_id == property_id)
    if building_id and hasattr(models.Unit, "building_id"):
        stmt = stmt.where(models.Unit.building_id == building_id)
    if floor_filter and hasattr(models.Unit, "floor"):
        stmt = stmt.where(models.Unit.floor.ilike(f"%{floor_filter.strip()}%"))
    if status_filter:
        stmt = stmt.where(models.Unit.status.ilike(f"%{status_filter.strip()}%"))
    if type_filter and hasattr(models.Unit, "type"):
        stmt = stmt.where(models.Unit.type.ilike(f"%{type_filter.strip()}%"))

    if search:
        search_term = search.strip()
        search_terms = []
        if hasattr(models.Unit, "unit_no"):
            search_terms.append(models.Unit.unit_no.ilike(f"%{search_term}%"))
        if hasattr(models.Unit, "subtitle"):
            search_terms.append(models.Unit.subtitle.ilike(f"%{search_term}%"))
        if hasattr(models.Unit, "floor"):
            search_terms.append(models.Unit.floor.ilike(f"%{search_term}%"))
        if hasattr(models.Unit, "type"):
            search_terms.append(models.Unit.type.ilike(f"%{search_term}%"))
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    return list(db.scalars(stmt).all())


# 2. POST /api/units/ - Create a new unit
@router.post("/", response_model=schemas.UnitSchema, status_code=status.HTTP_201_CREATED)
def create_unit(unit_in: schemas.UnitCreate, db: Session = Depends(get_db)):
    org_id = getattr(unit_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    # 1. Verify parent property exists
    prop_id = getattr(unit_in, "property_id", None)
    if not prop_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A parent Property ID is required to create a unit."
        )

    prop_stmt = select(models.Property).where(
        models.Property.id == prop_id,
        models.Property.organization_id == org_id
    )
    parent_prop = db.scalar(prop_stmt)
    if not parent_prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property with ID '{prop_id}' was not found in this organization."
        )

    # 2. Scoped duplicate check: (organization_id, property_id, unit_no) must be unique
    unit_no_val = getattr(unit_in, "unit_no", "").strip()
    dup_stmt = select(models.Unit).where(
        models.Unit.organization_id == org_id,
        models.Unit.property_id == prop_id,
        models.Unit.unit_no.ilike(unit_no_val)
    )
    existing = db.scalar(dup_stmt)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unit '{unit_no_val}' already exists for this property."
        )

    # 3. Assemble and sanitize unit data
    unit_data = unit_in.model_dump(exclude_unset=True) if hasattr(unit_in, "model_dump") else unit_in.dict(exclude_unset=True)
    if "id" not in unit_data or not unit_data["id"]:
        unit_data["id"] = uuid.uuid4()
    if "organization_id" not in unit_data or not unit_data["organization_id"]:
        unit_data["organization_id"] = org_id
    unit_data["property_id"] = prop_id
    unit_data["unit_no"] = unit_no_val

    # Default occupancy status
    if "status" not in unit_data or not unit_data["status"]:
        unit_data["status"] = "Available"

    # Sync rent/rent_amount model field naming
    if "rent" in unit_data and hasattr(models.Unit, "rent_amount") and not hasattr(models.Unit, "rent"):
        unit_data["rent_amount"] = unit_data.pop("rent")
    elif "rent_amount" in unit_data and hasattr(models.Unit, "rent") and not hasattr(models.Unit, "rent_amount"):
        unit_data["rent"] = unit_data.pop("rent_amount")

    db_unit = models.Unit(**unit_data)
    db.add(db_unit)

    # Increment property unit counter if column exists
    if hasattr(parent_prop, "units_count"):
        parent_prop.units_count = (parent_prop.units_count or 0) + 1

    db.commit()
    db.refresh(db_unit)
    return db_unit


# 3. GET /api/units/{unit_id} - Fetch a single unit by UUID or Unit Number
@router.get("/{unit_id}", response_model=schemas.UnitSchema)
def get_unit(
    unit_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    unit = find_unit_by_identifier(db, unit_id, organization_id)
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit not found."
        )
    return unit


# 4. PUT & PATCH /api/units/{unit_id} - Update unit status (OCCUPIED <-> VACANT), rent, and specs
@router.put("/{unit_id}", response_model=schemas.UnitSchema)
@router.patch("/{unit_id}", response_model=schemas.UnitSchema)
def update_unit(
    unit_id: str,
    unit_update: schemas.UnitUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    db_unit = find_unit_by_identifier(db, unit_id, organization_id)
    if not db_unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit not found."
        )

    update_data = unit_update.model_dump(exclude_unset=True) if hasattr(unit_update, "model_dump") else unit_update.dict(exclude_unset=True)

    # Normalize incoming status string
    if "status" in update_data and update_data["status"]:
        s = str(update_data["status"]).strip().upper()
        if s in ("AVAILABLE", "VACANT"):
            update_data["status"] = "Available"
        elif s in ("OCCUPIED", "LEASED"):
            update_data["status"] = "Occupied"
        elif s in ("MAINTENANCE", "UNDER_MAINTENANCE"):
            update_data["status"] = "Maintenance"

    for field, value in update_data.items():
        if hasattr(db_unit, field):
            setattr(db_unit, field, value)
        elif field == "rent" and hasattr(db_unit, "rent_amount"):
            setattr(db_unit, "rent_amount", value)
        elif field == "rent_amount" and hasattr(db_unit, "rent"):
            setattr(db_unit, "rent", value)

    db.commit()
    db.refresh(db_unit)
    return db_unit


# 5. DELETE /api/units/{unit_id} - Remove unit from inventory
@router.delete("/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unit(
    unit_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    db_unit = find_unit_by_identifier(db, unit_id, organization_id)
    if not db_unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit not found."
        )

    try:
        # Decrement property counter if column exists
        if db_unit.property_id:
            prop = db.scalar(select(models.Property).where(models.Property.id == db_unit.property_id))
            if prop and hasattr(prop, "units_count") and (prop.units_count or 0) > 0:
                prop.units_count -= 1

        db.delete(db_unit)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete this unit because active leases or invoice records are attached to it."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting unit: {str(e)}"
        )

    return None