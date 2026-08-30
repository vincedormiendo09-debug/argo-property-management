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


# ---------------------------------------------------------------------
# 1. GET BUILDINGS (Supports /api/buildings & /api/buildings/)
# ---------------------------------------------------------------------
@router.get("")
@router.get("/")
def read_buildings(
    organization_id: Optional[str] = Query(default=None),
    property_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    stmt = select(models.Building).where(
        or_(
            models.Building.organization_id == org_id,
            models.Building.organization_id.is_(None)
        )
    )

    if property_id and property_id not in ("undefined", "null", ""):
        try:
            stmt = stmt.where(models.Building.property_id == uuid.UUID(property_id))
        except ValueError:
            pass

    if status_filter:
        stmt = stmt.where(models.Building.status.ilike(f"%{status_filter.strip()}%"))

    buildings_list = list(db.scalars(stmt).all())

    # Map property names for display
    props_map = {
        p.id: (getattr(p, "name", None) or getattr(p, "property_name", None) or "Property Asset")
        for p in db.scalars(select(models.Property)).all()
    }

    results: List[Dict[str, Any]] = []
    for b in buildings_list:
        b_id = str(b.id)
        p_id = b.property_id
        prop_name = props_map.get(p_id, "Property Asset")

        results.append({
            "id": b_id,
            "organization_id": str(getattr(b, "organization_id", None) or org_id),
            "property_id": str(p_id),
            "property_name": prop_name,
            "property": prop_name,
            "code": getattr(b, "code", f"BLDG-{b_id[:4].upper()}"),
            "name": getattr(b, "name", "Building"),
            "floors": int(getattr(b, "floors", 1) or 1),
            "total_units": int(getattr(b, "total_units", 0) or 0),
            "occupied_units": int(getattr(b, "occupied_units", 0) or 0),
            "status": getattr(b, "status", "Active") or "Active",
            "floor_distribution": getattr(b, "floor_distribution", None)
        })

    if search:
        s = search.strip().lower()
        results = [
            r for r in results
            if s in (r.get("name") or "").lower()
            or s in (r.get("code") or "").lower()
            or s in (r.get("property_name") or "").lower()
        ]

    return results


# ---------------------------------------------------------------------
# 2. CREATE BUILDING (Supports POST /api/buildings & POST /api/buildings/)
# ---------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_building(
    bldg_in: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(bldg_in.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    bldg_name = (bldg_in.get("name") or "").strip()
    if not bldg_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Building Name is required."
        )

    # 1. Resolve parent property
    prop_id_raw = bldg_in.get("property_id")
    prop = None

    if prop_id_raw and str(prop_id_raw).strip() not in ("undefined", "null", ""):
        try:
            prop_uuid = uuid.UUID(str(prop_id_raw).strip())
            prop = db.scalar(
                select(models.Property).where(
                    models.Property.id == prop_uuid,
                    or_(
                        models.Property.organization_id == org_id,
                        models.Property.organization_id.is_(None)
                    )
                )
            )
        except ValueError:
            pass

    if not prop:
        prop = db.scalar(
            select(models.Property).where(
                or_(
                    models.Property.organization_id == org_id,
                    models.Property.organization_id.is_(None)
                )
            )
        )

    if not prop:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A registered Property asset is required before adding buildings."
        )

    prop_id = prop.id
    bldg_code = (bldg_in.get("code") or f"BLDG-{str(uuid.uuid4())[:4].upper()}").strip()

    # 2. Scoped duplicate code check
    existing = db.scalar(
        select(models.Building).where(
            models.Building.organization_id == org_id,
            models.Building.code.ilike(bldg_code)
        )
    )
    if existing:
        bldg_code = f"{bldg_code}-{str(uuid.uuid4())[:3].upper()}"

    floors = int(bldg_in.get("floors") or 1)
    floor_dist = bldg_in.get("floor_distribution")

    if not floor_dist or not isinstance(floor_dist, dict):
        floor_dist = {f"Floor {i}": 4 for i in range(1, floors + 1)}

    calculated_total_units = int(bldg_in.get("total_units") or sum(int(v) for v in floor_dist.values()))

    bldg_id = uuid.uuid4()
    if bldg_in.get("id"):
        try:
            bldg_id = uuid.UUID(str(bldg_in["id"]))
        except ValueError:
            pass

    db_bldg = models.Building(
        id=bldg_id,
        organization_id=org_id,
        property_id=prop_id,
        code=bldg_code,
        name=bldg_name,
        floors=floors,
        total_units=calculated_total_units,
        occupied_units=int(bldg_in.get("occupied_units") or 0),
        status=bldg_in.get("status") or "Active",
        floor_distribution=floor_dist
    )
    db.add(db_bldg)

    # 3. Automatically provision corresponding unit rows in inventory
    units_created = 0
    for floor_key, unit_count in floor_dist.items():
        floor_num_str = "".join(filter(str.isdigit, floor_key)) or "1"
        try:
            f_num = int(floor_num_str)
        except ValueError:
            f_num = 1

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

    if hasattr(prop, "units_count"):
        prop.units_count = (prop.units_count or 0) + units_created

    db.commit()
    db.refresh(db_bldg)

    return {
        "id": str(db_bldg.id),
        "organization_id": str(db_bldg.organization_id),
        "property_id": str(db_bldg.property_id),
        "code": db_bldg.code,
        "name": db_bldg.name,
        "floors": db_bldg.floors,
        "total_units": db_bldg.total_units,
        "occupied_units": db_bldg.occupied_units,
        "status": db_bldg.status,
        "floor_distribution": db_bldg.floor_distribution
    }


# ---------------------------------------------------------------------
# 3. GET SINGLE BUILDING
# ---------------------------------------------------------------------
@router.get("/{building_id}")
@router.get("/{building_id}/")
def get_building(
    building_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    clean_id = building_id.strip()

    bldg = None
    try:
        b_uuid = uuid.UUID(clean_id)
        bldg = db.scalar(
            select(models.Building).where(
                models.Building.id == b_uuid,
                or_(
                    models.Building.organization_id == org_id,
                    models.Building.organization_id.is_(None)
                )
            )
        )
    except ValueError:
        pass

    if not bldg and hasattr(models.Building, "code"):
        bldg = db.scalar(
            select(models.Building).where(
                models.Building.code.ilike(clean_id),
                or_(
                    models.Building.organization_id == org_id,
                    models.Building.organization_id.is_(None)
                )
            )
        )

    if not bldg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found."
        )

    return {
        "id": str(bldg.id),
        "organization_id": str(bldg.organization_id or org_id),
        "property_id": str(bldg.property_id),
        "code": bldg.code,
        "name": bldg.name,
        "floors": bldg.floors,
        "total_units": bldg.total_units,
        "occupied_units": bldg.occupied_units,
        "status": bldg.status,
        "floor_distribution": bldg.floor_distribution
    }


# ---------------------------------------------------------------------
# 4. UPDATE BUILDING (PUT / PATCH)
# ---------------------------------------------------------------------
@router.put("/{building_id}")
@router.put("/{building_id}/")
@router.patch("/{building_id}")
@router.patch("/{building_id}/")
def update_building(
    building_id: str,
    bldg_update: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    clean_id = building_id.strip()

    db_bldg = None
    try:
        b_uuid = uuid.UUID(clean_id)
        db_bldg = db.scalar(
            select(models.Building).where(
                models.Building.id == b_uuid,
                or_(
                    models.Building.organization_id == org_id,
                    models.Building.organization_id.is_(None)
                )
            )
        )
    except ValueError:
        pass

    if not db_bldg and hasattr(models.Building, "code"):
        db_bldg = db.scalar(
            select(models.Building).where(
                models.Building.code.ilike(clean_id),
                or_(
                    models.Building.organization_id == org_id,
                    models.Building.organization_id.is_(None)
                )
            )
        )

    if not db_bldg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found."
        )

    for field, value in bldg_update.items():
        if hasattr(db_bldg, field):
            if field == "property_id" and value:
                try:
                    setattr(db_bldg, field, uuid.UUID(str(value)))
                except ValueError:
                    pass
            else:
                setattr(db_bldg, field, value)

    db.commit()
    db.refresh(db_bldg)

    return {
        "id": str(db_bldg.id),
        "organization_id": str(db_bldg.organization_id),
        "property_id": str(db_bldg.property_id),
        "code": db_bldg.code,
        "name": db_bldg.name,
        "floors": db_bldg.floors,
        "total_units": db_bldg.total_units,
        "occupied_units": db_bldg.occupied_units,
        "status": db_bldg.status,
        "floor_distribution": db_bldg.floor_distribution
    }


# ---------------------------------------------------------------------
# 5. DELETE BUILDING
# ---------------------------------------------------------------------
@router.delete("/{building_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{building_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_building(
    building_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    clean_id = building_id.strip()

    db_bldg = None
    try:
        b_uuid = uuid.UUID(clean_id)
        db_bldg = db.scalar(
            select(models.Building).where(
                models.Building.id == b_uuid,
                or_(
                    models.Building.organization_id == org_id,
                    models.Building.organization_id.is_(None)
                )
            )
        )
    except ValueError:
        pass

    if not db_bldg and hasattr(models.Building, "code"):
        db_bldg = db.scalar(
            select(models.Building).where(
                models.Building.code.ilike(clean_id),
                or_(
                    models.Building.organization_id == org_id,
                    models.Building.organization_id.is_(None)
                )
            )
        )

    if not db_bldg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found."
        )

    try:
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