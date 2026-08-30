import uuid
import logging
from datetime import datetime
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from .. import models, schemas

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def parse_org_id(org_id_raw: Optional[str]) -> uuid.UUID:
    """Safely converts string, null, or undefined organization IDs to valid UUIDs."""
    if not org_id_raw:
        return DEFAULT_ORG_ID
    clean = str(org_id_raw).strip().lower()
    if clean in ("undefined", "null", ""):
        return DEFAULT_ORG_ID
    try:
        return uuid.UUID(clean)
    except Exception:
        return DEFAULT_ORG_ID


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


def find_unit_by_identifier(db: Session, unit_id: str, organization_id: uuid.UUID):
    """Robustly resolves a unit by UUID, exact unit_no, normalized slug, or unit_number."""
    clean_id = unit_id.strip()

    # 1. Try parsing as UUID
    try:
        parsed_uuid = uuid.UUID(clean_id)
        unit = db.scalar(
            select(models.Unit).where(
                models.Unit.id == parsed_uuid,
                or_(
                    models.Unit.organization_id == organization_id,
                    models.Unit.organization_id.is_(None)
                )
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
            models.Unit.unit_no.ilike(clean_id),
            or_(
                models.Unit.organization_id == organization_id,
                models.Unit.organization_id.is_(None)
            )
        )
    )
    if unit:
        return unit

    # 3. Normalized match (e.g., "unit-101" -> "Unit 101")
    normalized_name = clean_id.replace("-", " ").title().strip()
    unit = db.scalar(
        select(models.Unit).where(
            models.Unit.unit_no.ilike(normalized_name),
            or_(
                models.Unit.organization_id == organization_id,
                models.Unit.organization_id.is_(None)
            )
        )
    )
    if unit:
        return unit

    # 4. Match on unit_number if present in model
    if hasattr(models.Unit, "unit_number"):
        unit = db.scalar(
            select(models.Unit).where(
                or_(
                    models.Unit.unit_number.ilike(clean_id),
                    models.Unit.unit_number.ilike(normalized_name)
                ),
                or_(
                    models.Unit.organization_id == organization_id,
                    models.Unit.organization_id.is_(None)
                )
            )
        )
        if unit:
            return unit

    return None


# ---------------------------------------------------------------------
# 1. GET UNITS (Matches both /api/units and /api/units/)
# ---------------------------------------------------------------------
@router.get("")
@router.get("/")
def read_units(
    organization_id: Optional[str] = Query(default=None),
    property_id: Optional[str] = Query(default=None),
    building_id: Optional[str] = Query(default=None),
    floor_filter: Optional[str] = Query(default=None, alias="floor"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    stmt = select(models.Unit).where(
        or_(
            models.Unit.organization_id == org_id,
            models.Unit.organization_id.is_(None)
        )
    )
    
    if property_id and property_id not in ("undefined", "null", ""):
        try:
            stmt = stmt.where(models.Unit.property_id == uuid.UUID(property_id))
        except ValueError:
            pass

    if building_id and building_id not in ("undefined", "null", "") and hasattr(models.Unit, "building_id"):
        try:
            stmt = stmt.where(models.Unit.building_id == uuid.UUID(building_id))
        except ValueError:
            pass

    if floor_filter and hasattr(models.Unit, "floor"):
        stmt = stmt.where(models.Unit.floor.ilike(f"%{floor_filter.strip()}%"))

    if status_filter:
        stmt = stmt.where(models.Unit.status.ilike(f"%{status_filter.strip()}%"))

    if type_filter and hasattr(models.Unit, "type"):
        stmt = stmt.where(models.Unit.type.ilike(f"%{type_filter.strip()}%"))

    units_list = list(db.scalars(stmt).all())

    # Lookup tables for relations
    props_map = {
        p.id: (getattr(p, "name", None) or getattr(p, "property_name", None) or "Property") 
        for p in db.scalars(select(models.Property)).all()
    }
    bldgs_map = {
        b.id: (getattr(b, "name", None) or "Building") 
        for b in db.scalars(select(models.Building)).all()
    }

    results: List[Dict[str, Any]] = []
    for u in units_list:
        u_id = str(u.id)
        p_id = u.property_id
        b_id = getattr(u, "building_id", None)
        rent_val = float(getattr(u, "rent", None) or getattr(u, "rent_amount", None) or 0.0)

        results.append({
            "id": u_id,
            "organization_id": str(getattr(u, "organization_id", None) or org_id),
            "property_id": str(p_id),
            "property_name": props_map.get(p_id, "Property Asset"),
            "building_id": str(b_id) if b_id else None,
            "building_name": bldgs_map.get(b_id, "") if b_id else "",
            "unit_no": getattr(u, "unit_no", f"UNIT-{u_id[:4].upper()}"),
            "unit_number": getattr(u, "unit_number", getattr(u, "unit_no", "")),
            "type": getattr(u, "type", "1-Bedroom Apartment") or "1-Bedroom Apartment",
            "floor": getattr(u, "floor", "1st Floor") or "1st Floor",
            "floor_number": int(getattr(u, "floor_number", 1) or 1),
            "sqm": float(getattr(u, "sqm", 45.0) or 45.0),
            "rent": rent_val,
            "rent_amount": rent_val,
            "status": getattr(u, "status", "Available") or "Available",
            "tenant_name": getattr(u, "tenant_name", None),
            "subtitle": getattr(u, "subtitle", None),
            "description": getattr(u, "description", None)
        })

    if search:
        s = search.strip().lower()
        results = [
            r for r in results
            if s in (r.get("unit_no") or "").lower()
            or s in (r.get("property_name") or "").lower()
            or s in (r.get("building_name") or "").lower()
            or s in (r.get("type") or "").lower()
            or s in (r.get("floor") or "").lower()
            or s in (r.get("tenant_name") or "").lower()
        ]

    return results


# ---------------------------------------------------------------------
# 2. CREATE UNIT (Matches POST /api/units & POST /api/units/)
# ---------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_unit(
    unit_in: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(unit_in.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    # 1. Verify and resolve parent property
    prop_id_raw = unit_in.get("property_id")
    parent_prop = None

    if prop_id_raw and str(prop_id_raw).strip() not in ("undefined", "null", ""):
        try:
            p_uuid = uuid.UUID(str(prop_id_raw).strip())
            parent_prop = db.scalar(
                select(models.Property).where(
                    models.Property.id == p_uuid,
                    or_(
                        models.Property.organization_id == org_id,
                        models.Property.organization_id.is_(None)
                    )
                )
            )
        except ValueError:
            pass

    if not parent_prop:
        parent_prop = db.scalar(
            select(models.Property).where(
                or_(
                    models.Property.organization_id == org_id,
                    models.Property.organization_id.is_(None)
                )
            )
        )

    if not parent_prop:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A registered Property asset is required before creating units."
        )

    prop_id = parent_prop.id
    unit_no_val = (unit_in.get("unit_no") or unit_in.get("unit_number") or "").strip()
    if not unit_no_val:
        unit_no_val = f"U-{str(uuid.uuid4())[:4].upper()}"

    # 2. Duplicate check
    existing = db.scalar(
        select(models.Unit).where(
            models.Unit.organization_id == org_id,
            models.Unit.property_id == prop_id,
            models.Unit.unit_no.ilike(unit_no_val)
        )
    )
    if existing:
        unit_no_val = f"{unit_no_val}-{str(uuid.uuid4())[:3].upper()}"

    # 3. Assemble record
    new_id = uuid.uuid4()
    if unit_in.get("id"):
        try:
            new_id = uuid.UUID(str(unit_in["id"]))
        except ValueError:
            pass

    rent_val = float(unit_in.get("rent") or unit_in.get("rent_amount") or 0.00)
    sqm_val = float(unit_in.get("sqm") or 45.00)
    floor_val = (unit_in.get("floor") or "1st Floor").strip()
    floor_num = int(unit_in.get("floor_number") or "".join(filter(str.isdigit, floor_val)) or 1)

    unit_data = {
        "id": new_id,
        "organization_id": org_id,
        "property_id": prop_id,
        "unit_no": unit_no_val,
        "unit_number": unit_no_val,
        "type": unit_in.get("type") or "1-Bedroom Apartment",
        "floor": floor_val,
        "floor_number": floor_num,
        "sqm": sqm_val,
        "status": unit_in.get("status") or "Available",
        "subtitle": unit_in.get("subtitle") or f"{floor_val} · Standard Unit",
        "description": unit_in.get("description")
    }

    if hasattr(models.Unit, "rent"):
        unit_data["rent"] = rent_val
    if hasattr(models.Unit, "rent_amount"):
        unit_data["rent_amount"] = rent_val

    # Optional building link
    bldg_id_raw = unit_in.get("building_id")
    if bldg_id_raw and str(bldg_id_raw).strip() not in ("undefined", "null", ""):
        try:
            unit_data["building_id"] = uuid.UUID(str(bldg_id_raw).strip())
        except ValueError:
            pass

    db_unit = models.Unit(**unit_data)
    db.add(db_unit)

    # Increment property unit counter
    if hasattr(parent_prop, "units_count"):
        parent_prop.units_count = (parent_prop.units_count or 0) + 1

    db.commit()
    db.refresh(db_unit)

    return {
        "id": str(db_unit.id),
        "organization_id": str(db_unit.organization_id),
        "property_id": str(db_unit.property_id),
        "unit_no": db_unit.unit_no,
        "type": db_unit.type,
        "floor": db_unit.floor,
        "sqm": float(db_unit.sqm or 0),
        "rent": float(getattr(db_unit, "rent", None) or getattr(db_unit, "rent_amount", None) or 0),
        "status": db_unit.status
    }


# ---------------------------------------------------------------------
# 3. GET SINGLE UNIT
# ---------------------------------------------------------------------
@router.get("/{unit_id}")
@router.get("/{unit_id}/")
def get_unit(
    unit_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    unit = find_unit_by_identifier(db, unit_id, org_id)
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit not found."
        )

    rent_val = float(getattr(unit, "rent", None) or getattr(unit, "rent_amount", None) or 0.0)
    return {
        "id": str(unit.id),
        "organization_id": str(unit.organization_id or org_id),
        "property_id": str(unit.property_id),
        "building_id": str(unit.building_id) if getattr(unit, "building_id", None) else None,
        "unit_no": unit.unit_no,
        "type": unit.type,
        "floor": unit.floor,
        "sqm": float(unit.sqm or 0),
        "rent": rent_val,
        "rent_amount": rent_val,
        "status": unit.status
    }


# ---------------------------------------------------------------------
# 4. UPDATE UNIT (PUT / PATCH)
# ---------------------------------------------------------------------
@router.put("/{unit_id}")
@router.put("/{unit_id}/")
@router.patch("/{unit_id}")
@router.patch("/{unit_id}/")
def update_unit(
    unit_id: str,
    unit_update: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    db_unit = find_unit_by_identifier(db, unit_id, org_id)
    if not db_unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit not found."
        )

    # Normalize status string
    if "status" in unit_update and unit_update["status"]:
        s = str(unit_update["status"]).strip().upper()
        if s in ("AVAILABLE", "VACANT"):
            unit_update["status"] = "Available"
        elif s in ("OCCUPIED", "LEASED"):
            unit_update["status"] = "Occupied"
        elif s in ("MAINTENANCE", "UNDER_MAINTENANCE"):
            unit_update["status"] = "Maintenance"

    for field, value in unit_update.items():
        if hasattr(db_unit, field):
            if field in ("property_id", "building_id") and value:
                try:
                    setattr(db_unit, field, uuid.UUID(str(value)))
                except ValueError:
                    pass
            elif field in ("rent", "rent_amount", "sqm") and value is not None:
                setattr(db_unit, field, float(value))
            else:
                setattr(db_unit, field, value)
        elif field == "rent" and hasattr(db_unit, "rent_amount") and value is not None:
            setattr(db_unit, "rent_amount", float(value))
        elif field == "rent_amount" and hasattr(db_unit, "rent") and value is not None:
            setattr(db_unit, "rent", float(value))

    db.commit()
    db.refresh(db_unit)

    rent_val = float(getattr(db_unit, "rent", None) or getattr(db_unit, "rent_amount", None) or 0.0)
    return {
        "id": str(db_unit.id),
        "organization_id": str(db_unit.organization_id),
        "property_id": str(db_unit.property_id),
        "unit_no": db_unit.unit_no,
        "type": db_unit.type,
        "floor": db_unit.floor,
        "sqm": float(db_unit.sqm or 0),
        "rent": rent_val,
        "status": db_unit.status
    }


# ---------------------------------------------------------------------
# 5. DELETE UNIT
# ---------------------------------------------------------------------
@router.delete("/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{unit_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_unit(
    unit_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    db_unit = find_unit_by_identifier(db, unit_id, org_id)
    if not db_unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unit not found."
        )

    try:
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